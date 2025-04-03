import logging
import os
from telegram import Update, InputFile
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode  # Adicionar esta importação para uso em todo o arquivo
from config.settings import load_settings
from keepa.browser import initialize_driver
from keepa.api import login_to_keepa, update_keepa_product
from data.data_manager import load_post_info, save_post_info, clean_old_entries
# Importar driver_sessions de message_processor para compartilhar as mesmas sessões
from bot.message_processor import process_message, driver_sessions, post_info
# Importar funcionalidade de backup
from utils.backup import create_backup, list_backups, delete_backup, auto_cleanup_backups

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
    
    status_message = (
        f"🤖 **Status do Bot:**\n\n"
        f"💬 **Chat de Origem:** {settings.SOURCE_CHAT_ID or 'Não configurado'}\n"
        f"📩 **Chat de Destino:** {settings.DESTINATION_CHAT_ID or 'Não configurado'}\n"
        f"👤 **ID do Admin:** {settings.ADMIN_ID or 'Não configurado'}\n"
        f"📊 **Posts rastreados:** {len(post_info)}\n"
        f"🔐 **Contas Keepa:**\n{accounts_info}\n"
        f"🔄 **Conta Padrão:** {settings.DEFAULT_KEEPA_ACCOUNT}\n"
        f"🔄 **Alertas de Atualização:** {'Sim' if settings.UPDATE_EXISTING_TRACKING else 'Não'}"
    )
    
    # Usar ParseMode.MARKDOWN para formatação
    from telegram.constants import ParseMode
    await update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN)

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
        
        driver = initialize_driver()
        success = login_to_keepa(driver, account_identifier)
        
        if success:
            # Armazenar a sessão para uso futuro
            driver_sessions[account_identifier] = driver
            await update.message.reply_text(f"✅ Login bem-sucedido para conta '{account_identifier}'!")
        else:
            await update.message.reply_text(f"❌ Login falhou para conta '{account_identifier}'. Verifique os logs para detalhes.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao testar conta: {str(e)}")

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
        driver = initialize_driver()
        success = login_to_keepa(driver, account_identifier)
        
        if success:
            # Armazenar a sessão para uso futuro
            driver_sessions[account_identifier] = driver
            await update.message.reply_text(f"✅ Sessão Keepa iniciada com sucesso para conta '{account_identifier}'!")
        else:
            await update.message.reply_text(f"❌ Falha ao iniciar sessão Keepa para conta '{account_identifier}'. Verifique os logs.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao iniciar sessão Keepa: {str(e)}")

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
            try:
                driver.quit()
                logger.info(f"Sessão do driver Chrome fechada para conta {account_identifier}")
            except Exception as e:
                logger.error(f"Erro ao fechar o driver Chrome: {str(e)}")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao atualizar preço: {str(e)}")

async def list_accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Listar todas as contas Keepa configuradas."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode listar contas.")
        return
    
    if not settings.KEEPA_ACCOUNTS:
        await update.message.reply_text("❌ Nenhuma conta Keepa configurada.")
        return
    
    accounts_info = "\n".join([f"• {account}" for account in settings.KEEPA_ACCOUNTS.keys()])
    message = (
        f"🔐 **Contas Keepa Configuradas:**\n\n"
        f"{accounts_info}\n\n"
        f"Conta padrão: {settings.DEFAULT_KEEPA_ACCOUNT}"
    )
    
    # Usar ParseMode.MARKDOWN para formatação
    from telegram.constants import ParseMode
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
    
    # Fechar todas as sessões
    for account, driver in driver_sessions.items():
        try:
            driver.quit()
            logger.info(f"Sessão fechada para conta: {account}")
        except Exception as e:
            logger.error(f"Erro ao fechar sessão para conta {account}: {str(e)}")
    
    # Limpar o dicionário de sessões
    driver_sessions.clear()
    await update.message.reply_text("✅ Todas as sessões de navegador fechadas.")

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
        
        from telegram.constants import ParseMode
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

def setup_handlers(application):
    """Configurar todos os manipuladores do bot"""
    # Manipuladores de comando
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("clear", clear_cache_command))
    application.add_handler(CommandHandler("start_keepa", start_keepa_command))
    application.add_handler(CommandHandler("update", update_price_manual_command))
    application.add_handler(CommandHandler("test_account", test_account_command))
    application.add_handler(CommandHandler("accounts", list_accounts_command))
    application.add_handler(CommandHandler("close_sessions", close_sessions_command))
    
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