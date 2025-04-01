import os
from dataclasses import dataclass
from dotenv import load_dotenv
from typing import Dict

@dataclass
class KeepaAccount:
    """Keepa account credentials"""
    username: str
    password: str

@dataclass
class Settings:
    """Application settings"""
    TELEGRAM_BOT_TOKEN: str
    SOURCE_CHAT_ID: str
    DESTINATION_CHAT_ID: str
    ADMIN_ID: str
    UPDATE_EXISTING_TRACKING: bool
    DATA_FILE: str
    # Dictionary of Keepa accounts keyed by identifier
    KEEPA_ACCOUNTS: Dict[str, KeepaAccount]
    # Default account to use if no specific identifier is matched
    DEFAULT_KEEPA_ACCOUNT: str

def load_settings() -> Settings:
    """Load settings from environment variables"""
    # Load variables from .env file
    load_dotenv(override=True)
    
    # Default values
    data_file = "post_info.json"
    update_existing = True
    
    # Load Keepa accounts
    keepa_accounts = {}
    
    # Define account identifiers to look for
    account_identifiers = ["Premium", "Meraxes", "Balerion", "Pro"]
    
    # Load each account if defined in .env
    for identifier in account_identifiers:
        username_key = f"KEEPA_{identifier.upper()}_USERNAME"
        password_key = f"KEEPA_{identifier.upper()}_PASSWORD"
        
        username = os.getenv(username_key)
        password = os.getenv(password_key)
        
        if username and password:
            keepa_accounts[identifier] = KeepaAccount(username=username, password=password)
    
    # Set default account
    default_account = os.getenv("DEFAULT_KEEPA_ACCOUNT", "Premium")
    
    settings = Settings(
        TELEGRAM_BOT_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        SOURCE_CHAT_ID=os.getenv("SOURCE_CHAT_ID", ""),
        DESTINATION_CHAT_ID=os.getenv("DESTINATION_CHAT_ID", ""),
        ADMIN_ID=os.getenv("ADMIN_ID", ""),
        UPDATE_EXISTING_TRACKING=os.getenv("UPDATE_EXISTING_TRACKING", update_existing),
        DATA_FILE=os.getenv("DATA_FILE", data_file),
        KEEPA_ACCOUNTS=keepa_accounts,
        DEFAULT_KEEPA_ACCOUNT=default_account
    )
    
    return settings