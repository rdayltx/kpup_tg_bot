import datetime
import asyncio
import time
import random
import os
import json
from utils.text_parser import extract_asin_from_text, extract_source_from_text
from data.data_manager import load_post_info, save_post_info
from utils.logger import get_logger
from telegram.error import BadRequest, TelegramError

logger = get_logger(__name__)

async def retrieve_missing_products(bot, source_chat_id, post_info):
    """
    Recuperar posts de produtos que podem estar faltando no post_info.json
    usando uma abordagem de varredura ampla
    
    Args:
        bot: Instância do Bot do Telegram
        source_chat_id: ID do chat de origem
        post_info: Dicionário atual de post_info
        
    Returns:
        dict: Dicionário post_info atualizado
    """
    logger.info("Iniciando recuperação completa de publicações ausentes...")
    
    # Converter source_chat_id para inteiro para comparações corretas
    try:
        source_chat_id_int = int(source_chat_id)
    except ValueError:
        logger.error(f"ID de chat inválido: {source_chat_id}")
        return post_info
    
    # Encontrar o ID de mensagem mais recente que conhecemos
    try:
        existing_ids = [int(msg_id) for msg_id in post_info.keys() if msg_id.isdigit()]
        latest_msg_id = max(existing_ids) if existing_ids else 0
        lowest_msg_id = min(existing_ids) if existing_ids else 0
    except (ValueError, StopIteration):
        logger.warning("Não foi possível determinar o ID da última mensagem, usando 0")
        latest_msg_id = 0
        lowest_msg_id = 0
        
    logger.info(f"ID da última mensagem rastreada: {latest_msg_id}")
    logger.info(f"ID da mensagem mais antiga rastreada: {lowest_msg_id}")
    
    # Preparar a recuperação
    new_posts = {}
    added_count = 0
    posts_examined = 0
    asin_posts_found = 0
    
    # Limites de processamento
    max_messages_per_run = 200  # Limite total de mensagens a verificar
    
    # Rastrear IDs já verificados para não repetir
    checked_ids = set(existing_ids)
    
    # Verificar se já temos um arquivo de progresso
    progress_file = "recovery_progress.json"
    try:
        if os.path.exists(progress_file):
            with open(progress_file, "r") as f:
                recovery_data = json.load(f)
                
            # Carregar progresso anterior
            if "checked_ids" in recovery_data:
                for id_str in recovery_data["checked_ids"]:
                    checked_ids.add(int(id_str))
                logger.info(f"Carregado progresso anterior: {len(checked_ids)} IDs já verificados")
    except Exception as e:
        logger.warning(f"Não foi possível carregar progresso anterior: {e}")
    
    # Criar lista de IDs a verificar em ordem estratégica
    try:
        # Primeiro: começar a partir do último ID conhecido e ir para cima
        upper_range = range(latest_msg_id + 1, latest_msg_id + 500)
        
        # Segundo: verificar para baixo a partir do último ID
        # Usamos uma faixa limitada para evitar processar mensagens muito antigas
        lower_range = range(latest_msg_id - 1, max(0, latest_msg_id - 1000), -1)
        
        # Terceiro: verificar lacunas entre os IDs registrados
        # Criar uma lista dos IDs que já temos, ordenados
        existing_ids.sort()
        gaps = []
        
        # Identificar lacunas grandes entre IDs consecutivos
        for i in range(len(existing_ids) - 1):
            current = existing_ids[i]
            next_id = existing_ids[i + 1]
            
            if next_id - current > 5:  # Se houver uma lacuna de mais de 5 IDs
                # Adicionar alguns IDs dessa lacuna
                gap_start = current + 1
                gap_end = next_id
                sample_size = min(20, gap_end - gap_start)  # No máximo 20 amostras por lacuna
                
                # Selecionar amostras distribuídas pela lacuna
                if sample_size > 0:
                    step = (gap_end - gap_start) // sample_size
                    if step < 1:
                        step = 1
                    gap_samples = range(gap_start, gap_end, step)
                    gaps.extend(gap_samples)
        
        # Combinar todas as faixas
        all_ids = list(upper_range) + list(lower_range) + gaps
        
        # Remover IDs já verificados
        ids_to_check = [msg_id for msg_id in all_ids if msg_id not in checked_ids]
        
        # Limitar ao máximo permitido
        ids_to_check = ids_to_check[:max_messages_per_run]
        
        logger.info(f"Preparados {len(ids_to_check)} IDs para verificação")
        
        # Dividir os IDs em lotes para processamento mais eficiente
        batch_size = 10
        batches = [ids_to_check[i:i + batch_size] for i in range(0, len(ids_to_check), batch_size)]
        
        # Processar cada lote
        for batch_num, batch in enumerate(batches, 1):
            if added_count >= 30:
                logger.info(f"Atingido limite de 30 novos posts, pausando recuperação")
                break
                
            logger.info(f"Processando lote {batch_num}/{len(batches)} ({len(batch)} IDs)")
            
            # Lista para armazenar mensagens obtidas neste lote
            batch_messages = []
            
            # Tentar obter cada mensagem deste lote
            for msg_id in batch:
                try:
                    # Marcar como verificado independentemente do resultado
                    checked_ids.add(msg_id)
                    
                    # Tentar recuperar a mensagem
                    message = await bot.forward_message(
                        chat_id=source_chat_id_int,
                        from_chat_id=source_chat_id_int,
                        message_id=msg_id,
                        disable_notification=True
                    )
                    
                    # Adicionar à lista de mensagens do lote
                    batch_messages.append((msg_id, message))
                    posts_examined += 1
                    
                except Exception as e:
                    # Mensagem não encontrada ou outro erro
                    pass
                
                # Pausa breve entre requisições
                await asyncio.sleep(0.2)
            
            # Processar mensagens recuperadas neste lote
            for msg_id, message in batch_messages:
                msg_id_str = str(msg_id)
                
                try:
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
                        
                        # Salvar incrementalmente
                        if added_count % 5 == 0:
                            combined = {**post_info, **new_posts}
                            save_post_info(combined)
                            logger.info(f"Checkpoint: Salvos {added_count} posts até agora")
                except Exception as e:
                    logger.warning(f"Erro ao processar mensagem {msg_id}: {e}")
            
            # Salvar o progresso da verificação regularmente
            try:
                progress_data = {
                    "last_run": datetime.datetime.now().isoformat(),
                    "checked_ids": list(map(str, checked_ids)),
                    "posts_found": added_count
                }
                
                with open(progress_file, "w") as f:
                    json.dump(progress_data, f)
            except Exception as e:
                logger.warning(f"Não foi possível salvar progresso: {e}")
            
            # Pausa entre lotes
            await asyncio.sleep(1)
        
        # Finalizar processamento
        if new_posts:
            # Adicionar todos os novos posts ao post_info
            post_info.update(new_posts)
            save_post_info(post_info)
            logger.info(f"Adicionados {added_count} posts de produtos ausentes ao rastreamento (verificados {posts_examined} posts)")
        else:
            logger.info(f"Nenhum post novo adicionado (verificados {posts_examined} posts)")
        
        return post_info
        
    except Exception as e:
        logger.error(f"Erro durante o processo de recuperação: {e}")
        
        # Salvar qualquer progresso feito até agora
        if new_posts:
            post_info.update(new_posts)
            save_post_info(post_info)
            logger.info(f"Salvos {len(new_posts)} posts encontrados antes do erro")
        
        return post_info

