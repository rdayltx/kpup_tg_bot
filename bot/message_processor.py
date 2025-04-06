import logging
import asyncio
from datetime import datetime
import re
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config.settings import load_settings
from data.data_manager import load_post_info, save_post_info
from utils.text_parser import extract_asin_from_text, extract_source_from_text, extract_price_from_comment, should_ignore_message, should_ignore_message
from keepa.browser import initialize_driver
from keepa.api import login_to_keepa, update_keepa_product, delete_keepa_tracking
from utils.logger import get_logger
from utils.retry import async_retry
from keepa.browser_session_manager import browser_manager
from data.product_database import product_db

# Importar o formatador de mensagens aprimorado
from utils.message_formatter import format_destination_message

logger = get_logger(__name__)
settings = load_settings()

# Inicializar variáveis globais
# Isso será compartilhado com handlers.py
driver_sessions = {}
post_info = load_post_info()

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processar mensagens do canal/grupo e identificar posts e comentários."""
    global post_info, driver_sessions
    
    if not settings.SOURCE_CHAT_ID:
        return

    message = update.message or update.channel_post
    if not message:
        return

    # Obter informações do usuário que enviou a mensagem
    user_name = None
    if message.from_user:
        # Priorizar nome completo, depois username, depois ID
        if message.from_user.first_name:
            user_name = message.from_user.first_name
            if message.from_user.last_name:
                user_name += f" {message.from_user.last_name}"
        elif message.from_user.username:
            user_name = f"@{message.from_user.username}"
        else:
            user_name = f"ID:{message.from_user.id}"
    else:
        # Se for mensagem de canal ou chat, pegar o título
        if message.sender_chat:
            user_name = message.sender_chat.title or f"Canal:{message.sender_chat.id}"
        else:
            user_name = "Desconhecido"

    # Verificar se a mensagem vem do grupo/canal correto
    effective_chat_id = str(update.effective_chat.id)
    sender_chat_id = str(message.sender_chat.id) if message.sender_chat else None

    if effective_chat_id != settings.SOURCE_CHAT_ID and sender_chat_id != settings.SOURCE_CHAT_ID:
        return

    message_id = message.message_id
    message_text = message.text or message.caption or ""

    logger.info(f"Processando mensagem {message_id}: {message_text[:50]}...")
    
    # Verificar se a mensagem contém palavras-chave para ignorar
    if should_ignore_message(message_text):
        logger.info(f"Ignorando mensagem {message_id} pois contém palavras-chave para ignorar")
        return
    
    # NOVA VERIFICAÇÃO: Ignorar mensagem se contiver palavras-chave para ignorar
    if should_ignore_message(message_text):
        logger.info(f"Ignorando mensagem {message_id} pois contém palavras-chave ignoradas")
        return
    
    # Verificar se a mensagem vem do grupo/canal correto
    effective_chat_id = str(update.effective_chat.id)
    sender_chat_id = str(message.sender_chat.id) if message.sender_chat else None

    if effective_chat_id != settings.SOURCE_CHAT_ID and sender_chat_id != settings.SOURCE_CHAT_ID:
        return

    message_id = message.message_id
    message_text = message.text or message.caption or ""

    logger.info(f"Processando mensagem {message_id}: {message_text[:50]}...")

    # Extrair ASIN e fonte se este for um post de produto
    asin = extract_asin_from_text(message_text)
    
    if asin:
        source = extract_source_from_text(message_text)
        logger.info(f"Post com ASIN encontrado: {asin}, Fonte: {source}")
        
        # Armazenar post original com ASIN, Fonte e timestamp
        post_info[str(message_id)] = {
            "asin": asin,
            "source": source,
            "timestamp": datetime.now().isoformat()
        }
        save_post_info(post_info)
    
    # Verificar se este é um comentário em um post rastreado
    elif message.reply_to_message:
        replied_message = message.reply_to_message
        replied_message_id = str(replied_message.message_id)

        # Verificar se o post original é rastreado
        if replied_message_id in post_info:
            asin = post_info[replied_message_id]["asin"]
            source = post_info[replied_message_id]["source"]
            comment = message_text.strip()
            
            logger.info(f"Comentário identificado para ASIN {asin}: {comment}")
            logger.info(f"Fonte do post original: {source}")
            logger.info(f"Usuário que enviou o comentário: {user_name}")
            
            # Verificar comando DELETE
            if re.search(r'\bDELETE\b', comment, re.IGNORECASE):
                logger.info(f"🗑️ Comando DELETE detectado para ASIN {asin}")
                await handle_delete_comment(context, asin, source, comment, user_name)
                return
            
            # Extrair preço do comentário
            price = extract_price_from_comment(comment)
            
            if price:
                logger.info(f"Preço extraído do comentário: {price} (tipo: {type(price).__name__})")
                
                # Garantir formato correto do preço (número com ponto decimal)
                try:
                    # Verificar se é convertível para float
                    float_price = float(price)
                    # Converter de volta para string com 2 casas decimais
                    price = f"{float_price:.2f}"
                    # Garantir que usa . como separador decimal (não ,)
                    price = price.replace(",", ".")
                    
                    logger.info(f"Preço normalizado: {price}")
                except ValueError:
                    logger.error(f"Preço extraído não é um número válido: {price}")
                    if settings.ADMIN_ID:
                        await context.bot.send_message(
                            chat_id=settings.ADMIN_ID,
                            text=f"⚠️ Preço extraído não é válido para ASIN {asin}: {price}"
                        )
                    return False
            
            # Usar fonte como identificador de conta se existir em nossas contas
            account_identifier = None
            if source in settings.KEEPA_ACCOUNTS:
                account_identifier = source
                logger.info(f"Usando fonte como identificador de conta: {account_identifier}")
            else:
                # Se a fonte não for uma conta válida, verificar se há uma terceira parte no comentário
                parts = comment.strip().split(',')
                if len(parts) >= 3:
                    potential_account = parts[2].strip()
                    if potential_account in settings.KEEPA_ACCOUNTS:
                        account_identifier = potential_account
                        logger.info(f"Usando parte do comentário como identificador de conta: {account_identifier}")
            
            # Se ainda não tiver uma conta válida, usar a padrão
            if not account_identifier:
                account_identifier = settings.DEFAULT_KEEPA_ACCOUNT
                logger.info(f"Nenhuma conta válida encontrada, usando a padrão: {account_identifier}")
            
            if price:
                logger.info(f"Preço extraído do comentário: {price}")
                await handle_price_update(context, asin, source, comment, price, account_identifier, user_name)
            else:
                logger.warning(f"⚠️ Não foi possível extrair preço do comentário: {comment}")
                
                # Notificar administrador
                if settings.ADMIN_ID:
                    await context.bot.send_message(
                        chat_id=settings.ADMIN_ID,
                        text=f"⚠️ Não foi possível extrair preço do comentário para ASIN {asin}: {comment}"
                    )

@async_retry(max_attempts=3, delay=5, backoff=2, jitter=0.1)
async def handle_price_update(context, asin, source, comment, price, account_identifier, user_name):
    """
    Gerenciar atualização de preço no Keepa
    """
    update_success = False
    driver = None
    product_title = None
    session = None
    
    try:
        # Tentar obter uma sessão de navegador do gerenciador
        session = await browser_manager.get_session(account_identifier)
        if not session:
            logger.error(f"❌ Não foi possível obter uma sessão válida para a conta {account_identifier}")
            
            # Fallback para o método antigo se o gerenciador falhar
            logger.info(f"Tentando método alternativo com um novo driver para {account_identifier}")
            driver = initialize_driver(account_identifier)
            login_success = login_to_keepa(driver, account_identifier)
            
            if not login_success:
                logger.error(f"❌ Falha ao fazer login no Keepa com a conta {account_identifier}")
                if settings.ADMIN_ID:
                    await context.bot.send_message(
                        chat_id=settings.ADMIN_ID,
                        text=f"❌ Falha ao fazer login no Keepa com a conta {account_identifier}"
                    )
                return False
            pass
        else:
            # Usar o driver da sessão
            driver = session.driver
            logger.info(f"Usando sessão existente para conta {account_identifier}")
        
        # Executar a atualização
        update_success, product_title = update_keepa_product(driver, asin, price)
        if update_success:
            logger.info(f"✅ ASIN {asin} atualizado com sucesso no Keepa com preço {price} usando conta {account_identifier}")
            
            # Atualizar o banco de dados de produtos
            product_db.update_product(account_identifier, asin, price, product_title)
            logger.info(f"✅ Banco de dados de produtos atualizado para ASIN {asin}, conta {account_identifier}")
            
            # Notificar administrador
            if settings.ADMIN_ID:
                await context.bot.send_message(
                    chat_id=settings.ADMIN_ID,
                    text=f"✅ ASIN {asin} atualizado com preço {price} usando conta {account_identifier}"
                )
        else:
            logger.error(f"❌ Falha ao atualizar ASIN {asin} no Keepa")
            
            # Notificar administrador
            if settings.ADMIN_ID:
                await context.bot.send_message(
                    chat_id=settings.ADMIN_ID,
                    text=f"❌ Falha ao atualizar ASIN {asin} no Keepa usando conta {account_identifier}"
                )
            pass
                
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar preço no Keepa: {str(e)}")
        
        # Notificar administrador
        if settings.ADMIN_ID:
            await context.bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=f"❌ Erro ao atualizar preço no Keepa com a conta {account_identifier}: {str(e)}"
            )
        # Repassar a exceção para o mecanismo de retry
        raise
    finally:
        # Só fechar o driver se criamos um novo (não fechamos o driver gerenciado pelo SessionManager)
        if driver and not session:
            try:
                driver.quit()
                logger.info(f"Sessão do driver Chrome fechada para a conta {account_identifier}")
            except Exception as e:
                logger.error(f"Erro ao fechar o driver Chrome: {str(e)}")
        pass
    
    # Formatar e enviar a mensagem informativa para o canal de destino
    formatted_message = format_destination_message(
        asin=asin,
        comment=comment,
        source=source,
        price=price,
        action="update",
        success=update_success,
        user_name=user_name,
        product_title=product_title
    )
    
    # Enviar para o grupo de destino
    try:
        if settings.DESTINATION_CHAT_ID:
            await context.bot.send_message(
                chat_id=settings.DESTINATION_CHAT_ID,
                text=formatted_message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            logger.info(f"Informações detalhadas enviadas para o chat {settings.DESTINATION_CHAT_ID}")
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem para o grupo de destino: {e}")
        if settings.ADMIN_ID:
            await context.bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=f"❌ Erro ao enviar mensagem para o grupo de destino: {e}"
            )
    
    return update_success

@async_retry(max_attempts=3, delay=5, backoff=2, jitter=0.1)
async def handle_delete_comment(context, asin, source, comment, user_name):
    """
    Gerenciar solicitação de exclusão de rastreamento no Keepa
    
    Args:
        context: Contexto do Telegram
        asin: ASIN do produto
        source: Identificador da fonte
        comment: Comentário do usuário
        user_name: Nome do usuário que fez a ação
    """
    
    account_identifier = None
    delete_success = False
    driver = None
    session = None
    product_title = None
    
    # Usar fonte como identificador de conta se existir em nossas contas
    if source in settings.KEEPA_ACCOUNTS:
        account_identifier = source
        logger.info(f"Usando fonte como identificador de conta para exclusão: {account_identifier}")
    else:
        # Se a fonte não for uma conta válida, verificar se há uma terceira parte no comentário
        parts = comment.strip().split(',')
        if len(parts) >= 3:
            potential_account = parts[2].strip()
            if potential_account in settings.KEEPA_ACCOUNTS:
                account_identifier = potential_account
                logger.info(f"Usando parte do comentário como identificador de conta para exclusão: {account_identifier}")
    
    # Se ainda não tiver uma conta válida, usar a padrão
    if not account_identifier:
        account_identifier = settings.DEFAULT_KEEPA_ACCOUNT
        logger.info(f"Nenhuma conta válida encontrada para exclusão, usando a padrão: {account_identifier}")
    
    try:
        # Tentar obter uma sessão de navegador do gerenciador
        session = await browser_manager.get_session(account_identifier)
        if not session:
            logger.error(f"❌ Não foi possível obter uma sessão válida para a conta {account_identifier}")
            
            # Fallback para o método antigo
            logger.info(f"Tentando método alternativo com um novo driver para {account_identifier}")
            driver = initialize_driver(account_identifier)
            login_success = login_to_keepa(driver, account_identifier)
            
            if not login_success:
                logger.error(f"❌ Falha ao fazer login no Keepa com a conta {account_identifier}")
                if settings.ADMIN_ID:
                    await context.bot.send_message(
                        chat_id=settings.ADMIN_ID,
                        text=f"❌ Falha ao fazer login no Keepa com a conta {account_identifier} para exclusão"
                    )
                return False
        else:
            # Usar o driver da sessão
            driver = session.driver
            logger.info(f"Usando sessão existente para conta {account_identifier}")
        
        # Executar a exclusão
        delete_success, product_title = delete_keepa_tracking(driver, asin)
        if delete_success:
            logger.info(f"✅ Rastreamento do ASIN {asin} excluído com sucesso usando conta {account_identifier}")
            
            # Notificar administrador
            if settings.ADMIN_ID:
                await context.bot.send_message(
                    chat_id=settings.ADMIN_ID,
                    text=f"✅ Rastreamento do ASIN {asin} excluído usando conta {account_identifier}"
                )
        else:
            logger.error(f"❌ Falha ao excluir rastreamento do ASIN {asin}")
            
            # Notificar administrador
            if settings.ADMIN_ID:
                await context.bot.send_message(
                    chat_id=settings.ADMIN_ID,
                    text=f"❌ Falha ao excluir rastreamento do ASIN {asin} usando conta {account_identifier}"
                )
            pass    
            
    except Exception as e:
        logger.error(f"❌ Erro ao excluir rastreamento no Keepa: {str(e)}")
        
        # Notificar administrador
        if settings.ADMIN_ID:
            await context.bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=f"❌ Erro ao excluir rastreamento no Keepa com a conta {account_identifier}: {str(e)}"
            )
        # Repassar a exceção para o mecanismo de retry
        raise
    finally:
        # Só fechar o driver se criamos um novo (não fechamos o driver gerenciado pelo SessionManager)
        if driver and not session:
            try:
                driver.quit()
                logger.info(f"Sessão do driver Chrome fechada para a conta {account_identifier}")
            except Exception as e:
                logger.error(f"Erro ao fechar o driver Chrome: {str(e)}")
            
        pass
    
    # Formatar e enviar a mensagem informativa para o canal de destino
    formatted_message = format_destination_message(
        asin=asin,
        comment=comment,
        source=source,
        action="delete",
        success=delete_success,
        user_name=user_name,
        product_title=product_title
    )
    
    # Enviar para o grupo de destino
    try:
        if settings.DESTINATION_CHAT_ID:
            await context.bot.send_message(
                chat_id=settings.DESTINATION_CHAT_ID,
                text=formatted_message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            logger.info(f"Informações de exclusão enviadas para o chat {settings.DESTINATION_CHAT_ID}")
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem de exclusão para o grupo de destino: {e}")
        if settings.ADMIN_ID:
            await context.bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=f"❌ Erro ao enviar mensagem de exclusão para o grupo de destino: {e}"
            )
    
    return delete_success