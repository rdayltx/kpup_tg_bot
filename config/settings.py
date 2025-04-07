import os
from dataclasses import dataclass, field
from dotenv import load_dotenv
from typing import Dict, List

@dataclass
class KeepaAccount:
    """Credenciais da conta Keepa"""
    username: str
    password: str

@dataclass
class Settings:
    """Configurações da aplicação"""
    TELEGRAM_BOT_TOKEN: str
    SOURCE_CHAT_ID: str
    DESTINATION_CHAT_ID: str
    ADMIN_ID: str
    UPDATE_EXISTING_TRACKING: bool
    DATA_FILE: str
    # Dicionário de contas Keepa indexadas por identificador
    KEEPA_ACCOUNTS: Dict[str, KeepaAccount]
    # Conta padrão a ser usada se nenhum identificador específico for encontrado
    DEFAULT_KEEPA_ACCOUNT: str
    TARGET_CHAT_NAME: str  # Novo atributo para o nome do chat
    HARDCODED_ID: str     # Novo atributo para o ID hardcoded
    # Mapeamento de identificadores de conta para nomes de usuário
    ACCOUNT_USERNAME_MAPPINGS: Dict[str, List[str]] = field(default_factory=dict)
    # Configurações para screenshots
    ENABLE_SCREENSHOTS: bool = field(default=False)
    ENABLE_SCREENSHOT_LOGS: bool = field(default=False)

def load_settings() -> Settings:
    """Carregar configurações das variáveis de ambiente"""
    # Carregar variáveis do arquivo .env
    load_dotenv(override=True)
    
    # Valores padrão
    data_file = "post_info.json"
    update_existing = True
    target_chat_name = "chat do keepa do pobre"  # Valor padrão
    hardcoded_id = "-1002563291570"             # Valor padrão
    
    # Carregar contas Keepa
    keepa_accounts = {}
    
    # Definir identificadores de conta para procurar
    account_identifiers = ["Premium", "Meraxes", "Balerion", "Cannibal", "Vermithor"]
    
    # Carregar cada conta se definida no arquivo .env
    for identifier in account_identifiers:
        username_key = f"KEEPA_{identifier.upper()}_USERNAME"
        password_key = f"KEEPA_{identifier.upper()}_PASSWORD"
        
        username = os.getenv(username_key)
        password = os.getenv(password_key)
        
        if username and password:
            keepa_accounts[identifier] = KeepaAccount(username=username, password=password)
    
    # Definir conta padrão
    default_account = os.getenv("DEFAULT_KEEPA_ACCOUNT", "Premium")
    
    # Definir os mapeamentos especiais de nome de usuário
    account_mappings = {
        "Premium": ["jobadira", "premium"],
        "Meraxes": ["meraxes", "pobremeraxes@gmail.com"],
        "Balerion": ["balerion", "pobrebalerion@gmail.com"],
        "Cannibal": ["cannibal", "pobrecannibal@gmail.com"],
        "Vermithor": ["vermithor", "pobrevermithor@gmail.com"],
    }
    
    # Configurações de screenshots
    enable_screenshots = os.getenv("ENABLE_SCREENSHOTS", "false").lower() in ("true", "1", "yes")
    enable_screenshot_logs = os.getenv("ENABLE_SCREENSHOT_LOGS", "false").lower() in ("true", "1", "yes")
    
    settings = Settings(
        TELEGRAM_BOT_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        SOURCE_CHAT_ID=os.getenv("SOURCE_CHAT_ID", ""),
        DESTINATION_CHAT_ID=os.getenv("DESTINATION_CHAT_ID", ""),
        ADMIN_ID=os.getenv("ADMIN_ID", ""),
        UPDATE_EXISTING_TRACKING=os.getenv("UPDATE_EXISTING_TRACKING", update_existing),
        DATA_FILE=os.getenv("DATA_FILE", data_file),
        KEEPA_ACCOUNTS=keepa_accounts,
        DEFAULT_KEEPA_ACCOUNT=default_account,
        TARGET_CHAT_NAME=os.getenv("TARGET_CHAT_NAME", target_chat_name),  # Carrega do .env ou usa padrão
        HARDCODED_ID=os.getenv("HARDCODED_ID", hardcoded_id),             # Carrega do .env ou usa padrão
        ACCOUNT_USERNAME_MAPPINGS=account_mappings,
        ENABLE_SCREENSHOTS=enable_screenshots,
        ENABLE_SCREENSHOT_LOGS=enable_screenshot_logs
    )
    
    return settings