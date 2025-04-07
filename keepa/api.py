import time
import random
import logging
import os
import re  # Adicionar esta importação para expressões regulares
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from config.settings import load_settings, KeepaAccount
from utils.retry import sync_retry

from utils.logger import get_logger

logger = get_logger(__name__)
settings = load_settings()

# Dicionário para armazenar sessões de navegador para diferentes contas
browser_sessions = {}


# Função de screenshot condicional
def save_debug_screenshot(driver, filename, force=False):
    """
    Salva screenshot apenas se settings.ENABLE_SCREENSHOTS for True ou force=True.
    Loga apenas se settings.ENABLE_SCREENSHOT_LOGS for True.
    
    Args:
        driver: WebDriver do Selenium
        filename: Nome do arquivo para salvar
        force: Forçar captura mesmo se screenshots estiverem desabilitados
    """
    # Verificar se devemos capturar a tela
    if not (settings.ENABLE_SCREENSHOTS or force):
        return
        
    try:
        screenshot_path = os.path.join(os.getcwd(), filename)
        driver.save_screenshot(screenshot_path)
        
        # Logar apenas se o logging de screenshots estiver habilitado
        if settings.ENABLE_SCREENSHOT_LOGS:
            logger.info(f"Screenshot salvo em: {screenshot_path}")
    except Exception as e:
        # Sempre logar erros (isso é importante para diagnóstico)
        logger.error(f"Erro ao salvar screenshot: {str(e)}")

# Funções de espera por elementos
def wait_for_element(driver, selector, by=By.CSS_SELECTOR, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )

def wait_for_visible_element(driver, selector, by=By.CSS_SELECTOR, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, selector))
    )

def click_element(driver, selector, by=By.CSS_SELECTOR):
    element = wait_for_element(driver, selector, by)
    driver.execute_script("arguments[0].click();", element)

