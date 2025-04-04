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
    
    # Converter source_chat_id para inteiro para comparações corretas
    try:
        source_chat_id_int = int(source_chat_id)
    except ValueError:
        logger.error(f"ID de chat inválido: {source_chat_id}")
        return post_info
    
    # Encontrar o ID de mensagem mais recente em post_info
    try:
        latest_msg_id = max(int(msg_id) for msg_id in post_info.keys() if msg_id.isdigit())
    except (ValueError, StopIteration):
        logger.warning("Não foi possível determinar o ID da última mensagem, usando 0")
        latest_msg_id = 0
        
    logger.info(f"ID da última mensagem rastreada: {latest_msg_id}")
    
    # Obter mensagens recentes do chat de origem
    try:
        # Ao invés de get_updates, seria melhor usar get_history ou similar
        # Como alternativa, podemos usar get_chat_history ou get_messages
        # Este é um exemplo usando uma abordagem alternativa
        
        added_count = 0
        
        # Exemplo de abordagem alternativa (depende da biblioteca específica do Telegram usada)
        # Isso é apenas um esboço - o método real dependerá da API exata que você está usando
        try:
            # Tentar obter historico de chat se disponível
            messages = await bot.get_chat_history(chat_id=source_chat_id_int, limit=100)
        except AttributeError:
            # Fallback para o método atual se get_chat_history não estiver disponível
            updates = await bot.get_updates(limit=100)
            messages = []
            for update in updates:
                message = update.message or update.channel_post
                if message and message.chat_id == source_chat_id_int:
                    messages.append(message)
        
        # Processar cada mensagem
        for message in messages:
            msg_id_str = str(message.message_id)
            
            # Pular se o ID da mensagem já estiver em post_info
            if msg_id_str in post_info:
                continue
                
            # Pular se o ID da mensagem for menor que latest_msg_id (já processado)
            if message.message_id <= latest_msg_id:
                continue
                
            message_text = message.text or message.caption or ""
            
            # Extrair ASIN e fonte
            asin = extract_asin_from_text(message_text)
            
            if asin:
                source = extract_source_from_text(message_text)
                logger.info(f"Encontrado post ausente com ASIN: {asin}, Fonte: {source}, ID: {message.message_id}")
                
                # Adicionar ao post_info com o timestamp real da mensagem
                timestamp = message.date.isoformat() if hasattr(message, 'date') else datetime.datetime.now().isoformat()
                
                post_info[msg_id_str] = {
                    "asin": asin,
                    "source": source,
                    "timestamp": timestamp
                }
                added_count += 1
        
        logger.info(f"Adicionados {added_count} posts de produtos ausentes ao rastreamento")
        return post_info
        
    except Exception as e:
        logger.error(f"Erro ao recuperar produtos ausentes: {str(e)}")
        return post_info