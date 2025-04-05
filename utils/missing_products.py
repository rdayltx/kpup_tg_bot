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
        
        # Tentar resolver o chat_id de várias maneiras diferentes
        chat = None
        chat_id_to_use = None
        
        # Lista de formatos de ID para tentar
        formats_to_try = [
            int("-1002563291570"),  # Como int, formato original
            int("2563291570"),      # Como int, sem o prefixo -100
            "-1002563291570",       # Como string, formato original
            "2563291570",           # Como string, sem prefixo
            "-100" + "2563291570".lstrip("0")  # Formato alternativo
        ]
        
        # Tentar resolver o chat de diferentes maneiras
        for format_id in formats_to_try:
            try:
                logger.info(f"Tentando acessar o chat com formato de ID: {format_id}")
                chat = await app.get_chat(format_id)
                logger.info(f"Chat acessado com sucesso: {chat.title} (ID: {chat.id})")
                chat_id_to_use = format_id
                break
            except Exception as e:
                logger.warning(f"Formato {format_id} falhou: {str(e)}")
        
        # Se ainda não conseguimos acessar, tentar métodos alternativos
        if not chat:
            # Método alternativo: Usar o ID diretamente para get_messages ou get_history
            logger.info("Tentando acessar mensagens diretamente...")
            try:
                # Tentar obter uma mensagem recente (ID arbitrário alto)
                messages = await app.get_messages(-1002563291570, 1000)
                if messages:
                    logger.info(f"Mensagem acessada diretamente: {messages}")
                    chat_id_to_use = -1002563291570
                    # Agora podemos tentar acessar o chat novamente
                    chat = await app.get_chat(chat_id_to_use)
                    logger.info(f"Chat acessado após obter mensagem: {chat.title}")
            except Exception as e:
                logger.warning(f"Tentativa direta falhou: {str(e)}")
        
        # Segundo método alternativo: Usar o link de convite
        if not chat:
            invite_link = os.environ.get('CHAT_INVITE_LINK', 'https://t.me/+nv9ZJS7ADqQ1MzVh')
            if invite_link:
                try:
                    logger.info(f"Tentando obter detalhes do chat via link de convite: {invite_link}")
                    
                    # Extrair o hash do convite do link
                    invite_hash = invite_link.split('+')[-1]
                    logger.info(f"Hash do convite: {invite_hash}")
                    
                    # Tentar obter o chat usando o hash
                    # Primeiro tentar entrar (mesmo que já seja membro)
                    try:
                        await app.join_chat(invite_link)
                        logger.info("Tentativa de entrar no chat enviada")
                    except Exception as join_err:
                        logger.warning(f"Erro ao entrar (pode já ser membro): {str(join_err)}")
                    
                    # Agora tentar obter informações do chat usando get_chat
                    try:
                        # Tentar obter o chat usando o hash do convite
                        chat_info = await app.get_chat(invite_hash)
                        logger.info(f"Chat obtido via hash: {chat_info.title} (ID: {chat_info.id})")
                        chat = chat_info
                        chat_id_to_use = chat_info.id
                    except Exception as hash_err:
                        logger.warning(f"Erro ao acessar via hash: {str(hash_err)}")
                    
                    # Se ainda não conseguimos, tentar usar diálogos para encontrar o chat
                    if not chat:
                        logger.info("Tentando encontrar o chat nos diálogos recentes...")
                        async for dialog in app.get_dialogs():
                            logger.info(f"Verificando diálogo: {dialog.chat.title} (ID: {dialog.chat.id})")
                            if dialog.chat.type in ["supergroup", "channel"]:
                                # Ver se o ID corresponde ao que estamos procurando
                                if str(dialog.chat.id).endswith("2563291570"):
                                    logger.info(f"Chat encontrado nos diálogos: {dialog.chat.title} (ID: {dialog.chat.id})")
                                    chat = dialog.chat
                                    chat_id_to_use = dialog.chat.id
                                    break
                except Exception as invite_err:
                    logger.warning(f"Erro ao processar convite: {str(invite_err)}")
        
        # Se ainda não conseguimos acessar o chat
        if not chat:
            logger.error("Não foi possível acessar o chat por nenhum método.")
            # Tente usar o ID original mesmo assim para o próximo passo
            chat_id_to_use = -1002563291570
        
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