def check_element_exists(driver, selector, by=By.CSS_SELECTOR, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        return True
    except TimeoutException:
        return False

def check_element_visible(driver, selector, by=By.CSS_SELECTOR, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((by, selector))
        )
        return True
    except TimeoutException:
        return False

def check_logged_in_account(driver, account_identifier):
    """
    Verificar se já está logado na conta especificada
    
    Args:
        driver: Instância do Selenium WebDriver
        account_identifier: Identificador de string para a conta
        
    Returns:
        bool: True se estiver logado na conta correta, False caso contrário
    """
    try:
        # Aguardar um pouco para a página carregar completamente
        time.sleep(2)
        
        # Verificar se há um menu de usuário ou elemento de perfil
        if check_element_exists(driver, "#panelUserMenu", timeout=3):
            logger.info("Menu do usuário encontrado")
            
            # Verificar se o username está visível
            try:
                username_element = wait_for_element(driver, "#panelUsername", timeout=5)
                username_text = username_element.text.strip()
                
                # Se o texto do nome de usuário estiver vazio, tentar obter o HTML diretamente
                if not username_text:
                    username_text = driver.execute_script(
                        "return document.getElementById('panelUsername').textContent || '';"
                    ).strip()
                
                logger.info(f"Nome de usuário encontrado: {username_text}")
                
                # Verificar se o identificador de conta está no texto de usuário
                if account_identifier.lower() in username_text.lower():
                    logger.info(f"✅ Já logado como {account_identifier}")
                    return True
                
                # Verificar casos especiais usando as configurações
                if account_identifier in settings.ACCOUNT_USERNAME_MAPPINGS:
                    special_usernames = settings.ACCOUNT_USERNAME_MAPPINGS[account_identifier]
                    for special_username in special_usernames:
                        if special_username.lower() in username_text.lower():
                            logger.info(f"✅ Já logado na conta {account_identifier} (caso especial: {special_username})")
                            return True
                
                logger.info(f"⚠️ Logado em uma conta diferente: {username_text}")
                return False
                
            except Exception as e:
                logger.warning(f"⚠️ Erro ao verificar elemento de nome de usuário: {str(e)}")
                
                # Tentar um método alternativo para verificar login
                try:
                    # Verificar se existem elementos na interface que só aparecem quando logado
                    if check_element_exists(driver, ".tracking__buttons", timeout=3):
                        logger.info("Verificado que está logado (encontrado botões de rastreamento)")
                        return True
                except:
                    pass
                
                return False
        else:
            logger.info("Menu do usuário não encontrado. Provavelmente não está logado.")
            return False
    except Exception as e:
        logger.info(f"Não foi possível verificar o login: {str(e)}")
        return False
    
def login_to_keepa(driver, account_identifier=None):
    """
    Login no site Keepa usando o identificador de conta especificado
    
    Args:
        driver: Instância do Selenium WebDriver
        account_identifier: Identificador de string para a conta a ser usada
    
    Returns:
        bool: True se o login for bem-sucedido, False caso contrário
    """
    # Obter as credenciais de conta apropriadas
    if account_identifier and account_identifier in settings.KEEPA_ACCOUNTS:
        account = settings.KEEPA_ACCOUNTS[account_identifier]
    elif settings.DEFAULT_KEEPA_ACCOUNT in settings.KEEPA_ACCOUNTS:
        account = settings.KEEPA_ACCOUNTS[settings.DEFAULT_KEEPA_ACCOUNT]
        account_identifier = settings.DEFAULT_KEEPA_ACCOUNT
    else:
        logger.error(f"❌ Nenhuma conta Keepa válida encontrada para o identificador: {account_identifier}")
        return False
    
    logger.info(f"Iniciando processo de login no Keepa para a conta: {account_identifier}...")
    
    try:
        # Primeiro carregar a página inicial do Keepa
        driver.get("https://keepa.com")
        time.sleep(random.uniform(2, 4))  # Aumentar o tempo de espera para carregamento completo
        
        # Verificar se já está logado na conta correta
        if check_logged_in_account(driver, account_identifier):
            logger.info(f"✅ Já logado como {account_identifier}")
            return True
            
        # Capturar screenshot para diagnóstico
        screenshot_path = os.path.join(os.getcwd(), "pre_login_screen.png")
        save_debug_screenshot(driver,screenshot_path)
        # logger.info(f"Screenshot de pré-login salvo em: {screenshot_path}")
        
        # Se estiver logado mas em uma conta diferente, deslogar primeiro
        if check_element_visible(driver, "#panelUserMenu", timeout=3):
            try:
                # Clicar no menu de usuário
                click_element(driver, "#panelUserMenu")
                time.sleep(1)
                
                # Verificar se o menu de logout está visível
                if check_element_visible(driver, "//span[contains(text(), 'Logout') or contains(text(), 'Sair')]", by=By.XPATH, timeout=2):
                    # Clicar em logout
                    logout_selector = "//span[contains(text(), 'Logout') or contains(text(), 'Sair')]"
                    click_element(driver, logout_selector, By.XPATH)
                    time.sleep(3)  # Aumentar tempo de espera após logout
                    logger.info("Deslogado da conta anterior")
                else:
                    # O menu pode não ter aberto corretamente
                    logger.warning("Menu de logout não encontrado após clicar no menu do usuário")
                    driver.refresh()
                    time.sleep(3)
            except Exception as e:
                logger.warning(f"⚠️ Falha ao deslogar: {str(e)}")
                # Atualizar a página para tentar novamente
                driver.refresh()
                time.sleep(3)
        
        # Procurar pelo botão de login na nova interface
        login_buttons = [
            "a.loginLink",
            ".mdc-button:contains('Login')",
            "//a[contains(text(), 'Login')]"
        ]
        
        login_clicked = False
        for selector in login_buttons:
            try:
                if "contains" in selector:
                    # Usar JavaScript para encontrar botões por texto
                    login_clicked = driver.execute_script("""
                        var buttons = document.querySelectorAll('.mdc-button');
                        for (var i = 0; i < buttons.length; i++) {
                            if (buttons[i].textContent.includes('Login')) {
                                buttons[i].click();
                                return true;
                            }
                        }
                        return false;
                    """)
                elif selector.startswith("//"):
                    # XPath
                    if check_element_visible(driver, selector, by=By.XPATH, timeout=3):
                        click_element(driver, selector, By.XPATH)
                        login_clicked = True
                else:
                    # CSS Selector
                    if check_element_visible(driver, selector, timeout=3):
                        click_element(driver, selector)
                        login_clicked = True
                
                if login_clicked:
                    logger.info(f"Botão de login clicado usando: {selector}")
                    time.sleep(2)
                    break
            except Exception as e:
                logger.warning(f"Erro ao clicar no botão de login usando {selector}: {str(e)}")
                continue
        
        # Se não conseguimos clicar no botão de login, tentar abrir o overlay de login manualmente
        if not login_clicked:
            try:
                driver.execute_script('''
                    var overlay = document.querySelector("#loginOverlay"); 
                    if (overlay) {
                        overlay.style.display = "block";
                    } else {
                        console.log("Overlay de login não encontrado");
                        // Tentar encontrar botão de login e clicar
                        var loginBtn = document.querySelector("a.loginLink");
                        if (loginBtn) {
                            loginBtn.click();
                        }
                    }
                ''')
                logger.info("Sobreposição de login tornada visível ou botão de login clicado.")
                time.sleep(2)  # Aguardar a sobreposição aparecer
            except Exception as e:
                logger.warning(f"Erro ao tornar a sobreposição de login visível: {str(e)}")
                # Tentar método alternativo - procurar por um botão de login
                try:
                    if check_element_visible(driver, "a.loginLink", timeout=3):
                        click_element(driver, "a.loginLink")
                        time.sleep(2)
                        logger.info("Botão de login clicado.")
                except Exception as login_e:
                    logger.warning(f"Erro ao clicar no botão de login: {str(login_e)}")

        # Verificar se o formulário de login está visível
        if not check_element_visible(driver, "#username", timeout=5):
            logger.error("❌ Formulário de login não está visível após tentativas")
            screenshot_path = os.path.join(os.getcwd(), "login_form_error.png")
            save_debug_screenshot(driver,screenshot_path)
            # logger.info(f"Screenshot salvo em: {screenshot_path}")
            return False

        # Verificar CAPTCHA
        if check_element_visible(driver, "iframe[title='reCAPTCHA']", timeout=3):
            logger.warning("⚠️ CAPTCHA detectado. O modo automatizado não pode prosseguir.")
            save_debug_screenshot(driver,"captcha_detected.png")
            return False

        # Esperar explicitamente pelo campo de usuário
        username_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "username"))
        )
        
        # Preencher nome de usuário com ações mais robustas
        username_field.clear()
        time.sleep(random.uniform(0.5, 1.5))
        # Preencher caractere por caractere
        for char in account.username:
            username_field.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))  # Pequena pausa entre caracteres
        logger.info("Nome de usuário preenchido.")

        # Preencher senha
        password_field = wait_for_element(driver, "#password")
        password_field.clear()
        time.sleep(random.uniform(0.5, 1.5))
        # Preencher caractere por caractere
        for char in account.password:
            password_field.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))  # Pequena pausa entre caracteres
        logger.info("Senha preenchida.")

        # Clicar no botão de login
        time.sleep(random.uniform(1, 2))
        submit_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "submitLogin"))
        )
        driver.execute_script("arguments[0].click();", submit_button)
        logger.info("Botão de login clicado. Aguardando autenticação...")
        
        # Aguardar o carregamento da página ou aparecimento do OTP
        WebDriverWait(driver, 15).until(  # Aumentar tempo de espera
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )
        time.sleep(3)  # Buffer adicional aumentado

        # Capturar screenshot para diagnóstico
        screenshot_path = os.path.join(os.getcwd(), "post_login_screen.png")
        save_debug_screenshot(driver,screenshot_path)
        # logger.info(f"Screenshot pós-login salvo em: {screenshot_path}")

        # Verificar erros de login
        if check_element_visible(driver, "#loginError", timeout=2) and driver.find_element(By.ID, "loginError").text:
            error_text = driver.find_element(By.ID, "loginError").text
            logger.error(f"❌ Erro de login: {error_text}")
            return False
        
        # Verificar se o OTP é necessário
        if check_element_visible(driver, "#sectionLoginOtp", timeout=2):
            logger.warning("⚠️ Autenticação OTP necessária!")
            logger.warning("Por favor, verifique seu e-mail para o OTP enviado pelo Keepa.")
            return False
        
        # Verificar se o login foi bem-sucedido (tentando várias vezes)
        for attempt in range(3):
            time.sleep(2)  # Aguardar um pouco
            if check_logged_in_account(driver, account_identifier):
                logger.info(f"✅ Login bem-sucedido com a conta: {account_identifier}!")
                return True
            logger.info(f"Tentativa {attempt+1}: Ainda verificando login...")
        
        # Verificação final - tentar determinar estado
        if check_element_visible(driver, "#panelUserMenu", timeout=2):
            # Estamos logados, mas pode não ser a conta correta
            logger.warning(f"⚠️ Logado, mas pode não ser na conta {account_identifier}. Prosseguindo mesmo assim.")
            return True
        else:
            logger.warning(f"⚠️ Login pode ter falhado para conta: {account_identifier}")
            return False
    
    except Exception as e:
        logger.error(f"❌ Erro durante o login: {str(e)}")
        save_debug_screenshot(driver,"login_error.png")
        return False

