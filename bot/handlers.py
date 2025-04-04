import logging
import os
import asyncio
from datetime import datetime
from telegram import Update, InputFile
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from config.settings import load_settings
from keepa.browser import initialize_driver
from keepa.api import login_to_keepa, update_keepa_product, delete_keepa_tracking
from data.data_manager import load_post_info, save_post_info, clean_old_entries
# Importar driver_sessions de message_processor para compartilhar as mesmas sessões
from bot.message_processor import process_message, driver_sessions, post_info
# Importar gerenciador de sessões
from keepa.browser_session_manager import browser_manager
# Importar funcionalidade de backup
from utils.backup import create_backup, list_backups, delete_backup, auto_cleanup_backups
# Importar utilitário de retry
from utils.retry import async_retry

from utils.logger import get_logger

logger = get_logger(__name__)
settings = load_settings()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enviar mensagem quando o comando /start é emitido."""
    await update.message.reply_text("Bot iniciado! Vou capturar ASINs, comentários e atualizar preços no Keepa.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostrar status atual da configuração do bot."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode verificar o status.")
        return
    
    # Obter contas disponíveis
    accounts_info = "\n".join([f"• {account}" for account in settings.KEEPA_ACCOUNTS.keys()])
    if not accounts_info:
        accounts_info = "Nenhuma conta configurada"
    
    # Obter informações das sessões ativas
    active_sessions = len(browser_manager.sessions)
    
    status_message = (
        f"🤖 **Status do Bot:**\n\n"
        f"💬 **Chat de Origem:** {settings.SOURCE_CHAT_ID or 'Não configurado'}\n"
        f"📩 **Chat de Destino:** {settings.DESTINATION_CHAT_ID or 'Não configurado'}\n"
        f"👤 **ID do Admin:** {settings.ADMIN_ID or 'Não configurado'}\n"
        f"📊 **Posts rastreados:** {len(post_info)}\n"
        f"🌐 **Sessões ativas:** {active_sessions}\n"
        f"🔐 **Contas Keepa:**\n{accounts_info}\n"
        f"🔄 **Conta Padrão:** {settings.DEFAULT_KEEPA_ACCOUNT}\n"
        f"🔄 **Alertas de Atualização:** {'Sim' if settings.UPDATE_EXISTING_TRACKING else 'Não'}"
    )
    
    # Usar ParseMode.MARKDOWN para formatação
    await update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN)

@async_retry(max_attempts=2)
async def test_account_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Testar login para uma conta Keepa específica."""
    global driver_sessions
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode testar contas.")
        return
    
    try:
        args = context.args
        if not args:
            accounts_list = ", ".join(settings.KEEPA_ACCOUNTS.keys())
            await update.message.reply_text(f"❌ Por favor, especifique uma conta para testar. Contas disponíveis: {accounts_list}")
            return
        
        account_identifier = args[0]
        
        if account_identifier not in settings.KEEPA_ACCOUNTS:
            await update.message.reply_text(f"❌ Conta '{account_identifier}' não encontrada na configuração.")
            return
        
        await update.message.reply_text(f"Testando login para conta '{account_identifier}'...")
        
        # Usar o gerenciador de sessões
        session = await browser_manager.get_session(account_identifier)
        
        if session and session.is_logged_in:
            await update.message.reply_text(f"✅ Login bem-sucedido para conta '{account_identifier}'!")
        else:
            # Fallback para o método antigo
            driver = initialize_driver(account_identifier)
            success = login_to_keepa(driver, account_identifier)
            
            if success:
                # Armazenar a sessão para uso futuro
                driver_sessions[account_identifier] = driver
                await update.message.reply_text(f"✅ Login bem-sucedido para conta '{account_identifier}'!")
            else:
                await update.message.reply_text(f"❌ Login falhou para conta '{account_identifier}'. Verifique os logs para detalhes.")
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao testar conta: {str(e)}")
        # Repassar a exceção para o mecanismo de retry
        raise

