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
    # Mapeamento de identificadores de conta para nomes de usuário
    ACCOUNT_USERNAME_MAPPINGS: Dict[str, List[str]] = field(default_factory=dict)

def load_settings() -> Settings:
    """Carregar configurações das variáveis de ambiente"""
    # Carregar variáveis do arquivo .env
    load_dotenv(override=True)
    
    # Valores padrão
    data_file = "post_info.json"
    update_existing = True
    
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
    
    settings = Settings(
        TELEGRAM_BOT_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        SOURCE_CHAT_ID=os.getenv("SOURCE_CHAT_ID", ""),
        DESTINATION_CHAT_ID=os.getenv("DESTINATION_CHAT_ID", ""),
        ADMIN_ID=os.getenv("ADMIN_ID", ""),
        UPDATE_EXISTING_TRACKING=os.getenv("UPDATE_EXISTING_TRACKING", update_existing),
        DATA_FILE=os.getenv("DATA_FILE", data_file),
        KEEPA_ACCOUNTS=keepa_accounts,
        DEFAULT_KEEPA_ACCOUNT=default_account,
        ACCOUNT_USERNAME_MAPPINGS=account_mappings
    )
    
    return settings