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
    
    # Vamos verificar IDs específicos ao redor do último ID conhecido
    # e também um intervalo adicional para trás para preencher lacunas
    try:
        added_count = 0
        
        # Verificar 30 publicações anteriores para preencher lacunas + intervalo ao redor do último ID
        start_id = max(1, latest_msg_id - 100)  # Verificar até 100 IDs para trás para cobrir 30+ publicações
        end_id = latest_msg_id + 30
        
        logger.info(f"Verificando mensagens no intervalo de IDs: {start_id} a {end_id}")
        
        # Lista para armazenar progressivamente os novos posts encontrados
        new_posts = {}
        
        # Contador para publicações examinadas (independente se têm ASIN ou não)
        posts_examined = 0
        # Contador para publicações com ASIN encontradas
        asin_posts_found = 0
        
        for msg_id in range(start_id, end_id + 1):
            msg_id_str = str(msg_id)
            
            # Pular se o ID da mensagem já estiver em post_info
            if msg_id_str in post_info:
                continue
            
            try:
                # MODIFICADO: Em vez de encaminhar a mensagem, vamos obter a mensagem diretamente
                message = await bot.get_message(
                    chat_id=source_chat_id_int,
                    message_id=msg_id
                )
                
                # Se chegou aqui, conseguimos obter a mensagem
                # Incrementar contador de posts examinados
                posts_examined += 1
                
                # Agora processamos seu conteúdo
                message_text = message.text or message.caption or ""
                
                # Extrair ASIN e fonte
                asin = extract_asin_from_text(message_text)
                
                if asin:
                    asin_posts_found += 1
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
                    
                    # Adicionar aos novos posts
                    new_posts[msg_id_str] = {
                        "asin": asin,
                        "source": source,
                        "timestamp": timestamp
                    }
                    added_count += 1
                    
                    # Se já encontramos pelo menos 30 posts com ASIN, podemos parar a busca
                    # se estivermos analisando mensagens antigas (antes do último_msg_id - 30)
                    if asin_posts_found >= 30 and msg_id < (latest_msg_id - 30):
                        logger.info(f"Encontrados {asin_posts_found} posts com ASIN. Parando busca de mensagens mais antigas.")
                        break
                    
                    # A cada 5 posts encontrados, salvar para evitar perda de dados em caso de erro
                    if added_count % 5 == 0:
                        # Adicionar os novos posts ao post_info e salvar
                        combined_post_info = {**post_info, **new_posts}
                        save_post_info(combined_post_info)
                        logger.info(f"Checkpoint: Salvos {added_count} posts até agora")
            except Exception as msg_error:
                # Esta mensagem pode não existir ou não ser acessível
                logger.debug(f"Mensagem {msg_id} não acessível: {str(msg_error)}")
                # Simplesmente continuamos para a próxima
                pass
        
        # Adicionar todos os novos posts ao post_info
        post_info.update(new_posts)
        
        # Salvar apenas uma vez no final se houver alterações
        if added_count > 0:
            save_post_info(post_info)
            logger.info(f"Adicionados {added_count} posts de produtos ausentes ao rastreamento (verificados {posts_examined} posts)")
        else:
            logger.info(f"Nenhum post novo adicionado (verificados {posts_examined} posts)")
        
        return post_info
        
    except Exception as e:
        logger.error(f"Erro ao recuperar produtos ausentes: {str(e)}")
        
        # Salvar qualquer progresso feito até agora
        if new_posts:
            post_info.update(new_posts)
            save_post_info(post_info)
            logger.info(f"Salvos {len(new_posts)} posts encontrados antes do erro")
            
        return post_info