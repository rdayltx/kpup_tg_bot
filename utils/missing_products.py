import datetime
import asyncio
import os
import json
from utils.text_parser import extract_asin_from_text, extract_source_from_text
from data.data_manager import load_post_info, save_post_info
from utils.logger import get_logger
from config.settings import load_settings
import time
import random

# Importar Pyrogram
from pyrogram import Client
from pyrogram.errors import FloodWait, MessageIdInvalid, MessageNotModified, PeerIdInvalid

logger = get_logger(__name__)

# Carregar configurações
settings = load_settings()

# Função para recuperar mensagens usando string de sessão Pyrogram
async def recover_with_pyrogram_string(session_string, chat_id, post_info):
    """
    Recuperar mensagens usando uma conta de usuário via string de sessão Pyrogram
    
    Args:
        session_string: String de sessão Pyrogram
        chat_id: ID do chat para recuperar mensagens
        post_info: Dicionário atual de post_info
        
    Returns:
        dict: Dicionário post_info atualizado
    """
    logger.info(f"Iniciando recuperação com Pyrogram usando string de sessão")
    
    if not session_string:
        logger.error("String de sessão não fornecida")
        return post_info
    
    # Criar cliente Pyrogram usando string de sessão
    app = Client("memory_session", session_string=session_string, in_memory=True)
    
    # Dicionário para armazenar novos posts
    new_posts = {}
    added_count = 0
    processed_count = 0
    
    try:
        # Iniciar o cliente
        await app.start()
        logger.info("Cliente Pyrogram iniciado com sucesso")

        # Buscar o chat pelo nome em vez de tentar vários formatos de ID
        chat = None
        chat_id_to_use = None

        try:
            # Primeira tentativa: buscar o chat pelo título exato
            target_chat_name = "chat do keepa do pobre"
            
            logger.info(f"Buscando chat pelo nome: '{target_chat_name}'")
            
            found_chat = False
            async for dialog in app.get_dialogs():
                if dialog.chat.title and dialog.chat.title == target_chat_name:
                    logger.info(f"Chat encontrado pelo nome exato: {dialog.chat.title} (ID: {dialog.chat.id})")
                    chat = dialog.chat
                    chat_id_to_use = dialog.chat.id
                    found_chat = True
                    break
            
            # Se não encontrar pelo nome exato, procurar por substring
            if not found_chat:
                logger.info("Chat não encontrado pelo nome exato, procurando por substring...")
                async for dialog in app.get_dialogs():
                    if dialog.chat.title and "keepa do pobre" in dialog.chat.title.lower():
                        logger.info(f"Chat encontrado por substring: {dialog.chat.title} (ID: {dialog.chat.id})")
                        chat = dialog.chat
                        chat_id_to_use = dialog.chat.id
                        found_chat = True
                        break
            
            # Se ainda não encontrou, procurar pelo ID exato
            if not found_chat:
                logger.info("Tentando pelo ID específico -1002563291570...")
                try:
                    hardcoded_id = -1002563291570
                    dialog_chat = await app.get_chat(hardcoded_id)
                    logger.info(f"Chat encontrado pelo ID hardcoded: {dialog_chat.title} (ID: {dialog_chat.id})")
                    chat = dialog_chat
                    chat_id_to_use = hardcoded_id
                    found_chat = True
                except Exception as e:
                    logger.warning(f"Não foi possível acessar o chat pelo ID hardcoded: {str(e)}")
            
            # Se ainda não encontrou, procurar em todos os diálogos pelo ID que contém "2563291570"
            if not found_chat:
                logger.info("Procurando por ID que contenha '2563291570' em todos os diálogos...")
                async for dialog in app.get_dialogs():
                    if str(dialog.chat.id).find("2563291570") >= 0:
                        logger.info(f"Chat encontrado pelo ID parcial: {dialog.chat.title} (ID: {dialog.chat.id})")
                        chat = dialog.chat
                        chat_id_to_use = dialog.chat.id
                        found_chat = True
                        break
            
            # Se ainda não encontrou, mas temos mensagens para continuar
            if not found_chat and len(post_info) > 0:
                logger.warning("Não foi possível acessar o chat por nome ou ID, mas temos mensagens existentes para continuar.")
                chat_id_to_use = -1002563291570
            
            # Neste ponto, vamos tentar obter mensagens do chat
            if chat_id_to_use:
                logger.info(f"Usando ID final para histórico: {chat_id_to_use}")
                
                # ... resto do código para obter mensagens ...
            else:
                logger.error("Não foi possível identificar o chat por nenhum método.")
                return post_info

        except Exception as e:
            logger.error(f"Erro ao buscar chat: {str(e)}")
            # Se tudo falhar mas temos um ID conhecido, tentar usar mesmo assim
            chat_id_to_use = -1002563291570
            logger.info(f"Usando ID hardcoded como fallback: {chat_id_to_use}")
        
        # Neste ponto, vamos tentar obter mensagens do chat independentemente de termos conseguido obter os detalhes
        chat_id = chat_id_to_use
        
        logger.info(f"Usando ID final: {chat_id}")
        
        try:
            # Tentar acessar mensagens diretamente, mesmo sem ter conseguido get_chat
            logger.info("Tentando acessar o histórico do chat diretamente...")
            
            # Encontrar o último ID conhecido
            try:
                existing_ids = [int(msg_id) for msg_id in post_info.keys() if msg_id.isdigit()]
                latest_msg_id = max(existing_ids) if existing_ids else 0
                oldest_msg_id = min(existing_ids) if existing_ids else 0
                
                # Conjunto de IDs já processados para evitar duplicações
                processed_ids = set(existing_ids)
                
                logger.info(f"Último ID conhecido: {latest_msg_id}")
                logger.info(f"ID mais antigo conhecido: {oldest_msg_id}")
                logger.info(f"Total de {len(processed_ids)} mensagens já processadas")
            except Exception as e:
                logger.error(f"Erro ao processar IDs existentes: {str(e)}")
                latest_msg_id = 0
                oldest_msg_id = 0
                processed_ids = set()
            
            # Tentar acessar o histórico de mensagens usando get_chat_history
            # ou get_messages (conforme o que funcionar)
            try:
                # Este é o método principal - tentar get_chat_history primeiro
                logger.info("Tentando get_chat_history...")
                
                msg_count = 0
                max_msgs = 2000
                
                try:
                    async for message in app.get_chat_history(chat_id, limit=max_msgs):
                        # Processar cada mensagem
                        msg_count += 1
                        processed_count += 1
                        
                        # Pular mensagens já processadas
                        if message.id in processed_ids:
                            continue
                        
                        # Adicionar ao conjunto de processados
                        processed_ids.add(message.id)
                        
                        # Extrair ASIN se disponível
                        message_text = message.text or message.caption or ""
                        asin = extract_asin_from_text(message_text)
                        
                        if asin:
                            source = extract_source_from_text(message_text)
                            logger.info(f"Encontrado post com ASIN: {asin}, Fonte: {source}, ID: {message.id}")
                            
                            # Adicionar ao post_info
                            timestamp = datetime.datetime.now().isoformat()
                            if hasattr(message, 'date'):
                                timestamp = message.date.isoformat()
                            
                            # Adicionar aos novos posts
                            new_posts[str(message.id)] = {
                                "asin": asin,
                                "source": source,
                                "timestamp": timestamp
                            }
                            added_count += 1
                            
                            # Salvar incrementalmente
                            if added_count % 10 == 0:
                                combined_post_info = {**post_info, **new_posts}
                                save_post_info(combined_post_info)
                                logger.info(f"Checkpoint: Salvos {added_count} posts até agora")
                        
                        # Mostrar progresso
                        if msg_count % 100 == 0:
                            logger.info(f"Progresso: {msg_count}/{max_msgs} mensagens processadas")
                except Exception as history_err:
                    logger.warning(f"Erro ao usar get_chat_history: {str(history_err)}")
                    
                    # Método alternativo: get_messages
                    # Se get_chat_history falhar, tentar get_messages com IDs específicos
                    logger.info("Tentando acessar mensagens individuais...")
                    
                    # Definir intervalo para verificar (a partir do último ID conhecido)
                    start_id = max(1, latest_msg_id - 2000)
                    end_id = latest_msg_id + 200
                    
                    # Criar lotes de 100 IDs para buscar (para evitar sobrecarregar a API)
                    batch_size = 100
                    for batch_start in range(start_id, end_id, batch_size):
                        batch_end = min(batch_start + batch_size, end_id)
                        msg_ids = list(range(batch_start, batch_end))
                        
                        logger.info(f"Buscando lote de {len(msg_ids)} mensagens: {batch_start}-{batch_end}")
                        
                        try:
                            messages = await app.get_messages(chat_id, msg_ids)
                            
                            # Processar mensagens obtidas
                            for message in messages:
                                if not message or message.empty:
                                    continue
                                    
                                processed_count += 1
                                
                                # Pular mensagens já processadas
                                if message.id in processed_ids:
                                    continue
                                
                                # Adicionar ao conjunto de processados
                                processed_ids.add(message.id)
                                
                                # Extrair ASIN se disponível
                                message_text = message.text or message.caption or ""
                                asin = extract_asin_from_text(message_text)
                                
                                if asin:
                                    source = extract_source_from_text(message_text)
                                    logger.info(f"Encontrado post com ASIN: {asin}, Fonte: {source}, ID: {message.id}")
                                    
                                    # Adicionar ao post_info
                                    timestamp = datetime.datetime.now().isoformat()
                                    if hasattr(message, 'date'):
                                        timestamp = message.date.isoformat()
                                    
                                    # Adicionar aos novos posts
                                    new_posts[str(message.id)] = {
                                        "asin": asin,
                                        "source": source,
                                        "timestamp": timestamp
                                    }
                                    added_count += 1
                                    
                                    # Salvar incrementalmente
                                    if added_count % 10 == 0:
                                        combined_post_info = {**post_info, **new_posts}
                                        save_post_info(combined_post_info)
                                        logger.info(f"Checkpoint: Salvos {added_count} posts até agora")
                                
                            # Pausa entre lotes
                            await asyncio.sleep(1)
                        except FloodWait as e:
                            # Esperar o tempo recomendado pelo Telegram
                            logger.warning(f"Rate limit atingido. Aguardando {e.x} segundos...")
                            await asyncio.sleep(e.x)
                        except Exception as batch_err:
                            logger.warning(f"Erro ao processar lote {batch_start}-{batch_end}: {str(batch_err)}")
                            
                            # Ainda tentar mensagens individuais como último recurso
                            for msg_id in msg_ids:
                                try:
                                    message = await app.get_messages(chat_id, msg_id)
                                    if message and not message.empty:
                                        # Processar mensagem (mesmo código que acima)
                                        processed_count += 1
                                        
                                        # Pular mensagens já processadas
                                        if message.id in processed_ids:
                                            continue
                                        
                                        # Adicionar ao conjunto de processados
                                        processed_ids.add(message.id)
                                        
                                        # Extrair ASIN se disponível
                                        message_text = message.text or message.caption or ""
                                        asin = extract_asin_from_text(message_text)
                                        
                                        if asin:
                                            source = extract_source_from_text(message_text)
                                            logger.info(f"Encontrado post individual com ASIN: {asin}, ID: {message.id}")
                                            
                                            # Adicionar ao post_info
                                            timestamp = datetime.datetime.now().isoformat()
                                            if hasattr(message, 'date'):
                                                timestamp = message.date.isoformat()
                                            
                                            # Adicionar aos novos posts
                                            new_posts[str(message.id)] = {
                                                "asin": asin,
                                                "source": source,
                                                "timestamp": timestamp
                                            }
                                            added_count += 1
                                except Exception:
                                    # Ignorar erros individuais
                                    pass
                                
                                # Pequena pausa entre mensagens individuais
                                await asyncio.sleep(0.05)
                
                logger.info(f"Recuperação completa: {processed_count} mensagens processadas, {added_count} posts encontrados")
                
            except Exception as e:
                logger.error(f"Erro durante tentativas de recuperação de mensagens: {str(e)}")
                
        except Exception as e:
            logger.error(f"Erro ao acessar mensagens: {str(e)}")
        
        # Adicionar todos os novos posts ao post_info
        if new_posts:
            post_info.update(new_posts)
            save_post_info(post_info)
            logger.info(f"Recuperação concluída: {added_count} posts adicionados (processadas {processed_count} mensagens)")
        else:
            logger.info(f"Nenhum post novo encontrado (processadas {processed_count} mensagens)")
        
    except Exception as e:
        logger.error(f"Erro geral durante recuperação com Pyrogram: {str(e)}")
    finally:
        # Garantir que o cliente seja finalizado
        try:
            await app.stop()
            logger.info("Cliente Pyrogram encerrado")
        except Exception as e:
            logger.error(f"Erro ao encerrar cliente Pyrogram: {str(e)}")
    
    return post_info