@async_retry(max_attempts=2)
async def start_keepa_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Iniciar sessão Keepa."""
    global driver_sessions
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode iniciar a sessão Keepa.")
        return
    
    # Verificar se temos uma conta especificada
    args = context.args
    account_identifier = args[0] if args else settings.DEFAULT_KEEPA_ACCOUNT
    
    await update.message.reply_text(f"Iniciando sessão Keepa para conta '{account_identifier}'...")
    
    try:
        # Usar o gerenciador de sessões
        session = await browser_manager.get_session(account_identifier)
        
        if session and session.is_logged_in:
            await update.message.reply_text(f"✅ Sessão Keepa iniciada com sucesso para conta '{account_identifier}'!")
        else:
            # Fallback para o método antigo
            driver = initialize_driver(account_identifier)
            success = login_to_keepa(driver, account_identifier)
            
            if success:
                # Armazenar a sessão para uso futuro
                driver_sessions[account_identifier] = driver
                await update.message.reply_text(f"✅ Sessão Keepa iniciada com sucesso para conta '{account_identifier}'!")
            else:
                await update.message.reply_text(f"❌ Falha ao iniciar sessão Keepa para conta '{account_identifier}'. Verifique os logs.")
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao iniciar sessão Keepa: {str(e)}")
        # Repassar a exceção para o mecanismo de retry
        raise

@async_retry(max_attempts=2)
async def update_price_manual_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Atualizar manualmente o preço de um produto."""
    global driver_sessions
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode atualizar manualmente os preços.")
        return
    
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ Formato incorreto. Use: /update ASIN PREÇO [CONTA]")
            return
        
        asin = args[0].upper()
        price = args[1]
        
        # Verificar se temos uma conta especificada
        account_identifier = args[2] if len(args) > 2 else settings.DEFAULT_KEEPA_ACCOUNT
        
        await update.message.reply_text(f"Atualizando ASIN {asin} com preço {price} usando conta '{account_identifier}'...")
        
        # Tentar usar uma sessão existente do gerenciador
        session = await browser_manager.get_session(account_identifier)
        driver = None
        
        if session and session.is_logged_in:
            driver = session.driver
            logger.info(f"Usando sessão existente para a conta {account_identifier}")
            
            success = update_keepa_product(driver, asin, price)
            
            if success:
                await update.message.reply_text(f"✅ ASIN {asin} atualizado com sucesso com conta '{account_identifier}'!")
            else:
                await update.message.reply_text(f"❌ Falha ao atualizar ASIN {asin} com conta '{account_identifier}'.")
        else:
            # Criar uma nova instância de driver para esta operação
            driver = initialize_driver(account_identifier)
            
            try:
                success = login_to_keepa(driver, account_identifier)
                if not success:
                    await update.message.reply_text(f"❌ Falha ao fazer login no Keepa com conta '{account_identifier}'.")
                    return
                
                success = update_keepa_product(driver, asin, price)
                
                if success:
                    await update.message.reply_text(f"✅ ASIN {asin} atualizado com sucesso com conta '{account_identifier}'!")
                else:
                    await update.message.reply_text(f"❌ Falha ao atualizar ASIN {asin} com conta '{account_identifier}'.")
            finally:
                # Importante: Sempre encerrar o driver para liberar recursos
                # Só fechamos o driver se criamos um novo (não fechamos o driver gerenciado pelo SessionManager)
                if driver and not session:
                    try:
                        driver.quit()
                        logger.info(f"Sessão do driver Chrome fechada para conta {account_identifier}")
                    except Exception as e:
                        logger.error(f"Erro ao fechar o driver Chrome: {str(e)}")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao atualizar preço: {str(e)}")
        # Repassar a exceção para o mecanismo de retry
        raise