# Função especial para recuperação intensiva
async def perform_intensive_recovery(bot, source_chat_id, admin_id=None):
    """
    Realizar uma recuperação intensiva do histórico, por faixas de IDs
    
    Args:
        bot: Instância do Bot do Telegram
        source_chat_id: ID do chat de origem
        admin_id: ID do administrador para notificações
    """
    logger.info("Iniciando recuperação intensiva de mensagens")
    
    try:
        source_chat_id_int = int(source_chat_id)
    except ValueError:
        logger.error(f"ID de chat inválido: {source_chat_id}")
        return
    
    # Carregar dados atuais
    post_info = load_post_info()
    existing_ids = set(int(msg_id) for msg_id in post_info.keys() if msg_id.isdigit())
    
    # Criar faixas de IDs para verificação completa
    ranges_to_check = [
        (1, 300),         # Primeiras mensagens
        (300, 600),       # Faixa 300-600
        (600, 900),       # Faixa 600-900
        (900, 1200),      # Faixa 900-1200
        (1200, 1500),     # Faixa 1200-1500
        (1500, 1800),     # Faixa 1500-1800
        (1800, 2000)      # Faixa 1800-2000
    ]
    
    # Arquivo de progresso específico para recuperação intensiva
    progress_file = "intensive_recovery_progress.json"
    completed_ranges = []
    
    # Carregar progresso anterior se existir
    try:
        if os.path.exists(progress_file):
            with open(progress_file, "r") as f:
                progress_data = json.load(f)
                completed_ranges = progress_data.get("completed_ranges", [])
                
            logger.info(f"Carregado progresso anterior: {len(completed_ranges)} faixas já verificadas")
    except Exception as e:
        logger.warning(f"Não foi possível carregar progresso anterior: {e}")
    
    # Notificar o administrador sobre o início da recuperação
    if admin_id:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"🔄 Iniciando recuperação intensiva do histórico.\nVerificando {len(ranges_to_check)} faixas de IDs."
            )
        except Exception:
            pass
    
    # Processar cada faixa
    total_found = 0
    for i, (start_id, end_id) in enumerate(ranges_to_check):
        # Pular faixas já verificadas
        range_key = f"{start_id}-{end_id}"
        if range_key in completed_ranges:
            logger.info(f"Pulando faixa {range_key} (já verificada)")
            continue
        
        logger.info(f"Processando faixa {i+1}/{len(ranges_to_check)}: {start_id} a {end_id}")
        
        # Notificar o administrador sobre a faixa atual
        if admin_id:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"🔍 Verificando faixa {i+1}/{len(ranges_to_check)}: {start_id} a {end_id}"
                )
            except Exception:
                pass
        
        # Contar novos posts nesta faixa
        new_in_range = 0
        
        # Processar IDs em pequenos lotes
        batch_size = 10
        for batch_start in range(start_id, end_id, batch_size):
            batch_end = min(batch_start + batch_size, end_id)
            batch = list(range(batch_start, batch_end))
            
            # Filtrar IDs já conhecidos
            batch = [msg_id for msg_id in batch if msg_id not in existing_ids]
            
            # Se não há IDs novos para verificar neste lote, pular
            if not batch:
                continue
                
            # Lista para armazenar mensagens obtidas neste lote
            batch_messages = []
            
            # Tentar obter cada mensagem deste lote
            for msg_id in batch:
                try:
                    # Tentar recuperar a mensagem
                    message = await bot.forward_message(
                        chat_id=source_chat_id_int,
                        from_chat_id=source_chat_id_int,
                        message_id=msg_id,
                        disable_notification=True
                    )
                    
                    # Adicionar à lista de mensagens do lote
                    batch_messages.append((msg_id, message))
                    
                except Exception:
                    # Mensagem não encontrada ou outro erro
                    pass
                
                # Pausa breve entre requisições
                await asyncio.sleep(0.2)
            
            # Processar mensagens recuperadas neste lote
            for msg_id, message in batch_messages:
                msg_id_str = str(msg_id)
                
                try:
                    # Extrair texto da mensagem
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
                        
                        # Adicionar ao post_info
                        post_info[msg_id_str] = {
                            "asin": asin,
                            "source": source,
                            "timestamp": timestamp
                        }
                        existing_ids.add(msg_id)
                        total_found += 1
                        new_in_range += 1
                        
                        # Salvar incrementalmente
                        if total_found % 10 == 0:
                            save_post_info(post_info)
                            logger.info(f"Checkpoint: Salvos {total_found} posts no total")
                except Exception as e:
                    logger.warning(f"Erro ao processar mensagem {msg_id}: {e}")
            
            # Pausa entre lotes
            await asyncio.sleep(1)
        
        # Marcar esta faixa como concluída
        completed_ranges.append(range_key)
        
        # Atualizar o arquivo de progresso
        try:
            progress_data = {
                "last_run": datetime.datetime.now().isoformat(),
                "completed_ranges": completed_ranges,
                "total_found": total_found
            }
            
            with open(progress_file, "w") as f:
                json.dump(progress_data, f)
        except Exception as e:
            logger.warning(f"Não foi possível salvar progresso: {e}")
        
        # Salvar após cada faixa
        save_post_info(post_info)
        logger.info(f"Faixa {start_id}-{end_id} concluída: {new_in_range} novos posts (total: {total_found})")
        
        # Notificar o administrador sobre o progresso
        if admin_id:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"✅ Faixa {start_id}-{end_id} concluída: {new_in_range} novos posts\nTotal acumulado: {total_found} posts"
                )
            except Exception:
                pass
        
        # Pausa entre faixas para evitar rate limiting
        await asyncio.sleep(3)
    
    # Notificar conclusão da recuperação intensiva
    logger.info(f"Recuperação intensiva concluída. Total de posts encontrados: {total_found}")
    
    if admin_id:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"✅ Recuperação intensiva concluída!\nTotal de posts encontrados: {total_found}"
            )
        except Exception:
            pass
    
    return total_found

# Adicionar comando para o admin para iniciar recuperação intensiva
async def start_intensive_recovery_command(update, context):
    """
    Comando para iniciar o processo de recuperação intensiva
    """
    from config.settings import load_settings
    settings = load_settings()
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Este comando é exclusivo para administradores.")
        return
    
    await update.message.reply_text("🔄 Iniciando processo de recuperação intensiva do histórico. Isso pode levar tempo...")
    
    try:
        total_found = await perform_intensive_recovery(
            context.bot,
            settings.SOURCE_CHAT_ID,
            settings.ADMIN_ID
        )
        
        await update.message.reply_text(f"✅ Recuperação intensiva concluída! Foram encontrados {total_found} posts no total.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro durante a recuperação intensiva: {str(e)}")