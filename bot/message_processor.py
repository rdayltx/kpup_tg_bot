import logging
from datetime import datetime
import re
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config.settings import load_settings
from data.data_manager import load_post_info, save_post_info
from utils.text_parser import extract_asin_from_text, extract_source_from_text, extract_price_from_comment
from keepa.browser import initialize_driver
from keepa.api import login_to_keepa, update_keepa_product
from utils.logger import get_logger

# Importar a nova função de exclusão de rastreamento
from keepa.api import delete_keepa_tracking

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
            
            # Verificar comando DELETE
            if re.search(r'\bDELETE\b', comment, re.IGNORECASE):
                logger.info(f"🗑️ Comando DELETE detectado para ASIN {asin}")
                await handle_delete_comment(context, asin, source, comment)
                return
            
            # Extrair preço do comentário
            price = extract_price_from_comment(comment)
            
            # Usar fonte como identificador de conta se existir em nossas contas
            account_identifier = None
            if source.lower() in [acc.lower() for acc in settings.KEEPA_ACCOUNTS.keys()]:
                # Encontrar a chave correta com case matching
                for acc_key in settings.KEEPA_ACCOUNTS.keys():
                    if source.lower() == acc_key.lower():
                        account_identifier = acc_key
                        break
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
                await handle_price_update(context, asin, source, comment, price, account_identifier)
            else:
                logger.warning(f"⚠️ Não foi possível extrair preço do comentário: {comment}")
                
                # Notificar administrador
                if settings.ADMIN_ID:
                    await context.bot.send_message(
                        chat_id=settings.ADMIN_ID,
                        text=f"⚠️ Não foi possível extrair preço do comentário para ASIN {asin}: {comment}"
                    )

async def handle_price_update(context, asin, source, comment, price, account_identifier):
    """
    Gerenciar atualização de preço no Keepa com mecanismo de retry
    """
    update_success = False
    driver = None
    max_retries = 3
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Tentativa {attempt}/{max_retries} para atualizar ASIN {asin}")
            
            # Sempre inicializar um novo driver para cada atualização de preço
            driver = initialize_driver(account_identifier)
            login_success = login_to_keepa(driver, account_identifier)
            
            if login_success:
                update_success = update_keepa_product(driver, asin, price)
                if update_success:
                    logger.info(f"✅ ASIN {asin} atualizado com sucesso no Keepa com preço {price}")
                    
                    # Notificar administrador
                    if settings.ADMIN_ID:
                        await context.bot.send_message(
                            chat_id=settings.ADMIN_ID,
                            text=f"✅ ASIN {asin} atualizado com preço {price} usando conta {account_identifier}"
                        )
                    break  # Sair do loop se sucesso
                else:
                    logger.error(f"❌ Falha ao atualizar ASIN {asin} no Keepa (tentativa {attempt})")
            else:
                logger.error(f"❌ Falha ao fazer login no Keepa com a conta {account_identifier} (tentativa {attempt})")
                
                # Limpar a sessão para a próxima tentativa
                if attempt < max_retries:
                    logger.info(f"Limpando a sessão para a tentativa {attempt+1}")
                    # Implemente limpeza seletiva (ou use o driver.delete_all_cookies())
                    driver.delete_all_cookies()
                    
            if attempt < max_retries and not update_success:
                wait_time = attempt * 5  # Backoff exponencial
                logger.info(f"Aguardando {wait_time} segundos antes da próxima tentativa...")
                await asyncio.sleep(wait_time)
                
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar preço no Keepa (tentativa {attempt}): {str(e)}")
            if attempt < max_retries:
                wait_time = attempt * 5
                logger.info(f"Aguardando {wait_time} segundos antes da próxima tentativa...")
                await asyncio.sleep(wait_time)
        finally:
            # Importante: Sempre fechar o driver para liberar recursos
            if driver:
                try:
                    driver.quit()
                    logger.info(f"Sessão do driver Chrome fechada para a conta {account_identifier}")
                except Exception as e:
                    logger.error(f"Erro ao fechar o driver Chrome: {str(e)}")
    
    
    # Formatar e enviar a mensagem informativa para o canal de destino
    formatted_message = format_destination_message(
        asin=asin,
        comment=comment,
        source=source,
        price=price,
        action="update",
        success=update_success
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

async def handle_delete_comment(context, asin, source, comment):
    """
    Gerenciar solicitação de exclusão de rastreamento no Keepa
    
    Args:
        context: Contexto do Telegram
        asin: ASIN do produto
        source: Identificador da fonte
        comment: Comentário do usuário
    """
    account_identifier = None
    delete_success = False
    driver = None
    
    # Usar fonte como identificador de conta se existir em nossas contas
    if source.lower() in [acc.lower() for acc in settings.KEEPA_ACCOUNTS.keys()]:
        # Encontrar a chave correta com case matching
        for acc_key in settings.KEEPA_ACCOUNTS.keys():
            if source.lower() == acc_key.lower():
                account_identifier = acc_key
                break
        logger.info(f"Usando fonte como identificador de conta: {account_identifier}")
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
        # Inicializar um novo driver
        driver = initialize_driver(account_identifier)
        login_success = login_to_keepa(driver, account_identifier)
        
        if login_success:
            delete_success = delete_keepa_tracking(driver, asin)
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
        else:
            logger.error(f"❌ Falha ao fazer login no Keepa com a conta {account_identifier}")
            
            # Notificar administrador
            if settings.ADMIN_ID:
                await context.bot.send_message(
                    chat_id=settings.ADMIN_ID,
                    text=f"❌ Falha ao fazer login no Keepa com a conta {account_identifier} para exclusão"
                )
    except Exception as e:
        logger.error(f"❌ Erro ao excluir rastreamento no Keepa: {str(e)}")
        
        # Notificar administrador
        if settings.ADMIN_ID:
            await context.bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=f"❌ Erro ao excluir rastreamento no Keepa com a conta {account_identifier}: {str(e)}"
            )
    finally:
        # Sempre fechar o driver para liberar recursos
        if driver:
            try:
                driver.quit()
                logger.info(f"Sessão do driver Chrome fechada para a conta {account_identifier}")
            except Exception as e:
                logger.error(f"Erro ao fechar o driver Chrome: {str(e)}")
    
    # Formatar e enviar a mensagem informativa para o canal de destino
    formatted_message = format_destination_message(
        asin=asin,
        comment=comment,
        source=source,
        action="delete",
        success=delete_success
    )
    
    # Enviar para o grupo de destino
    try:
        if settings.DESTINATION_CHAT_ID:
            await context.bot.send_message(
                chat_id=settings.DESTINATION_CHAT_ID,
                text=formatted_message,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Informações de exclusão enviadas para o chat {settings.DESTINATION_CHAT_ID}")
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem de exclusão para o grupo de destino: {e}")
        if settings.ADMIN_ID:
            await context.bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=f"❌ Erro ao enviar mensagem de exclusão para o grupo de destino: {e}"
            )