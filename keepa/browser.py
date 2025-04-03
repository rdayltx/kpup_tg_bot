import os
import time
import random
import logging
import uuid
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from utils.logger import get_logger

logger = get_logger(__name__)

def find_chromedriver_manually():
    """
    Encontrar o caminho do executável ChromeDriver manualmente.
    """
    try:
        # Verificar variável de ambiente primeiro
        chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
        if chromedriver_path and os.path.exists(chromedriver_path) and os.access(chromedriver_path, os.X_OK):
            logger.info(f"Chromedriver encontrado na variável de ambiente em: {chromedriver_path}")
            return chromedriver_path
            
        # Tentar encontrar chromedriver no sistema
        result = subprocess.run(['which', 'chromedriver'], capture_output=True, text=True)
        if result.returncode == 0:
            chromedriver_path = result.stdout.strip()
            logger.info(f"Chromedriver encontrado em: {chromedriver_path}")
            return chromedriver_path
        
        # Procurar em diretórios comuns
        common_paths = [
            "/usr/local/bin/chromedriver",
            "/usr/bin/chromedriver",
            os.path.expanduser("~/.wdm/drivers/chromedriver")
        ]
        
        for path in common_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                logger.info(f"Chromedriver encontrado em: {path}")
                return path
        
        # Buscar no diretório ~/.wdm recursivamente
        wdm_dir = os.path.expanduser("~/.wdm")
        if os.path.exists(wdm_dir):
            for root, _, files in os.walk(wdm_dir):
                for file in files:
                    if file == "chromedriver" or file == "chromedriver.exe":
                        file_path = os.path.join(root, file)
                        if os.access(file_path, os.X_OK):
                            logger.info(f"Chromedriver encontrado em: {file_path}")
                            return file_path
        
        return None
    except Exception as e:
        logger.error(f"Erro ao procurar o chromedriver: {str(e)}")
        return None

def initialize_driver(account_identifier=None):
    """
    Inicializar WebDriver Selenium para Chrome
    
    Args:
        account_identifier: Identificador opcional para criar diretórios de dados separados para diferentes contas
    
    Returns:
        WebDriver: Instância configurada do WebDriver Chrome
    """
    # Usar um identificador de sessão baseado na conta
    session_id = account_identifier or "default"
    
    # Usar um diretório fixo para cada conta, sem UUID aleatório
    chrome_data_dir = os.getenv("CHROME_USER_DATA_DIR", "/tmp/chrome-data")
    unique_data_dir = f"{chrome_data_dir}-{session_id}"
    
    # Garantir que o diretório exista
    os.makedirs(unique_data_dir, exist_ok=True)
    
    # Configurar opções do Chrome
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Usar o diretório de dados fixo por conta
    chrome_options.add_argument(f"--user-data-dir={unique_data_dir}")
    logger.info(f"Usando diretório de dados Chrome para conta: {unique_data_dir}")
    
    # Resto do código permanece o mesmo...
    
    # Configurações adicionais para evitar detecção
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    # Tentar criar e configurar o driver
    try:
        # Primeiro tentar caminho direto da variável de ambiente
        chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
        if chromedriver_path and os.path.exists(chromedriver_path):
            logger.info(f"Usando ChromeDriver do caminho da variável de ambiente: {chromedriver_path}")
            service = Service(executable_path=chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info(f"Chrome inicializado com sucesso usando caminho da variável de ambiente: {chromedriver_path}")
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info(f"Sessão do navegador inicializada para conta: {account_identifier}")
            return driver
    except Exception as e:
        logger.warning(f"Falha ao inicializar Chrome usando caminho da variável de ambiente: {str(e)}")
    
    # Tentar encontrar chromedriver manualmente
    chromedriver_path = find_chromedriver_manually()
    
    if chromedriver_path:
        try:
            service = Service(executable_path=chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info(f"Chrome inicializado com sucesso usando caminho manual: {chromedriver_path}")
            
            # Desabilitar flag webdriver
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info(f"Sessão do navegador inicializada para conta: {account_identifier}")
            return driver
        except Exception as e:
            logger.error(f"Erro ao usar caminho manual do chromedriver: {str(e)}")
            raise Exception(f"Falha ao inicializar Chrome. Erro: {str(e)}")
    else:
        # Último recurso: Tentar usar Chrome integrado
        try:
            logger.info("Tentando usar webdriver_manager como último recurso...")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info("Chrome inicializado com sucesso usando ChromeDriverManager")
            
            # Desabilitar flag webdriver
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info(f"Sessão do navegador inicializada para conta: {account_identifier}")
            return driver
        except Exception as e:
            logger.error(f"Falha ao inicializar Chrome com todos os métodos. Erro: {str(e)}")
            raise Exception(f"Falha ao inicializar Chrome com todos os métodos. Erro: {str(e)}")