@sync_retry(max_attempts=3, delay=2)
def update_keepa_product(driver, asin, price):
    """
    Atualizar preço-alvo para um produto no Keepa
    
    Returns:
        tuple: (success, product_title)
    """
    logger.info(f"Atualizando produto ASIN {asin} com preço {price} (tipo: {type(price).__name__})")
    product_title = None
    
    # Garantir que o preço seja uma string
    if not isinstance(price, str):
        price = str(price)
    
    try:
        # Navegar para a página do produto
        driver.get(f"https://keepa.com/#!product/12-{asin}")
        
        # Verificar se a página carregou corretamente
        try:
            wait_for_element(driver, "#productInfoBox", timeout=10)
            
            # Tentar obter o título do produto
            try:
                title_element = wait_for_element(driver, "#productTitle", timeout=5)
                product_title = title_element.text.strip()
                logger.info(f"Título do produto obtido: {product_title}")
            except:
                # Tentar outro seletor se o primeiro falhar
                try:
                    title_element = wait_for_element(driver, ".productTitle", timeout=5)
                    product_title = title_element.text.strip()
                    logger.info(f"Título do produto obtido (seletor alternativo): {product_title}")
                except:
                    # Tenta navegar até a Amazon para obter o título
                    try:
                        current_url = driver.current_url
                        amazon_url = f"https://www.amazon.com.br/dp/{asin}"
                        driver.get(amazon_url)
                        time.sleep(3)  # Esperar carregamento
                        
                        title_element = wait_for_element(driver, "#productTitle", timeout=5)
                        product_title = title_element.text.strip()
                        logger.info(f"Título obtido da Amazon: {product_title}")
                        
                        # Voltar para a página do Keepa
                        driver.get(current_url)
                        time.sleep(2)
                    except Exception as e:
                        logger.warning(f"Não foi possível obter o título do produto {asin}: {str(e)}")
        except TimeoutException:
            logger.warning(f"⚠️ A página do produto para {asin} não carregou corretamente")
            return False, None

        # Clicar na aba de rastreamento
        try:
            click_element(driver, "#tabTrack")
            time.sleep(3)  # Esperar animações
            
            # Capturar screenshot para diagnóstico
            screenshot_path = os.path.join(os.getcwd(), f"tracking_tab_{asin}.png")
            save_debug_screenshot(driver,screenshot_path)
            # logger.info(f"Screenshot da aba de rastreamento salvo em: {screenshot_path}")
            
        except Exception as e:
            logger.error(f"❌ Falha ao acessar a aba de rastreamento: {str(e)}")
            return False, product_title

        # Verificar se o rastreamento já existe
        if settings.UPDATE_EXISTING_TRACKING and check_element_exists(driver, "#updateTracking"):
            logger.info("🔄 Alerta existente encontrado, atualizando...")
            try:
                click_element(driver, "#updateTracking")
                time.sleep(2)  # Esperar carregamento
                
                # Identificar o campo de preço da Amazon no painel Brasil
                try:
                    # Primeiro, verificar se o painel Brasil está ativo, se não, clicar na aba Brasil
                    if not check_element_exists(driver, "#tracking__panel--12.active", timeout=2):
                        # Clicar na aba Brasil se existir
                        if check_element_exists(driver, "#tracking__tab--12"):
                            click_element(driver, "#tracking__tab--12")
                            time.sleep(1)
                    
                    # Agora tentar encontrar o campo para o preço da Amazon
                    price_field = wait_for_element(
                        driver,
                        "#csvtype-12-0-threshold",  # Campo para preço da Amazon no Brasil
                        By.CSS_SELECTOR,
                        timeout=5
                    )
                    
                    # Limpar e preencher o campo usando JavaScript
                    driver.execute_script(f"""
                        var input = arguments[0];
                        input.value = '';
                        input.value = '{price}';
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change'));
                    """, price_field)
                    
                    logger.info(f"Campo de preço preenchido com: {price}")
                    
                    # Capturar screenshot após preencher o preço
                    screenshot_path = os.path.join(os.getcwd(), f"price_filled_{asin}.png")
                    save_debug_screenshot(driver,screenshot_path)
                    
                except Exception as price_e:
                    logger.error(f"❌ Erro ao identificar campo de preço: {str(price_e)}")
                    # Tentar método alternativo usando o seletor antigo
                    try:
                        old_selector = "//label[contains(.,'Amazon')]/ancestor::div[contains(@class,'mdc-text-field')]//input"
                        price_container = wait_for_element(
                            driver,
                            old_selector,
                            By.XPATH,
                            timeout=5
                        )
                        
                        driver.execute_script(f"""
                            var input = arguments[0];
                            input.value = '';
                            input.value = '{price}';
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change'));
                        """, price_container)
                        
                        logger.info(f"Campo de preço preenchido com método alternativo: {price}")
                    except Exception as old_e:
                        logger.error(f"❌ Método alternativo também falhou: {str(old_e)}")
                        return False, product_title
                
                # Enviar atualização
                btn_submit = wait_for_element(driver, "#submitTracking", timeout=8)
                driver.execute_script("arguments[0].click();", btn_submit)
                logger.info(f"✅ Alerta atualizado com sucesso para {asin}")
                
                # Capturar screenshot após submeter
                screenshot_path = os.path.join(os.getcwd(), f"submit_success_{asin}.png")
                save_debug_screenshot(driver,screenshot_path)
                
                time.sleep(4)
                return True, product_title
            except Exception as e:
                logger.error(f"❌ Erro ao atualizar alerta: {str(e)}")
                
                # Capturar screenshot do erro
                screenshot_path = os.path.join(os.getcwd(), f"update_error_{asin}.png")
                save_debug_screenshot(driver,screenshot_path)
                
                return False, product_title
        elif check_element_exists(driver, "#updateTracking"):
            logger.info(f"✅ Alerta já existe para {asin}, mas não foi atualizado porque UPDATE_EXISTING_TRACKING é falso")
            return True, product_title

        # Criar novo alerta se não existir ou se UPDATE_EXISTING_TRACKING for falso
        try:
            # Identificar o campo de preço da Amazon no painel Brasil
            try:
                # Primeiro, verificar se o painel Brasil está ativo, se não, clicar na aba Brasil
                if not check_element_exists(driver, "#tracking__panel--12.active", timeout=2):
                    # Clicar na aba Brasil se existir
                    if check_element_exists(driver, "#tracking__tab--12"):
                        click_element(driver, "#tracking__tab--12")
                        time.sleep(1)
                
                # Capturar screenshot para diagnóstico
                screenshot_path = os.path.join(os.getcwd(), f"before_price_entry_{asin}.png")
                save_debug_screenshot(driver,screenshot_path)
                
                # Agora tentar encontrar o campo para o preço da Amazon
                price_field = wait_for_element(
                    driver,
                    "#csvtype-12-0-threshold",  # Campo para preço da Amazon no Brasil
                    By.CSS_SELECTOR,
                    timeout=5
                )
                
                # Limpar e preencher o campo usando JavaScript
                driver.execute_script(f"""
                    var input = arguments[0];
                    input.value = '';
                    input.value = '{price}';
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change'));
                """, price_field)
                
                logger.info(f"Campo de preço preenchido com: {price}")
                
            except Exception as price_e:
                logger.error(f"❌ Erro ao identificar campo de preço: {str(price_e)}")
                # Tentar método alternativo usando o seletor antigo
                try:
                    old_selector = "//label[contains(.,'Amazon')]/ancestor::div[contains(@class,'mdc-text-field')]//input"
                    price_container = wait_for_element(
                        driver,
                        old_selector,
                        By.XPATH,
                        timeout=5
                    )
                    
                    driver.execute_script(f"""
                        var input = arguments[0];
                        input.value = '';
                        input.value = '{price}';
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change'));
                    """, price_container)
                    
                    logger.info(f"Campo de preço preenchido com método alternativo: {price}")
                except Exception as old_e:
                    logger.error(f"❌ Método alternativo também falhou: {str(old_e)}")
                    return False, product_title
            
            # Tentar criar novo alerta
            btn_submit = wait_for_element(driver, "#submitTracking", timeout=8)
            driver.execute_script("arguments[0].click();", btn_submit)
            logger.info(f"✅ Novo alerta criado para {asin}")
            
            # Capturar screenshot após submeter
            screenshot_path = os.path.join(os.getcwd(), f"new_alert_success_{asin}.png")
            save_debug_screenshot(driver,screenshot_path)
            
            time.sleep(4)  # Esperar confirmação
            return True, product_title
        except Exception as e:
            logger.error(f"❌ Erro ao criar alerta: {str(e)}")
            
            # Capturar screenshot do erro
            screenshot_path = os.path.join(os.getcwd(), f"create_alert_error_{asin}.png")
            save_debug_screenshot(driver,screenshot_path)
            
            return False, product_title

    except Exception as e:
        logger.error(f"❌ Erro crítico: {str(e)}")
        screenshot_path = os.path.join(os.getcwd(), f"error_{asin}.png")
        save_debug_screenshot(driver,screenshot_path)
        return False, product_title
    
    
