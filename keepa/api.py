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
        
        # Primeiro verificar se o menu do usuário está presente
        if not check_element_exists(driver, "#panelUserMenu", timeout=3):
            logger.info("Menu do usuário não encontrado. Provavelmente não está logado.")
            return False
            
        # Aguardar que o elemento seja visível
        try:
            username_element = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.ID, "panelUsername"))
            )
            username_text = username_element.text
            
            # Caso o texto do nome de usuário esteja vazio, tentar obter o HTML diretamente
            if not username_text:
                logger.info("Nome de usuário vazio, obtendo HTML interno")
                username_html = driver.execute_script(
                    "return document.getElementById('panelUsername').innerHTML"
                )
                username_text = username_html.strip()
                
            logger.info(f"Nome de usuário encontrado: {username_text}")
            
            # Método simplificado - apenas verificar se o identificador está no texto de usuário
            if account_identifier.lower() in username_text.lower():
                logger.info(f"✅ Já logado como {account_identifier}")
                return True
            
            # Caso especial para Premium (jobadira)
            if account_identifier == "Premium" and ("jobadira" in username_text.lower() or "premium" in username_text.lower()):
                logger.info(f"✅ Já logado na conta Premium")
                return True
                
            logger.info(f"⚠️ Logado em uma conta diferente: {username_text}")
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao verificar elemento de nome de usuário: {str(e)}")
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
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot de pré-login salvo em: {screenshot_path}")
        
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
        
        # Tornar a sobreposição de login visível - usar um método mais robusto
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
            driver.save_screenshot(screenshot_path)
            logger.info(f"Screenshot salvo em: {screenshot_path}")
            return False

        # Verificar CAPTCHA
        if check_element_visible(driver, "iframe[title='reCAPTCHA']", timeout=3):
            logger.warning("⚠️ CAPTCHA detectado. O modo automatizado não pode prosseguir.")
            driver.save_screenshot("captcha_detected.png")
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
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot pós-login salvo em: {screenshot_path}")

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
        driver.save_screenshot("login_error.png")
        return False

@sync_retry(max_attempts=3, delay=2)
def update_keepa_product(driver, asin, price):
    """
    Atualizar preço-alvo para um produto no Keepa
    """
    logger.info(f"Atualizando produto ASIN {asin} com preço {price}")
    
    try:
        # Navegar para a página do produto
        driver.get(f"https://keepa.com/#!product/12-{asin}")
        
        # Verificar se a página carregou corretamente
        try:
            wait_for_element(driver, "#productInfoBox", timeout=10)
        except TimeoutException:
            logger.warning(f"⚠️ A página do produto para {asin} não carregou corretamente")
            return False

        # Clicar na aba de rastreamento
        try:
            click_element(driver, "#tabTrack")
            time.sleep(3)  # Esperar animações
        except Exception as e:
            logger.error(f"❌ Falha ao acessar a aba de rastreamento: {str(e)}")
            return False

        # Verificar se o rastreamento já existe
        if settings.UPDATE_EXISTING_TRACKING and check_element_exists(driver, "#updateTracking"):
            logger.info("🔄 Alerta existente encontrado, atualizando...")
            try:
                click_element(driver, "#updateTracking")
                time.sleep(2)  # Esperar carregamento
                
                # Encontrar e preencher o campo de preço
                price_container = wait_for_element(
                    driver,
                    "//label[contains(.,'Amazon')]/ancestor::div[contains(@class,'mdc-text-field')]//input",
                    By.XPATH
                )
                driver.execute_script(f"""
                    var input = arguments[0];
                    input.value = '';
                    input.value = '{price}';
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change'));
                """, price_container)
                
                # Enviar atualização
                btn_submit = wait_for_element(driver, "#submitTracking", timeout=8)
                driver.execute_script("arguments[0].click();", btn_submit)
                logger.info(f"✅ Alerta atualizado com sucesso para {asin}")
                time.sleep(4)
                return True
            except Exception as e:
                logger.error(f"❌ Erro ao atualizar alerta: {str(e)}")
                return False
        elif check_element_exists(driver, "#updateTracking"):
            logger.info(f"✅ Alerta já existe para {asin}, mas não foi atualizado")
            return True

        # Criar novo alerta
        try:
            # Encontrar campo de preço usando o rótulo
            price_container = wait_for_element(
                driver,
                "//label[contains(.,'Amazon')]/ancestor::div[contains(@class,'mdc-text-field')]//input",
                By.XPATH
            )
            
            # Preencher valor
            driver.execute_script(f"""
                var input = arguments[0];
                input.value = '';
                input.value = '{price}';
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change'));
            """, price_container)
            
            # Tentar criar novo alerta
            btn_submit = wait_for_element(driver, "#submitTracking", timeout=8)
            driver.execute_script("arguments[0].click();", btn_submit)
            logger.info(f"✅ Novo alerta criado para {asin}")
            time.sleep(4)  # Esperar confirmação
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao criar alerta: {str(e)}")
            return False

    except Exception as e:
        logger.error(f"❌ Erro crítico: {str(e)}")
        screenshot_path = os.path.join(os.getcwd(), f"error_{asin}.png")
        driver.save_screenshot(screenshot_path)
        return False
    
    