# Versão compatível da função original para o bot usar
async def retrieve_missing_products(bot, source_chat_id, post_info):
    """
    Recuperar posts de produtos que podem estar faltando.
    Esta função agora usará Pyrogram com string de sessão.
    
    Args:
        bot: Instância do Bot do Telegram (não usado nesta versão)
        source_chat_id: ID do chat de origem
        post_info: Dicionário atual de post_info
        
    Returns:
        dict: Dicionário post_info atualizado
    """
    logger.info("Iniciando recuperação de posts faltantes usando Pyrogram...")
    
    # Tentar obter a string de sessão da configuração
    session_string = os.environ.get('PYROGRAM_SESSION_STRING', '')
    
    # Se não estiver no ambiente, verificar no arquivo .env ou em um arquivo de sessão
    if not session_string:
        session_file = "session_string.txt"
        if os.path.exists(session_file):
            try:
                with open(session_file, "r") as f:
                    session_string = f.read().strip()
                logger.info("String de sessão carregada de arquivo")
            except Exception as e:
                logger.error(f"Erro ao ler arquivo de string de sessão: {str(e)}")
    
    if not session_string:
        logger.error("String de sessão não encontrada. Pulando recuperação com Pyrogram.")
        return post_info
    
    try:
        # Executar recuperação com Pyrogram usando o ID específico do chat
        updated_post_info = await recover_with_pyrogram_string(session_string, source_chat_id, post_info)
        return updated_post_info
    except Exception as e:
        logger.error(f"Erro na recuperação com Pyrogram: {str(e)}")
        return post_info

