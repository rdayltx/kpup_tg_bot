import datetime
from utils.text_parser import extract_asin_from_text, extract_source_from_text
from data.data_manager import load_post_info, save_post_info
from utils.logger import get_logger
import json

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
    
    # Em vez de tentar obter mensagens anteriores, vamos verificar IDs específicos
    # ao redor do último ID conhecido (os 20 mais recentes)
    try:
        added_count = 0
        
        # Tentar IDs ao redor do último ID conhecido
        # Vamos tentar 20 IDs acima e 20 abaixo para cobrir possíveis lacunas
        start_id = max(1, latest_msg_id - 30)
        end_id = latest_msg_id + 30
        
        logger.info(f"Verificando mensagens no intervalo de IDs: {start_id} a {end_id}")
        
        for msg_id in range(start_id, end_id + 1):
            msg_id_str = str(msg_id)
            
            # Pular se o ID da mensagem já estiver em post_info
            if msg_id_str in post_info:
                continue
            
            try:
                # Tentar obter a mensagem específica
                message = await bot.forward_message(
                    chat_id=source_chat_id_int,
                    from_chat_id=source_chat_id_int,
                    message_id=msg_id,
                    disable_notification=True
                )
                
                # Se chegou aqui, conseguimos obter a mensagem
                # Agora processamos seu conteúdo
                message_text = message.text or message.caption or ""
                
                # Extrair ASIN e fonte
                asin = extract_asin_from_text(message_text)
                
                if asin:
                    source = extract_source_from_text(message_text)
                    logger.info(f"Encontrado post ausente com ASIN: {asin}, Fonte: {source}, ID: {message.message_id}")
                    
                    # Adicionar ao post_info
                    timestamp = datetime.datetime.now().isoformat()
                    if hasattr(message, 'date'):
                        if isinstance(message.date, datetime.datetime):
                            timestamp = message.date.isoformat()
                        else:
                            try:
                                timestamp = datetime.datetime.fromtimestamp(message.date).isoformat()
                            except:
                                pass
                    
                    post_info[msg_id_str] = {
                        "asin": asin,
                        "source": source,
                        "timestamp": timestamp
                    }
                    added_count += 1
            except Exception as msg_error:
                # Esta mensagem pode não existir ou não ser acessível
                # Simplesmente continuamos para a próxima
                pass
        # Salvar apenas uma vez no final se houver alterações
        if added_count > 0:
            save_post_info(post_info)
        
        logger.info(f"Adicionados {added_count} posts de produtos ausentes ao rastreamento")
        return post_info
        
    except Exception as e:
        logger.error(f"Erro ao recuperar produtos ausentes: {str(e)}")
        return post_info
    