@async_retry(max_attempts=2)
async def delete_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Excluir rastreamento de um produto."""
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode excluir rastreamentos.")
        return
    
    try:
        args = context.args
        if len(args) < 1:
            await update.message.reply_text("❌ Formato incorreto. Use: /delete ASIN [CONTA]")
            return
        
        asin = args[0].upper()
        
        # Verificar se temos uma conta especificada
        account_identifier = args[1] if len(args) > 1 else settings.DEFAULT_KEEPA_ACCOUNT
        
        await update.message.reply_text(f"Excluindo rastreamento para ASIN {asin} da conta '{account_identifier}'...")
        
        # Tentar usar uma sessão existente do gerenciador
        session = await browser_manager.get_session(account_identifier)
        driver = None
        
        if session and session.is_logged_in:
            driver = session.driver
            logger.info(f"Usando sessão existente para a conta {account_identifier}")
            
            success = delete_keepa_tracking(driver, asin)
            
            if success:
                await update.message.reply_text(f"✅ Rastreamento para ASIN {asin} excluído com sucesso da conta '{account_identifier}'!")
            else:
                await update.message.reply_text(f"❌ Falha ao excluir rastreamento para ASIN {asin} da conta '{account_identifier}'.")
        else:
            # Criar uma nova instância de driver para esta operação
            driver = initialize_driver(account_identifier)
            
            try:
                success = login_to_keepa(driver, account_identifier)
                if not success:
                    await update.message.reply_text(f"❌ Falha ao fazer login no Keepa com conta '{account_identifier}'.")
                    return
                
                success = delete_keepa_tracking(driver, asin)
                
                if success:
                    await update.message.reply_text(f"✅ Rastreamento para ASIN {asin} excluído com sucesso da conta '{account_identifier}'!")
                else:
                    await update.message.reply_text(f"❌ Falha ao excluir rastreamento para ASIN {asin} da conta '{account_identifier}'.")
            finally:
                # Importante: Sempre encerrar o driver para liberar recursos
                # Só fechamos o driver se criamos um novo (não fechamos o driver gerenciado pelo SessionManager)
                if driver and not session:
                    try:
                        driver.quit()
                        logger.info(f"Sessão do driver Chrome fechada para conta {account_identifier}")
                    except Exception as e:
                        logger.error(f"Erro ao fechar o driver Chrome: {str(e)}")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao excluir rastreamento: {str(e)}")
        # Repassar a exceção para o mecanismo de retry
        raise

async def list_accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Listar todas as contas Keepa configuradas."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode listar contas.")
        return
    
    if not settings.KEEPA_ACCOUNTS:
        await update.message.reply_text("❌ Nenhuma conta Keepa configurada.")
        return
    
    # Obter informações das sessões ativas
    active_sessions = browser_manager.sessions
    
    # Preparar a lista de contas com status das sessões
    account_lines = []
    for account in settings.KEEPA_ACCOUNTS.keys():
        status = "🟢 Ativa" if account in active_sessions else "⚪ Inativa"
        account_lines.append(f"• {account} - {status}")
    
    accounts_info = "\n".join(account_lines)
    
    message = (
        f"🔐 **Contas Keepa Configuradas:**\n\n"
        f"{accounts_info}\n\n"
        f"Conta padrão: {settings.DEFAULT_KEEPA_ACCOUNT}"
    )
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def clear_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Limpar cache de posts rastreados."""
    global post_info
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode usar este comando.")
        return
    
    post_info.clear()
    save_post_info(post_info)
    await update.message.reply_text("✅ Cache de posts limpo.")

