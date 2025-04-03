import datetime
from utils.text_parser import extract_asin_from_text, extract_source_from_text
from utils.logger import get_logger

logger = get_logger(__name__)

async def retrieve_missing_products(bot, source_chat_id, post_info):
    """
    Recuperar posts de produtos que podem estar faltando no post_info.json
    
    Args:
        bot: Instância do Bot do Telegram
        source_chat_id: ID do chat de origem
        post_info: Dicionário atual de post_info
        
    Returns:
        dict: Dicionário post_info atualizado
    """
    logger.info("Tentando recuperar posts de produtos ausentes...")
    
    if not post_info:
        logger.warning("Post info está vazio, não é possível determinar o último ID de post")
        return post_info
    
    # Encontrar o ID de mensagem mais recente em post_info
    try:
        latest_msg_id = max(int(msg_id) for msg_id in post_info.keys())
    except ValueError:
        logger.warning("Não foi possível determinar o ID da última mensagem, usando 0")
        latest_msg_id = 0
        
    logger.info(f"ID da última mensagem rastreada: {latest_msg_id}")
    
    # Obter mensagens recentes do chat de origem
    try:
        # Obter apenas um número razoável de mensagens recentes para evitar limites de taxa
        messages = await bot.get_updates(limit=100, offset=-100)
        added_count = 0
        
        # Filtrar mensagens do chat de origem
        source_messages = []
        for update in messages:
            message = update.message or update.channel_post
            if message and str(message.chat_id) == source_chat_id:
                source_messages.append(message)
        
        # Processar cada mensagem
        for message in source_messages:
            # Pular se o ID da mensagem já estiver em post_info
            if str(message.message_id) in post_info:
                continue
                
            # Pular se o ID da mensagem for menor que latest_msg_id (já processado)
            if int(message.message_id) <= latest_msg_id:
                continue
                
            message_text = message.text or message.caption or ""
            
            # Extrair ASIN e fonte
            asin = extract_asin_from_text(message_text)
            
            if asin:
                source = extract_source_from_text(message_text)
                logger.info(f"Encontrado post ausente com ASIN: {asin}, Fonte: {source}, ID: {message.message_id}")
                
                # Adicionar ao post_info
                post_info[str(message.message_id)] = {
                    "asin": asin,
                    "source": source,
                    "timestamp": datetime.datetime.now().isoformat()
                }
                added_count += 1
        
        logger.info(f"Adicionados {added_count} posts de produtos ausentes ao rastreamento")
        return post_info
        
    except Exception as e:
        logger.error(f"Erro ao recuperar produtos ausentes: {str(e)}")
        return post_info