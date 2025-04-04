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

def format_destination_message(asin, comment, source, price=None, action="update", 
                              success=True, user_name="Desconhecido", product_title=None):
    """
    Formatar uma mensagem mais informativa para o canal de destino
    
    Args:
        asin (str): ASIN do produto
        comment (str): Comentário original do usuário
        source (str): Fonte do rastreamento
        price (str, opcional): Preço extraído
        action (str): Ação realizada (atualização/exclusão)
        success (bool): Se a ação foi bem-sucedida
        user_name (str): Nome do usuário que fez a ação
        product_title (str, opcional): Título do produto, se disponível
        
    Returns:
        str: Mensagem formatada
    """
    # Criar um emoji de status
    status_emoji = "✅" if success else "❌"
    
    # Criar uma descrição da ação
    if action == "update":
        action_desc = f"{status_emoji} Atualização"
        if price:
            action_desc += f" para R$ {price}"
    elif action == "delete":
        action_desc = f"{status_emoji} Rastreamento deletado"
    else:
        action_desc = f"{status_emoji} Ação: {action}"
    
    # Formatar URL da Amazon
    amazon_url = f"https://www.amazon.com.br/dp/{asin}"
    
    # Criar URL do Keepa
    keepa_url = f"https://keepa.com/#!product/12-{asin}"
    
    # Formatar título do produto
    title_part = ""
    if product_title:
        # Limitar o tamanho do título para 100 caracteres para não ficar muito grande
        if len(product_title) > 100:
            product_title = product_title[:97] + "..."
        title_part = f"*{product_title}*\n\n"
    
    # Formatar a mensagem completa
    message = (
        f"{title_part}"
        f"{action_desc} para *{asin}*\n"
        f"Por: *{user_name}*\n"
        f"Conta: *{source}*\n"
        f"[Amazon]({amazon_url}) | [Keepa]({keepa_url})\n"
        f"💬 _Comentário: {comment}_"
    )
    
    return message