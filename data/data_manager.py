import json
from datetime import datetime, timedelta
import os
from config.settings import load_settings

# Load settings
settings = load_settings()

def load_post_info():
    """
    Load data from the JSON file
    """
    try:
        with open(settings.DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_post_info(post_info):
    """
    Save data to the JSON file
    """
    with open(settings.DATA_FILE, "w") as f:
        json.dump(post_info, f, indent=2)

def clean_old_entries(post_info):
    """
    Clean entries older than 2 days
    """
    now = datetime.now()
    two_days_ago = now - timedelta(days=2)
    cleaned_info = {}
    
    for msg_id, data in post_info.items():
        timestamp = datetime.fromisoformat(data["timestamp"])
        if timestamp >= two_days_ago:
            cleaned_info[msg_id] = data
            
    return cleaned_info