def delete_keepa_tracking(driver, asin):
    """
    Excluir rastreamento para um produto no Keepa
    
    Args:
        driver: Instância do Selenium WebDriver
        asin: ASIN do produto para excluir o rastreamento
        
    Returns:
        bool: True se a exclusão for bem-sucedida, False caso contrário
    """
    logger.info(f"🗑️ Tentando excluir rastreamento para ASIN {asin}")
    
    try:
        # Navegar para a página do produto
        driver.get(f"https://keepa.com/#!product/12-{asin}")
        
        # Verificar se a página carregou corretamente
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "productInfoBox"))
            )
            logger.info(f"Página do produto para {asin} carregada corretamente")
        except TimeoutException:
            logger.warning(f"⚠️ A página do produto para {asin} não carregou corretamente")
            return False

        # Clicar na aba de rastreamento
        try:
            tracking_tab = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "tabTrack"))
            )
            driver.execute_script("arguments[0].click();", tracking_tab)
            time.sleep(5)  # Esperar animações
            logger.info("Aba de rastreamento aberta")
        except Exception as e:
            logger.error(f"❌ Falha ao acessar a aba de rastreamento: {str(e)}")
            return False

        # Verificar se o rastreamento existe (botão deleteTracking deve estar presente)
        if not check_element_exists(driver, "#deleteTracking"):
            logger.warning(f"⚠️ Nenhum rastreamento encontrado para ASIN {asin}")
            return False
        
        # Rastreamento existe, tentar excluir
        logger.info("Rastreamento existe, tentando excluir")
        
        try:
            # Clicar no botão de excluir rastreamento
            delete_button = driver.find_element(By.ID, "deleteTracking")
            driver.execute_script("arguments[0].click();", delete_button)
            time.sleep(3)  # Esperar que a ação seja concluída
            
            # Verificar se o botão sumiu (o que indica sucesso na exclusão)
            # Usamos um timeout curto porque esperamos que não encontre o elemento
            if check_element_exists(driver, "#deleteTracking", timeout=2):
                logger.warning(f"⚠️ Botão de exclusão ainda presente após clicar, a exclusão pode ter falhado")
                return False
            else:
                logger.info(f"✅ Rastreamento excluído com sucesso para ASIN {asin} (botão de exclusão não mais presente)")
                return True
                
        except Exception as e:
            logger.error(f"❌ Erro ao clicar no botão de exclusão: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erro crítico durante exclusão: {str(e)}")
        screenshot_path = f"delete_error_{asin}.png"
        driver.save_screenshot(screenshot_path)
        return False