# Comando para administrador iniciar recuperação manual
async def start_recovery_command(update, context):
    """
    Comando para iniciar recuperação manual com Pyrogram
    """
    from config.settings import load_settings
    settings = load_settings()
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Este comando é exclusivo para administradores.")
        return
    
    await update.message.reply_text("🔄 Iniciando recuperação de mensagens usando Pyrogram. Isso pode levar algum tempo...")
    
    # Carregar dados atuais
    post_info = load_post_info()
    
    # Tentar obter a string de sessão da configuração
    session_string = os.environ.get('PYROGRAM_SESSION_STRING', '')
    
    # Se não estiver no ambiente, verificar no arquivo .env ou em um arquivo de sessão
    if not session_string:
        session_file = "session_string.txt"
        if os.path.exists(session_file):
            try:
                with open(session_file, "r") as f:
                    session_string = f.read().strip()
                logger.info("String de sessão carregada de arquivo")
            except Exception as e:
                logger.error(f"Erro ao ler arquivo de string de sessão: {str(e)}")
    
    if not session_string:
        await update.message.reply_text("❌ String de sessão não encontrada. Configure PYROGRAM_SESSION_STRING no ambiente ou crie um arquivo session_string.txt")
        return
    
    try:
        # Executar recuperação com Pyrogram
        updated_post_info = await recover_with_pyrogram_string(session_string, settings.SOURCE_CHAT_ID, post_info)
        
        # Contar novos posts
        new_count = len(updated_post_info) - len(post_info)
        
        await update.message.reply_text(f"✅ Recuperação concluída! {new_count} novos posts encontrados.\nTotal atual: {len(updated_post_info)} posts.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro durante a recuperação: {str(e)}")