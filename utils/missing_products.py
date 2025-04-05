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
        
        # Lidar com o erro PEER_ID_INVALID
        try:
            # Para chat_id específico fornecido
            chat_id_to_use = int("-1002563291570")  # Usar o ID exato fornecido
            logger.info(f"Usando ID de chat específico: {chat_id_to_use}")
            
            # Tentar obter informações do chat
            try:
                # Primeiro, tentar entrar no chat usando link de convite (se disponível)
                invite_link = os.environ.get('CHAT_INVITE_LINK', '')
                if invite_link:
                    try:
                        logger.info(f"Tentando entrar no chat usando link de convite: {invite_link}")
                        await app.join_chat(invite_link)
                        logger.info(f"Tentativa de entrar no chat enviada com sucesso")
                    except Exception as join_err:
                        logger.warning(f"Tentativa de entrar no chat falhou (pode ser que já seja membro): {str(join_err)}")
                
                # Agora tentar acessar o chat diretamente
                try:
                    chat = await app.get_chat(chat_id_to_use)
                    logger.info(f"Chat acessado com sucesso: {chat.title}")
                    chat_id = chat_id_to_use
                except PeerIdInvalid:
                    # Tentar formato alternativo
                    alternative_id = int(chat_id_to_use)  # sem string
                    logger.info(f"Tentando formato alternativo: {alternative_id}")
                    chat = await app.get_chat(alternative_id)
                    logger.info(f"Chat acessado com formato alternativo: {chat.title}")
                    chat_id = alternative_id
            except Exception as chat_err:
                logger.error(f"Não foi possível acessar o chat {chat_id_to_use}: {str(chat_err)}")
                
                # SOLUÇÃO DE CONTORNO PARA TESTES:
                # Se não conseguimos acessar o chat, mas temos algumas mensagens no post_info,
                # podemos tentar trabalhar com essas mensagens diretamente
                if len(post_info) > 0:
                    logger.warning("Não foi possível acessar o chat. Tentando trabalhar com IDs de mensagens conhecidas.")
                    # Informar usuário sobre as etapas manuais necessárias
                    logger.warning("ATENÇÃO: A conta usada pela sessão Pyrogram precisa ser membro do chat.")
                    logger.warning("SOLUÇÃO: Entre no chat com essa conta, envie uma mensagem, e tente novamente.")
                    
                    # Retornar post_info inalterado
                    return post_info
                else:
                    # Sem mensagens conhecidas e sem acesso ao chat, não podemos continuar
                    raise
        except Exception as e:
            logger.error(f"Todos os métodos para acessar o chat falharam: {str(e)}")
            await app.stop()
            return post_info
        
        # Se chegou aqui, conseguimos acessar o chat. Prosseguir com a recuperação...
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
        
        # Modo de recuperação: tudo em um
        # Vai buscar todas as mensagens recentes de uma vez
        try:
            logger.info("Iniciando recuperação completa do histórico recente")
            
            # Obter mensagens recentes (acima do último ID conhecido)
            # Limitamos a 2000 mensagens para não sobrecarregar
            max_msgs = 2000
            msg_count = 0
            
            # Obter histórico do chat
            async for message in app.get_chat_history(chat_id, limit=max_msgs):
                msg_count += 1
                processed_count += 1
                
                # Pular mensagens já processadas
                if message.id in processed_ids:
                    continue
                
                # Adicionar ao conjunto de processados
                processed_ids.add(message.id)
                
                # Extrair texto da mensagem
                message_text = message.text or message.caption or ""
                
                # Extrair ASIN e fonte
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
                    
                    # Salvar incrementalmente a cada 10 novos posts
                    if added_count % 10 == 0:
                        combined_post_info = {**post_info, **new_posts}
                        save_post_info(combined_post_info)
                        logger.info(f"Checkpoint: Salvos {added_count} posts até agora")
                
                # Exibir progresso a cada 100 mensagens
                if msg_count % 100 == 0:
                    logger.info(f"Progresso: {msg_count}/{max_msgs} mensagens processadas, {added_count} posts encontrados")
            
            logger.info(f"Recuperação completa: {msg_count} mensagens processadas, {added_count} posts encontrados")
            
            # Procurar mensagens em faixas específicas para preencher lacunas
            # Definir faixas de IDs para verificar lacunas
            if len(existing_ids) > 5:
                # Ordenar IDs existentes
                sorted_ids = sorted(existing_ids)
                
                # Identificar lacunas entre IDs consecutivos
                gap_ranges = []
                for i in range(len(sorted_ids) - 1):
                    current = sorted_ids[i]
                    next_id = sorted_ids[i + 1]
                    
                    # Se houver uma lacuna significativa
                    if next_id - current > 30:
                        # Registrar faixa para verificação
                        gap_start = current + 1
                        gap_end = next_id - 1
                        gap_ranges.append((gap_start, gap_end))
                
                # Verificar até 5 lacunas principais
                for idx, (start_id, end_id) in enumerate(gap_ranges[:5]):
                    range_size = end_id - start_id + 1
                    logger.info(f"Verificando lacuna {idx+1}/{len(gap_ranges[:5])}: IDs {start_id}-{end_id} ({range_size} mensagens)")
                    
                    # Se a lacuna for muito grande, verificar apenas uma amostra
                    if range_size > 100:
                        # Criar uma lista de IDs para verificar (até 100 amostras)
                        sample_size = min(100, range_size)
                        step = range_size // sample_size
                        ids_to_check = list(range(start_id, end_id + 1, step))
                    else:
                        # Verificar todos os IDs na lacuna
                        ids_to_check = list(range(start_id, end_id + 1))
                    
                    # Verificar cada ID
                    gap_processed = 0
                    gap_found = 0
                    
                    for msg_id in ids_to_check:
                        # Pular se já foi processado
                        if msg_id in processed_ids:
                            continue
                        
                        try:
                            # Tentar obter a mensagem específica
                            message = await app.get_messages(chat_id, msg_id)
                            
                            if message and (message.text or message.caption):
                                gap_processed += 1
                                processed_count += 1
                                
                                # Adicionar ao conjunto de processados
                                processed_ids.add(message.id)
                                
                                # Extrair ASIN e fonte
                                message_text = message.text or message.caption or ""
                                asin = extract_asin_from_text(message_text)
                                
                                if asin:
                                    source = extract_source_from_text(message_text)
                                    logger.info(f"Encontrado post em lacuna com ASIN: {asin}, Fonte: {source}, ID: {message.id}")
                                    
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
                                    gap_found += 1
                                    
                                    # Salvar incrementalmente
                                    if added_count % 10 == 0:
                                        combined_post_info = {**post_info, **new_posts}
                                        save_post_info(combined_post_info)
                                        logger.info(f"Checkpoint: Salvos {added_count} posts no total")
                            
                            # Pausa curta para evitar flood
                            await asyncio.sleep(0.05)
                            
                        except FloodWait as e:
                            # Esperar o tempo recomendado pelo Telegram
                            logger.warning(f"Rate limit atingido. Aguardando {e.x} segundos...")
                            await asyncio.sleep(e.x)
                        except (MessageIdInvalid, MessageNotModified):
                            # Mensagem não existe ou não pode ser acessada
                            pass
                        except Exception as e:
                            logger.warning(f"Erro ao obter mensagem {msg_id}: {str(e)}")
                    
                    logger.info(f"Lacuna {idx+1} verificada: {gap_processed} mensagens, {gap_found} posts encontrados")
                
                logger.info(f"Verificação de lacunas concluída: {added_count} posts encontrados no total")
            
        except FloodWait as e:
            logger.warning(f"Rate limit atingido. Aguardando {e.x} segundos...")
            await asyncio.sleep(e.x)
        except Exception as e:
            logger.error(f"Erro durante recuperação com Pyrogram: {str(e)}")
        
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
        # Executar recuperação com Pyrogram (forçando ID específico)
        updated_post_info = await recover_with_pyrogram_string(session_string, "-1002563291570", post_info)
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
        # Executar recuperação com Pyrogram (forçando ID específico)
        updated_post_info = await recover_with_pyrogram_string(session_string, "-1002563291570", post_info)
        
        # Contar novos posts
        new_count = len(updated_post_info) - len(post_info)
        
        await update.message.reply_text(f"✅ Recuperação concluída! {new_count} novos posts encontrados.\nTotal atual: {len(updated_post_info)} posts.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro durante a recuperação: {str(e)}")