import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config.settings import load_settings
from data.data_manager import load_post_info, save_post_info
from utils.text_parser import extract_asin_from_text, extract_source_from_text, extract_price_from_comment
from keepa.browser import initialize_driver
from keepa.api import login_to_keepa, update_keepa_product

from utils.logger import get_logger

logger = get_logger(__name__)
settings = load_settings()

def format_destination_message(asin, comment, source, price=None, action="update", success=True):
    """
    Formatar uma mensagem mais informativa para o canal de destino
    
    Args:
        asin (str): ASIN do produto
        comment (str): Comentário original do usuário
        source (str): Fonte do rastreamento
        price (str, opcional): Preço extraído
        action (str): Ação realizada (atualização/exclusão)
        success (bool): Se a ação foi bem-sucedida
        
    Returns:
        str: Mensagem formatada
    """
    # Criar um emoji de status
    status_emoji = "✅" if success else "❌"
    
    # Criar uma descrição da ação
    action_desc = ""
    if action == "update":
        action_desc = f"Atualização {status_emoji}"
        if price:
            action_desc += f" Definida para R$ {price}"
    elif action == "delete":
        action_desc = f"Rastreamento deletado {status_emoji}"
    
    # Formatar URL da Amazon
    amazon_url = f"https://www.amazon.com.br/dp/{asin}"
    
    # Criar URL do Keepa
    keepa_url = f"https://keepa.com/#!product/12-{asin}"
    
    # Formatar a mensagem
    message = (
        f"*{asin}* - {action_desc}\n"
        f"👤 Conta: *{source}*\n"
        f"🛒 [Amazon]({amazon_url}) | 📊 [Keepa]({keepa_url})\n"
        f"💬 Comentário: {comment}"
        
    )
    
    return message