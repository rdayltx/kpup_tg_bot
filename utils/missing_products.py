import datetime
from utils.text_parser import extract_asin_from_text, extract_source_from_text
from data.data_manager import load_post_info, save_post_info
from utils.logger import get_logger
import json
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TelegramError

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
        
        # Usar uma abordagem alternativa: obter mensagens do histórico
        # em vez de tentar obter uma por uma
        try:
            # Método 1: Tentar obter mensagens do histórico recente
            last_messages = await bot.get_chat_history(chat_id=source_chat_id_int, limit=200)
            
            # Processar as mensagens obtidas
            messages_by_id = {msg.message_id: msg for msg in last_messages}
            logger.info(f"Obtidas {len(messages_by_id)} mensagens do histórico recente")
            
            # Se não conseguimos obter mensagens suficientes, tentaremos o método 2 ou 3
            if len(messages_by_id) < 50:
                logger.warning("Poucas mensagens obtidas do histórico. Tentando método alternativo.")
                messages_by_id = {}
        except Exception as e:
            logger.warning(f"Não foi possível obter histórico de mensagens: {str(e)}. Tentando método alternativo.")
            messages_by_id = {}
        
        # Se o método 1 falhou, tentar o método 2: cópia de mensagem para chat privado
        temp_messages = {}
        if not messages_by_id:
            try:
                # Método 2: Tentar obter mensagens individualmente sem encaminhar
                # Usaremos copyMessage para um chat temporário com o bot (se um admin estiver configurado)
                from config.settings import load_settings
                settings = load_settings()
                
                if settings.ADMIN_ID:
                    admin_id = int(settings.ADMIN_ID)
                    logger.info(f"Tentando obter mensagens via copyMessage para o admin ({admin_id})")
                    
                    # Vamos tentar copiar algumas mensagens para o admin e depois deletar
                    # para visualização sem encaminhamento
                    for msg_id in range(latest_msg_id - 10, latest_msg_id + 5):
                        try:
                            # Copiar mensagem para o admin
                            copied_msg = await bot.copy_message(
                                chat_id=admin_id,
                                from_chat_id=source_chat_id_int,
                                message_id=msg_id,
                                disable_notification=True
                            )
                            
                            # Obter o conteúdo
                            temp_msg_text = copied_msg.text or copied_msg.caption or ""
                            
                            # Adicionar à lista temporária
                            temp_messages[msg_id] = temp_msg_text
                            
                            # Deletar a mensagem copiada para não incomodar o admin
                            await bot.delete_message(
                                chat_id=admin_id,
                                message_id=copied_msg.message_id
                            )
                        except Exception as copy_err:
                            logger.warning(f"Não foi possível copiar mensagem {msg_id}: {str(copy_err)}")
                            continue
                    
                    logger.info(f"Obtidas {len(temp_messages)} mensagens via copyMessage")
            except Exception as copy_err:
                logger.warning(f"Falha no método de cópia para admin: {str(copy_err)}")
        
        # Método 3: Se os métodos anteriores falharem, recorrer ao forward (menos ideal)
        # mas salvando as mensagens de forma silenciosa
        if not messages_by_id and not temp_messages:
            logger.warning("Recorrendo ao método de encaminhamento (último recurso)")
            
            # Aqui manteremos o encaminhamento como último recurso
            # mas adicionaremos lógica para evitar flood
            
            # Limitar a quantidade de mensagens para não inundar o chat
            max_forwards = 20
            for msg_id in range(latest_msg_id - max_forwards, latest_msg_id + 5):
                if str(msg_id) in post_info:
                    continue
                    
                try:
                    # Tentar encaminhar a mensagem silenciosamente para o bot
                    # Este é o último recurso e não é ideal
                    message = await bot.forward_message(
                        chat_id=bot.id,  # Encaminhar para o próprio bot
                        from_chat_id=source_chat_id_int,
                        message_id=msg_id,
                        disable_notification=True
                    )
                    
                    # Adicionar ao dict de mensagens
                    messages_by_id[msg_id] = message
                    
                    # Deletar a mensagem encaminhada
                    try:
                        await bot.delete_message(
                            chat_id=bot.id,
                            message_id=message.message_id
                        )
                    except:
                        pass
                except Exception as fwd_err:
                    logger.debug(f"Não foi possível encaminhar mensagem {msg_id}: {str(fwd_err)}")
                    continue
                    
                # Limitar a quantidade
                if len(messages_by_id) >= max_forwards:
                    break
        
        # Agora vamos processar as mensagens que obtivemos
        # através dos diferentes métodos
        msgs_to_check = []
        
        # Adicionar mensagens do método 1 (histórico completo)
        for msg_id in range(start_id, end_id + 1):
            if msg_id in messages_by_id:
                msgs_to_check.append((msg_id, messages_by_id[msg_id]))
                
        # Adicionar mensagens do método 2 (cópia temporária para admin)
        for msg_id, msg_text in temp_messages.items():
            # Criar um objeto simples com propriedades text e message_id
            class SimpleMessage:
                def __init__(self, message_id, text):
                    self.message_id = message_id
                    self.text = text
                    self.caption = None
            
            simple_msg = SimpleMessage(msg_id, msg_text)
            msgs_to_check.append((msg_id, simple_msg))
        
        # Se ainda não temos mensagens suficientes, fazer uma tentativa direta
        # de obtenção individual para os 30 posts mais recentes
        if len(msgs_to_check) < 30:
            for msg_id in range(latest_msg_id - 30, latest_msg_id + 5):
                if msg_id in [m[0] for m in msgs_to_check]:
                    continue
                    
                if str(msg_id) in post_info:
                    continue
                    
                try:
                    # Último recurso: Tentar encaminhar apenas uma vez
                    message = await bot.forward_message(
                        chat_id=source_chat_id_int, 
                        from_chat_id=source_chat_id_int,
                        message_id=msg_id,
                        disable_notification=True
                    )
                    
                    # Adicionar ao dict de mensagens a verificar
                    msgs_to_check.append((msg_id, message))
                except Exception:
                    continue
        
        # Agora processar as mensagens que conseguimos obter
        logger.info(f"Processando {len(msgs_to_check)} mensagens obtidas para verificação")
        
        for msg_id, message in msgs_to_check:
            msg_id_str = str(msg_id)
            
            # Pular se o ID da mensagem já estiver em post_info
            if msg_id_str in post_info:
                continue
                
            try:
                # Incrementar contador de posts examinados
                posts_examined += 1
                
                # Extrair texto da mensagem
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
                    
                    # A cada 5 posts encontrados, salvar para evitar perda de dados em caso de erro
                    if added_count % 5 == 0:
                        # Adicionar os novos posts ao post_info e salvar
                        combined_post_info = {**post_info, **new_posts}
                        save_post_info(combined_post_info)
                        logger.info(f"Checkpoint: Salvos {added_count} posts até agora")
            except Exception as msg_error:
                logger.debug(f"Erro ao processar mensagem {msg_id}: {str(msg_error)}")
                continue
        
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
        if 'new_posts' in locals() and new_posts:
            post_info.update(new_posts)
            save_post_info(post_info)
            logger.info(f"Salvos {len(new_posts)} posts encontrados antes do erro")
            
        return post_info