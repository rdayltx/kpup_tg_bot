import json
from datetime import datetime, timedelta
import os
from config.settings import load_settings

# Carregar configurações
settings = load_settings()

def load_post_info():
    """
    Carregar dados do arquivo JSON
    """
    try:
        with open(settings.DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_post_info(post_info):
    """
    Salvar dados no arquivo JSON
    """
    with open(settings.DATA_FILE, "w") as f:
        json.dump(post_info, f, indent=2)

def clean_old_entries(post_info):
    """
    Limpar entradas com mais de 2 dias
    """
    now = datetime.now()
    two_days_ago = now - timedelta(days=2)
    cleaned_info = {}
    
    for msg_id, data in post_info.items():
        timestamp = datetime.fromisoformat(data["timestamp"])
        if timestamp >= two_days_ago:
            cleaned_info[msg_id] = data
            
    return cleaned_info