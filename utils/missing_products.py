import datetime
from utils.text_parser import extract_asin_from_text, extract_source_from_text
from data.data_manager import load_post_info, save_post_info
from utils.logger import get_logger
import json
from telegram.error import BadRequest, TelegramError
import time
import asyncio
import random

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
        start_id = max(1, latest_msg_id - 300)  # Verificar até 300 IDs para trás para cobrir 30+ publicações
        end_id = latest_msg_id + 50
        
        # Se tivermos menos de 20 posts registrados, ampliar a busca para trás
        if len(post_info) < 20:
            start_id = max(1, latest_msg_id - 500)
            logger.info(f"Poucos posts registrados ({len(post_info)}), ampliando busca para trás")
        
        logger.info(f"Verificando mensagens no intervalo de IDs: {start_id} a {end_id}")
        
        # Lista para armazenar progressivamente os novos posts encontrados
        new_posts = {}
        
        # Definir ID inicial com base no último ID conhecido
        # e um parâmetro de offset maior para pular mensagens já processadas
        current_msg_id = max(latest_msg_id + 1, latest_msg_id - 300)
        
        # Contador para publicações examinadas (independente se têm ASIN ou não)
        posts_examined = 0
        # Contador para publicações com ASIN encontradas
        asin_posts_found = 0
        
        # Método direto: Procurar mensagens no intervalo especificado com um limite
        # para não sobrecarregar o Telegram
        max_fwd_per_batch = 10  # Máximo de mensagens encaminhadas por lote
        fwd_batches = 5         # Número de lotes a processar
        
        # Limitar total de encaminhamentos
        max_total_forwards = 30
        total_forwards = 0
        
        # Controle de IDs testados para evitar duplicações
        tested_ids = set()
        
        # Estratégia 1: Procurar mensagens acima do último ID conhecido
        # (mensagens mais recentes que talvez não tenham sido registradas)
        logger.info(f"Verificando mensagens mais recentes (acima de ID {latest_msg_id})")
        
        current_msg_id = latest_msg_id + 1
        msgs_to_check = []
        
        for batch in range(fwd_batches):
            if total_forwards >= max_total_forwards:
                break
                
            batch_forwards = 0
            
            # Verificar uma faixa de IDs em sequência crescente
            for msg_id in range(current_msg_id, current_msg_id + max_fwd_per_batch):
                if str(msg_id) in post_info or msg_id in tested_ids:
                    tested_ids.add(msg_id)
                    continue
                
                if batch_forwards >= max_fwd_per_batch or total_forwards >= max_total_forwards:
                    break
                
                try:
                    # Tentar obter a mensagem
                    message = await bot.get_chat(
                        chat_id=source_chat_id_int
                    )
                    
                    # Se conseguimos obter o chat, tentar obter a mensagem específica
                    try:
                        message = await bot.forward_message(
                            chat_id=source_chat_id_int,
                            from_chat_id=source_chat_id_int,
                            message_id=msg_id,
                            disable_notification=True
                        )
                        
                        # Adicionar à lista para processamento
                        msgs_to_check.append((msg_id, message))
                        batch_forwards += 1
                        total_forwards += 1
                        
                        # Esperar um pouco para não sobrecarregar a API
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        # A mensagem específica não existe, pulamos
                        tested_ids.add(msg_id)
                        pass
                        
                except Exception as chat_err:
                    logger.warning(f"Erro ao acessar o chat: {str(chat_err)}")
                    # Se não pudermos acessar o chat, não adianta continuar
                    break
            
            # Atualizar o ID de início para o próximo lote
            current_msg_id += max_fwd_per_batch
            
            # Processar o lote atual
            if msgs_to_check:
                await process_message_batch(msgs_to_check, post_info, new_posts, posts_examined, asin_posts_found, added_count)
                
                # Limpar para o próximo lote
                msgs_to_check = []
                
                # Aguardar entre lotes para evitar rate limit
                if batch < fwd_batches - 1:
                    await asyncio.sleep(1)
        
        # Estratégia 2: Procurar mensagens abaixo do último ID conhecido
        # (mensagens antigas que podem ter sido perdidas)
        logger.info(f"Verificando mensagens mais antigas (abaixo de ID {latest_msg_id})")
        
        # Reset contadores para a segunda estratégia
        current_msg_id = latest_msg_id - 1
        
        for batch in range(fwd_batches):
            if total_forwards >= max_total_forwards:
                break
                
            batch_forwards = 0
            
            # Verificar uma faixa de IDs em sequência decrescente
            for i in range(max_fwd_per_batch):
                msg_id = current_msg_id - i
                
                if msg_id <= 0 or str(msg_id) in post_info or msg_id in tested_ids:
                    tested_ids.add(msg_id)
                    continue
                
                if batch_forwards >= max_fwd_per_batch or total_forwards >= max_total_forwards:
                    break
                
                try:
                    # Tentar encaminhar a mensagem
                    message = await bot.forward_message(
                        chat_id=source_chat_id_int,
                        from_chat_id=source_chat_id_int,
                        message_id=msg_id,
                        disable_notification=True
                    )
                    
                    # Adicionar à lista para processamento
                    msgs_to_check.append((msg_id, message))
                    batch_forwards += 1
                    total_forwards += 1
                    
                    # Esperar um pouco para não sobrecarregar a API
                    await asyncio.sleep(0.5)
                except Exception:
                    # A mensagem específica não existe, pulamos
                    tested_ids.add(msg_id)
                    pass
            
            # Atualizar o ID de início para o próximo lote
            current_msg_id -= max_fwd_per_batch
            
            # Processar o lote atual
            if msgs_to_check:
                await process_message_batch(msgs_to_check, post_info, new_posts, posts_examined, asin_posts_found, added_count)
                
                # Limpar para o próximo lote
                msgs_to_check = []
                
                # Aguardar entre lotes para evitar rate limit
                if batch < fwd_batches - 1:
                    await asyncio.sleep(1)
        
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

async def process_message_batch(messages, post_info, new_posts, posts_examined, asin_posts_found, added_count):
    """
    Processar um lote de mensagens para extrair posts com ASIN.
    
    Args:
        messages: Lista de tuplas (msg_id, message)
        post_info: Dicionário de posts já registrados
        new_posts: Dicionário para armazenar novos posts encontrados
        posts_examined: Contador de posts examinados
        asin_posts_found: Contador de posts com ASIN encontrados
        added_count: Contador de posts adicionados
    """
    logger.info(f"Processando lote de {len(messages)} mensagens obtidas para verificação")
    
    for msg_id, message in messages:
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
            
    # Retornar os contadores atualizados
    return posts_examined, asin_posts_found, added_count