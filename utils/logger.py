import logging
import os
import sys
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
import colorama
from colorama import Fore, Style

# Inicializar colorama
colorama.init(autoreset=True)

# Definir códigos de cores para diferentes níveis de log
LOG_COLORS = {
    'DEBUG': Fore.CYAN,
    'INFO': Fore.GREEN,
    'WARNING': Fore.YELLOW,
    'ERROR': Fore.RED,
    'CRITICAL': Fore.MAGENTA + Style.BRIGHT
}

# Definir símbolos para diferentes níveis de log
LOG_SYMBOLS = {
    'DEBUG': '🔍',
    'INFO': 'ℹ️',
    'WARNING': '⚠️',
    'ERROR': '❌',
    'CRITICAL': '🔥'
}

# Definir formato de log personalizado
LOG_FORMAT = '%(asctime)s - %(symbol)s %(colored_levelname)s - %(name)s - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Definir localização do arquivo de log
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'keepa_bot.log')

class SensitiveDataFilter(logging.Filter):
    """Filtro para remover dados sensíveis dos logs"""
    
    def __init__(self):
        super().__init__()
        # Padrões para filtrar
        self.patterns = [
            # Requisições HTTP com tokens
            re.compile(r'(HTTP Request: (POST|GET) https://api\.telegram\.org/bot)[^/]+(/\w+)'),
            # Tokens do Telegram
            re.compile(r'([0-9]{8,10}:AAF[A-Za-z0-9_-]{30,35})'),
            # Endereços de e-mail
            re.compile(r'(\w+@\w+\.\w+)'),
            # Senhas em texto claro
            re.compile(r'password=([^&\s]+)'),
        ]
        
        # Módulos para filtrar completamente
        self.filtered_modules = [
            'httpx',
            'urllib3',
            'selenium.webdriver.remote',
            'PIL',
        ]
    
    def filter(self, record):
        # Pular logs de certos módulos
        if any(record.name.startswith(module) for module in self.filtered_modules):
            return False
            
        # Filtrar dados sensíveis da mensagem
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            # Aplicar cada padrão
            for pattern in self.patterns:
                # Usar um try-except para lidar com diferentes tipos de padrões
                try:
                    if hasattr(pattern, 'groups') and callable(pattern.groups):
                        num_groups = len(pattern.groups())
                        if num_groups > 1:
                            record.msg = pattern.sub(r'\1***\3', record.msg)
                        else:
                            record.msg = pattern.sub(r'***', record.msg)
                    else:
                        # Caso padrão para expressões regulares simples
                        record.msg = pattern.sub(r'***', record.msg)
                except (TypeError, AttributeError):
                    # Fallback para substituição simples em caso de erro
                    try:
                        record.msg = pattern.sub(r'***', record.msg)
                    except:
                        pass  # Ignora se não puder substituir
        
        return True

class ColoredFormatter(logging.Formatter):
    """Formatador personalizado para adicionar cores e símbolos às mensagens de log"""
    
    def format(self, record):
        # Salvar o formato original
        levelname = record.levelname
        
        # Adicionar o levelname colorido e o símbolo ao registro
        record.colored_levelname = LOG_COLORS.get(levelname, '') + levelname + Style.RESET_ALL
        record.symbol = LOG_SYMBOLS.get(levelname, '')
        
        # Chamar o método format do formatador original
        return super().format(record)

def setup_logging(log_level=logging.INFO, console_output=True, file_output=True, max_file_size=10*1024*1024, backup_count=5):
    """
    Configurar configuração de log com filtragem e formatação aprimoradas
    
    Args:
        log_level (int): O nível de log (por exemplo, logging.INFO)
        console_output (bool): Se deve gerar logs para o console
        file_output (bool): Se deve gerar logs para arquivo
        max_file_size (int): Tamanho máximo de cada arquivo de log em bytes
        backup_count (int): Número de arquivos de log de backup a manter
    """
    # Criar logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remover manipuladores existentes para evitar duplicados
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Criar filtro para dados sensíveis
    sensitive_filter = SensitiveDataFilter()
    
    # Criar formatadores
    colored_formatter = ColoredFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s', datefmt=DATE_FORMAT)
    
    # Adicionar manipulador de console se solicitado
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(colored_formatter)
        console_handler.addFilter(sensitive_filter)
        root_logger.addHandler(console_handler)
    
    # Adicionar manipulador de arquivo se solicitado
    if file_output:
        # Criar diretório de logs se não existir
        os.makedirs(LOG_DIR, exist_ok=True)
        
        # Criar manipulador de arquivo rotativo
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=max_file_size,
            backupCount=backup_count
        )
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(sensitive_filter)
        root_logger.addHandler(file_handler)
    
    # Definir níveis específicos para módulos barulhentos
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('selenium').setLevel(logging.WARNING)
    
    return root_logger

def get_logger(name):
    """
    Obter um logger com o nome especificado
    
    Args:
        name (str): O nome do logger
        
    Returns:
        logging.Logger: O logger
    """
    return logging.getLogger(name)