@sync_retry(max_attempts=3, delay=2)
def delete_keepa_tracking(driver, asin):
    """
    Excluir rastreamento para um produto no Keepa
    
    Args:
        driver: Instância do Selenium WebDriver
        asin: ASIN do produto para excluir o rastreamento
        
    Returns:
        tuple: (success, product_title) - Se a exclusão foi bem-sucedida e o título do produto (se disponível)
    """
    logger.info(f"🗑️ Tentando excluir rastreamento para ASIN {asin}")
    product_title = None
    
    try:
        # Navegar para a página do produto
        driver.get(f"https://keepa.com/#!product/12-{asin}")
        
        # Verificar se a página carregou corretamente
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "productInfoBox"))
            )
            logger.info(f"Página do produto para {asin} carregada corretamente")
            
            # Tentar obter o título do produto
            try:
                title_element = wait_for_element(driver, "#productTitle", timeout=5)
                product_title = title_element.text.strip()
                logger.info(f"Título do produto obtido: {product_title}")
            except:
                # Tentar outro seletor se o primeiro falhar
                try:
                    title_element = wait_for_element(driver, ".productTitle", timeout=5)
                    product_title = title_element.text.strip()
                    logger.info(f"Título do produto obtido (seletor alternativo): {product_title}")
                except:
                    # Tenta navegar até a Amazon para obter o título
                    try:
                        current_url = driver.current_url
                        amazon_url = f"https://www.amazon.com.br/dp/{asin}"
                        driver.get(amazon_url)
                        time.sleep(3)  # Esperar carregamento
                        
                        title_element = wait_for_element(driver, "#productTitle", timeout=5)
                        product_title = title_element.text.strip()
                        logger.info(f"Título obtido da Amazon: {product_title}")
                        
                        # Voltar para a página do Keepa
                        driver.get(current_url)
                        time.sleep(2)
                    except Exception as e:
                        logger.warning(f"Não foi possível obter o título do produto {asin}: {str(e)}")
        except TimeoutException:
            logger.warning(f"⚠️ A página do produto para {asin} não carregou corretamente")
            
            # Capturar screenshot do erro
            screenshot_path = os.path.join(os.getcwd(), f"product_load_error_{asin}.png")
            save_debug_screenshot(driver,screenshot_path)
            
            return False, None

        # Clicar na aba de rastreamento
        try:
            tracking_tab = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "tabTrack"))
            )
            driver.execute_script("arguments[0].click();", tracking_tab)
            time.sleep(5)  # Esperar animações
            logger.info("Aba de rastreamento aberta")
            
            # Capturar screenshot para diagnóstico
            screenshot_path = os.path.join(os.getcwd(), f"delete_tracking_tab_{asin}.png")
            save_debug_screenshot(driver,screenshot_path)
            
        except Exception as e:
            logger.error(f"❌ Falha ao acessar a aba de rastreamento: {str(e)}")
            return False, product_title

        # Verificar se o rastreamento existe (botão deleteTracking deve estar presente)
        if not check_element_exists(driver, "#deleteTracking"):
            logger.warning(f"⚠️ Nenhum rastreamento encontrado para ASIN {asin}")
            
            # Capturar screenshot
            screenshot_path = os.path.join(os.getcwd(), f"no_tracking_{asin}.png")
            save_debug_screenshot(driver,screenshot_path)
            
            return False, product_title
        
        # Rastreamento existe, tentar excluir
        logger.info("Rastreamento existe, tentando excluir")
        
        try:
            # Primeiro verificar se o painel Brasil está ativo
            if not check_element_exists(driver, "#tracking__panel--12.active", timeout=2):
                # Clicar na aba Brasil se existir
                if check_element_exists(driver, "#tracking__tab--12"):
                    click_element(driver, "#tracking__tab--12")
                    time.sleep(1)
            
            # Clicar no botão de excluir rastreamento
            delete_button = driver.find_element(By.ID, "deleteTracking")
            driver.execute_script("arguments[0].click();", delete_button)
            time.sleep(3)  # Esperar que a ação seja concluída
            
            # Capturar screenshot após tentar excluir
            screenshot_path = os.path.join(os.getcwd(), f"after_delete_{asin}.png")
            save_debug_screenshot(driver,screenshot_path)
            
            # Verificar se o botão sumiu (o que indica sucesso na exclusão)
            # Usamos um timeout curto porque esperamos que não encontre o elemento
            if check_element_exists(driver, "#deleteTracking", timeout=2):
                logger.warning(f"⚠️ Botão de exclusão ainda presente após clicar, a exclusão pode ter falhado")
                return False, product_title
            else:
                logger.info(f"✅ Rastreamento excluído com sucesso para ASIN {asin} (botão de exclusão não mais presente)")
                return True, product_title
                
        except Exception as e:
            logger.error(f"❌ Erro ao clicar no botão de exclusão: {str(e)}")
            
            # Capturar screenshot do erro
            screenshot_path = os.path.join(os.getcwd(), f"delete_error_{asin}.png")
            save_debug_screenshot(driver,screenshot_path)
            
            return False, product_title
            
    except Exception as e:
        logger.error(f"❌ Erro crítico durante exclusão: {str(e)}")
        screenshot_path = f"delete_error_{asin}.png"
        save_debug_screenshot(driver,screenshot_path)
        return False, product_title