async def close_sessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fechar todas as sessões de navegador."""
    global driver_sessions
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode usar este comando.")
        return
    
    # Fechar sessões do gerenciador
    closed_count = browser_manager.close_all_sessions()
    
    # Fechar sessões antigas
    old_sessions_count = 0
    for account, driver in driver_sessions.items():
        try:
            driver.quit()
            logger.info(f"Sessão antiga fechada para conta: {account}")
            old_sessions_count += 1
        except Exception as e:
            logger.error(f"Erro ao fechar sessão antiga para conta {account}: {str(e)}")
    
    # Limpar o dicionário de sessões
    driver_sessions.clear()
    
    await update.message.reply_text(f"✅ Sessões fechadas: {closed_count} gerenciadas + {old_sessions_count} antigas.")

# Novos comandos de backup
async def create_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Criar um backup dos dados e logs do bot."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode criar backups.")
        return
    
    await update.message.reply_text("🔄 Criando backup... Isso pode levar um momento.")
    
    try:
        backup_path = create_backup()
        
        if backup_path:
            # Enviar o arquivo de backup
            with open(backup_path, 'rb') as backup_file:
                await update.message.reply_document(
                    document=InputFile(backup_file),
                    caption=f"✅ Backup criado com sucesso: {os.path.basename(backup_path)}"
                )
            
            # Limpeza automática de backups antigos
            deleted = auto_cleanup_backups(max_backups=10)
            if deleted > 0:
                await update.message.reply_text(f"🧹 Limpeza automática: Removidos {deleted} backup(s) antigo(s).")
        else:
            await update.message.reply_text("❌ Falha ao criar backup. Verifique os logs para detalhes.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao criar backup: {str(e)}")

async def list_backups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Listar todos os backups disponíveis."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode visualizar backups.")
        return
    
    try:
        backups = list_backups()
        
        if not backups:
            await update.message.reply_text("📂 Nenhum backup encontrado.")
            return
        
        # Formatar a lista de backups
        backup_list = []
        for i, backup in enumerate(backups, 1):
            creation_time = backup["creation_time"].strftime("%Y-%m-%d %H:%M:%S")
            backup_list.append(f"{i}. {backup['filename']} - {creation_time} - {backup['size_mb']} MB")
        
        await update.message.reply_text(
            f"📂 **Backups Disponíveis ({len(backups)}):**\n\n" + 
            "\n".join(backup_list) + 
            "\n\nPara baixar um backup, use: `/download_backup FILENAME`",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao listar backups: {str(e)}")

async def download_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Baixar um arquivo de backup específico."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode baixar backups.")
        return
    
    try:
        args = context.args
        if not args:
            await update.message.reply_text("❌ Por favor, especifique um nome de arquivo de backup para baixar.")
            return
        
        filename = args[0]
        
        # Verificar se o arquivo existe
        backup_dir = "/app/backups"
        backup_path = os.path.join(backup_dir, filename)
        
        if not os.path.exists(backup_path):
            # Tentar listar backups disponíveis
            backups = list_backups()
            available_files = "\n".join([f"• {b['filename']}" for b in backups[:5]])
            
            message = f"❌ Arquivo de backup não encontrado: {filename}\n\n"
            if available_files:
                message += f"Backups disponíveis (mostrando máx. 5):\n{available_files}\n\nUse /list_backups para lista completa."
            else:
                message += "Nenhum arquivo de backup encontrado."
            
            await update.message.reply_text(message)
            return
        
        # Enviar o arquivo de backup
        await update.message.reply_text(f"🔄 Preparando para enviar backup: {filename}")
        
        with open(backup_path, 'rb') as backup_file:
            await update.message.reply_document(
                document=InputFile(backup_file),
                caption=f"✅ Backup: {filename}"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao baixar backup: {str(e)}")

async def delete_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Excluir um arquivo de backup específico."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode excluir backups.")
        return
    
    try:
        args = context.args
        if not args:
            await update.message.reply_text("❌ Por favor, especifique um nome de arquivo de backup para excluir.")
            return
        
        filename = args[0]
        
        # Excluir o backup
        success = delete_backup(filename)
        
        if success:
            await update.message.reply_text(f"✅ Backup excluído com sucesso: {filename}")
        else:
            # Tentar listar backups disponíveis
            backups = list_backups()
            available_files = "\n".join([f"• {b['filename']}" for b in backups[:5]])
            
            message = f"❌ Falha ao excluir backup: {filename}\n\n"
            if available_files:
                message += f"Backups disponíveis (mostrando máx. 5):\n{available_files}\n\nUse /list_backups para lista completa."
            else:
                message += "Nenhum arquivo de backup encontrado."
            
            await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao excluir backup: {str(e)}")

async def sessions_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostrar status detalhado das sessões de navegador ativas."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode verificar o status das sessões.")
        return
    
    # Obter informações das sessões do gerenciador
    sessions = browser_manager.sessions
    
    if not sessions:
        await update.message.reply_text("🔍 Nenhuma sessão ativa no gerenciador.")
        return
    
    # Criar mensagem com detalhes das sessões
    sessions_list = []
    for account_id, session in sessions.items():
        idle_time = int((datetime.now() - session.last_used).total_seconds())
        idle_str = f"{idle_time} segundos"
        if idle_time > 60:
            idle_str = f"{idle_time // 60} minutos, {idle_time % 60} segundos"
        
        status = "🟢 Logado" if session.is_logged_in else "🟠 Não logado"
        sessions_list.append(f"• {account_id}: {status}, Inatividade: {idle_str}")
    
    # Também verificar driver_sessions antigas
    old_sessions = []
    for account_id in driver_sessions:
        old_sessions.append(f"• {account_id} (método antigo)")
    
    old_sessions_text = "\n".join(old_sessions) if old_sessions else "Nenhuma"
    
    message = (
        f"🌐 **Status das Sessões:**\n\n"
        f"**Sessões gerenciadas ({len(sessions)}):**\n"
        f"{chr(10).join(sessions_list)}\n\n"
        f"**Sessões antigas ({len(driver_sessions)}):**\n"
        f"{old_sessions_text}"
    )
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

def setup_handlers(application):
    """Configurar todos os manipuladores do bot"""
    # Manipuladores de comando
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("clear", clear_cache_command))
    application.add_handler(CommandHandler("start_keepa", start_keepa_command))
    application.add_handler(CommandHandler("update", update_price_manual_command))
    application.add_handler(CommandHandler("delete", delete_product_command))
    application.add_handler(CommandHandler("test_account", test_account_command))
    application.add_handler(CommandHandler("accounts", list_accounts_command))
    application.add_handler(CommandHandler("close_sessions", close_sessions_command))
    application.add_handler(CommandHandler("sessions", sessions_status_command))
    
    # Comandos de backup
    application.add_handler(CommandHandler("backup", create_backup_command))
    application.add_handler(CommandHandler("list_backups", list_backups_command))
    application.add_handler(CommandHandler("download_backup", download_backup_command))
    application.add_handler(CommandHandler("delete_backup", delete_backup_command))
    
    # Manipulador de mensagens
    application.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION, 
        process_message
    ))
    
    logger.info("Manipuladores configurados")