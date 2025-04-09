import logging
import os
import json
import glob
import re
from utils.timezone_config import get_brazil_datetime, format_brazil_datetime
import traceback
from datetime import datetime, timedelta
import asyncio
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
from utils.missing_products import start_recovery_command
from data.product_database import product_db
from handlers.product_commands import add_product_command, register_product_handlers
# Importar gerenciador de tarefas em segundo plano
from background_tasks import task_manager, start_background_task_manager
from bot.task_commands import register_task_handlers

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
    
    # Obter estatísticas do banco de dados de produtos
    product_stats = product_db.get_statistics()
    products_count = product_stats["total_products"]
    
    # Obter contagem de produtos por conta
    products_by_account = []
    for acc_id, acc_stats in product_stats["accounts"].items():
        products_by_account.append(f"• {acc_id}: {acc_stats['product_count']} produtos")
    
    products_info = "\n".join(products_by_account) if products_by_account else "Nenhum produto registrado"
    
    status_message = (
        f"🤖 **Status do Bot:**\n\n"
        f"💬 **Chat de Origem:** {settings.SOURCE_CHAT_ID or 'Não configurado'}\n"
        f"📩 **Chat de Destino:** {settings.DESTINATION_CHAT_ID or 'Não configurado'}\n"
        f"👤 **ID do Admin:** {settings.ADMIN_ID or 'Não configurado'}\n"
        f"📊 **Posts rastreados:** {len(post_info)}\n"
        f"📦 **Produtos no banco de dados:** {products_count}\n"
        f"🌐 **Sessões ativas:** {active_sessions}\n"
        f"🔐 **Contas Keepa:**\n{accounts_info}\n"
        f"📦 **Produtos por conta:**\n{products_info}\n"
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
            
            success, product_title = update_keepa_product(driver, asin, price)
            
            if success:
                # Atualizar o banco de dados de produtos
                product_db.update_product(account_identifier, asin, price, product_title)
                logger.info(f"✅ Banco de dados de produtos atualizado para ASIN {asin}, conta {account_identifier}")
                
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
                
                success, product_title = update_keepa_product(driver, asin, price)
                
                if success:
                    # Atualizar o banco de dados de produtos
                    product_db.update_product(account_identifier, asin, price, product_title)
                    logger.info(f"✅ Banco de dados de produtos atualizado para ASIN {asin}, conta {account_identifier}")
                    
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
            
            success, product_title = delete_keepa_tracking(driver, asin)
            
            if success:
                # Atualizar o banco de dados de produtos (excluir o produto)
                product_db.delete_product(account_identifier, asin)
                logger.info(f"✅ ASIN {asin} removido do banco de dados para conta {account_identifier}")
                
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
                
                success, product_title = delete_keepa_tracking(driver, asin)
                
                if success:
                    # Atualizar o banco de dados de produtos (excluir o produto)
                    product_db.delete_product(account_identifier, asin)
                    logger.info(f"✅ ASIN {asin} removido do banco de dados para conta {account_identifier}")
                    
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
    
    # Verificar se foi especificada uma conta
    args = context.args
    account_id = args[0] if args else None
    
    if account_id:
        # Verificar se a conta existe
        if account_id not in settings.KEEPA_ACCOUNTS:
            await update.message.reply_text(f"❌ Conta '{account_id}' não encontrada.")
            available_accounts = ", ".join(settings.KEEPA_ACCOUNTS.keys())
            await update.message.reply_text(f"Contas disponíveis: {available_accounts}")
            return
        
        # Obter produtos da conta específica
        products = product_db.get_all_products(account_id)
        
        if not products:
            await update.message.reply_text(f"Nenhum produto encontrado para a conta '{account_id}'.")
            return
        
        # Preparar mensagem com os produtos
        products_list = []
        for i, (asin, product_info) in enumerate(products.items(), 1):
            price = product_info.get("price", "?")
            title = product_info.get("product_title", "Sem título")
            last_updated = product_info.get("last_updated", "?")
            
            # Formatar data se disponível
            if last_updated and last_updated != "?":
                try:
                    dt = datetime.fromisoformat(last_updated)
                    last_updated = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            
            # Limitar título para não ficar muito grande
            if len(title) > 40:
                title = title[:37] + "..."
            
            products_list.append(f"{i}. {asin} - R${price} - {title} (Atualizado em: {last_updated})")
        
        # Dividir mensagem em partes se for muito longa
        message = f"📋 Produtos para conta '{account_id}' ({len(products)}):\n\n"
        
        # Enviar em várias mensagens se a lista for muito grande
        messages = []
        current_message = message
        
        for product in products_list:
            if len(current_message + product + "\n") > 4000:
                messages.append(current_message)
                current_message = ""
            
            current_message += product + "\n"
        
        if current_message:
            messages.append(current_message)
        
        # Enviar mensagens
        for msg in messages:
            await update.message.reply_text(msg)
    else:
        # Obter estatísticas de todas as contas (em vez de buscar um produto específico)
        stats = product_db.get_statistics()
        
        if stats["total_products"] == 0:
            await update.message.reply_text("Nenhum produto encontrado no banco de dados.")
            return
        
        # Preparar mensagem com estatísticas
        accounts_info = []
        for acc_id, acc_stats in stats["accounts"].items():
            product_count = acc_stats["product_count"]
            last_update = acc_stats["last_update"]
            
            # Formatar data se disponível
            if last_update:
                try:
                    dt = datetime.fromisoformat(last_update)
                    last_update = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    last_update = "?"
            else:
                last_update = "Nunca"
            
            accounts_info.append(f"• {acc_id}: {product_count} produtos (Última atualização: {last_update})")
        
        accounts_list = "\n".join(accounts_info)
        
        message = (
            f"📊 **Estatísticas do Banco de Dados de Produtos**\n\n"
            f"**Total de produtos:** {stats['total_products']}\n\n"
            f"**Contas:**\n{accounts_list}"
        )
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def product_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostrar estatísticas do banco de dados de produtos."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode ver estatísticas.")
        return
    
    # Obter estatísticas
    stats = product_db.get_statistics()
    
    if stats["total_products"] == 0:
        await update.message.reply_text("Nenhum produto encontrado no banco de dados.")
        return
    
    # Preparar mensagem com estatísticas
    accounts_info = []
    for acc_id, acc_stats in stats["accounts"].items():
        product_count = acc_stats["product_count"]
        last_update = acc_stats["last_update"]
        
        # Formatar data se disponível
        if last_update:
            try:
                dt = datetime.fromisoformat(last_update)
                last_update = dt.strftime("%Y-%m-%d %H:%M")
            except:
                last_update = "?"
        else:
            last_update = "Nunca"
        
        accounts_info.append(f"• {acc_id}: {product_count} produtos (Última atualização: {last_update})")
    
    accounts_list = "\n".join(accounts_info)
    
    # Formatação da data da última atualização
    last_update = stats.get("last_update", None)
    if last_update:
        try:
            dt = datetime.fromisoformat(last_update)
            last_update = dt.strftime("%Y-%m-%d %H:%M")
        except:
            last_update = "Desconhecida"
    else:
        last_update = "Nunca"
    
    message = (
        f"📊 **Estatísticas do Banco de Dados de Produtos**\n\n"
        f"**Total de produtos:** {stats['total_products']}\n"
        f"**Última atualização:** {last_update}\n\n"
        f"**Contas:**\n{accounts_list}\n\n"
        f"Para buscar um produto específico, use:\n`/product ASIN [CONTA]`"
    )
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def export_products_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exportar banco de dados de produtos para um arquivo JSON."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode exportar produtos.")
        return
    
    # Verificar se foi especificada uma conta
    args = context.args
    account_id = args[0] if args else None
    
    try:
        # Preparar o nome do arquivo com timestamp atual
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if account_id:
            # Exportar apenas produtos da conta especificada
            if account_id not in settings.KEEPA_ACCOUNTS:
                await update.message.reply_text(f"❌ Conta '{account_id}' não encontrada.")
                return
            
            products = product_db.get_all_products(account_id)
            
            if not products:
                await update.message.reply_text(f"Nenhum produto encontrado para a conta '{account_id}'.")
                return
            
            # Criar arquivo temporário com os produtos
            export_filename = f"produtos_{account_id}_{timestamp}.json"
            export_path = os.path.join("/tmp", export_filename)
            
            with open(export_path, "w") as f:
                json.dump({account_id: products}, f, indent=2)
            
            # Enviar o arquivo
            with open(export_path, 'rb') as f:
                await update.message.reply_document(
                    document=InputFile(f),
                    caption=f"✅ Exportados {len(products)} produtos da conta {account_id}."
                )
            
            # Limpar arquivo temporário
            os.remove(export_path)
        else:
            # Exportar todos os produtos
            products = product_db.get_all_products()
            
            if not products:
                await update.message.reply_text("Nenhum produto encontrado no banco de dados.")
                return
            
            # Contar total de produtos
            total_products = sum(len(acc_products) for acc_products in products.values())
            
            # Criar arquivo temporário com os produtos
            export_filename = f"todos_produtos_{timestamp}.json"
            export_path = os.path.join("/tmp", export_filename)
            
            with open(export_path, "w") as f:
                json.dump(products, f, indent=2)
            
            # Enviar o arquivo
            with open(export_path, 'rb') as f:
                await update.message.reply_document(
                    document=InputFile(f),
                    caption=f"✅ Exportados {total_products} produtos de {len(products)} contas."
                )
            
            # Limpar arquivo temporário
            os.remove(export_path)
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao exportar produtos: {str(e)}")

async def import_products_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Importar produtos de um arquivo JSON anexado."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode importar produtos.")
        return
    
    # Verificar se temos um arquivo anexado
    if not update.message.document:
        await update.message.reply_text("❌ Nenhum arquivo anexado. Por favor, envie um arquivo JSON junto com o comando.")
        return
    
    document = update.message.document
    file_name = document.file_name
    
    # Verificar se é um arquivo JSON
    if not file_name.lower().endswith('.json'):
        await update.message.reply_text("❌ O arquivo deve estar no formato JSON.")
        return
    
    await update.message.reply_text("🔄 Baixando e processando o arquivo...")
    
    try:
        # Baixar o arquivo
        file = await context.bot.get_file(document.file_id)
        file_path = os.path.join("/tmp", file_name)
        await file.download_to_drive(file_path)
        
        # Importar produtos
        success, stats = product_db.import_database(file_path)
        
        # Remover o arquivo temporário
        os.remove(file_path)
        
        if success:
            # Preparar mensagem de sucesso
            accounts_info = []
            for acc_id, count in stats["accounts"].items():
                if count > 0:
                    accounts_info.append(f"• {acc_id}: +{count} produtos")
            
            accounts_text = "\n".join(accounts_info) if accounts_info else "Nenhum produto novo"
            
            message = (
                f"✅ **Importação concluída com sucesso!**\n\n"
                f"**Total de produtos importados:** {stats['products_imported']}\n\n"
                f"**Produtos por conta:**\n{accounts_text}"
            )
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ Falha ao importar produtos. Verifique o formato do arquivo JSON.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao importar produtos: {str(e)}")

async def debug_products_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando de diagnóstico para debugar problemas com o banco de dados de produtos."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode usar este comando.")
        return
    
    # Verificar se foi especificada uma conta
    args = context.args
    account_id = args[0] if args else None
    
    if not account_id:
        await update.message.reply_text("❌ Por favor, especifique uma conta para diagnóstico.")
        return
    
    # Gerar relatório de diagnóstico
    try:
        await update.message.reply_text(f"🔍 Iniciando diagnóstico para conta '{account_id}'...")
        
        # 1. Verificar se o arquivo existe
        file_path = os.path.join("/app/data", f"products_{account_id}.json")
        file_exists = os.path.exists(file_path)
        
        # 2. Verificar tamanho e permissões do arquivo
        file_info = ""
        if file_exists:
            file_size = os.path.getsize(file_path)
            file_perms = oct(os.stat(file_path).st_mode)[-3:]
            file_info = f"- Tamanho: {file_size} bytes\n- Permissões: {file_perms}"
        
        # 3. Tentar ler o conteúdo do arquivo
        file_content = ""
        content_info = "- Não foi possível ler o conteúdo"
        
        if file_exists:
            try:
                with open(file_path, "r") as f:
                    file_content = f.read()
                if len(file_content) > 500:
                    content_info = f"- Conteúdo: primeiro 500 caracteres - {file_content[:500]}..."
                else:
                    content_info = f"- Conteúdo: {file_content}"
            except Exception as e:
                content_info = f"- Erro ao ler conteúdo: {str(e)}"
        
        # 4. Verificar o cache interno
        cache_info = "- Cache não disponível"
        try:
            if account_id in product_db.cached_databases:
                cache_products = product_db.cached_databases[account_id]
                cache_count = len(cache_products)
                some_products = list(cache_products.keys())[:5]
                cache_info = f"- Cache: {cache_count} produtos\n- Alguns ASINs: {', '.join(some_products)}"
            else:
                cache_info = "- Cache: Conta não encontrada no cache"
        except Exception as e:
            cache_info = f"- Erro ao acessar cache: {str(e)}"
        
        # 5. Tentar adicionar um produto de teste
        test_product_info = ""
        try:
            test_asin = f"TEST{random.randint(10000, 99999)}"
            test_price = "99.99"
            
            # Tentar adicionar produto
            success = product_db.update_product(account_id, test_asin, test_price, "Produto de teste")
            
            if success:
                # Verificar se o produto foi realmente adicionado
                products = product_db.get_all_products(account_id)
                if test_asin in products:
                    test_product_info = f"- Teste: ✓ Produto {test_asin} adicionado com sucesso"
                else:
                    test_product_info = f"- Teste: ⚠️ Produto retornou sucesso mas não foi encontrado na leitura"
            else:
                test_product_info = "- Teste: ❌ Falha ao adicionar produto de teste"
        except Exception as e:
            test_product_info = f"- Teste: ❌ Erro: {str(e)}"
        
        # Montar mensagem de diagnóstico
        diagnostico = (
            f"📊 **Diagnóstico do Banco de Dados para '{account_id}'**\n\n"
            f"**Arquivo:** {file_path}\n"
            f"- Existe: {'✓' if file_exists else '❌'}\n"
            f"{file_info}\n\n"
            f"**Conteúdo:**\n{content_info}\n\n"
            f"**Cache interno:**\n{cache_info}\n\n"
            f"**Teste de adição:**\n{test_product_info}"
        )
        
        await update.message.reply_text(diagnostico, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Erro durante diagnóstico: {str(e)}")
        
async def search_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando alternativo para buscar produto pelo ASIN."""
    # Obter o nome do comando corretamente
    command_text = "/search"  # Valor padrão
    command_entities = [entity for entity in update.message.entities if entity.type == "bot_command"]
    if command_entities:
        command_text = update.message.text[command_entities[0].offset:command_entities[0].offset + command_entities[0].length]
        logger.info(f"Comando {command_text} chamado por {update.effective_user.id}")
    else:
        logger.info(f"Função de busca chamada por {update.effective_user.id}")
    
    args = context.args
    if len(args) < 1:
        await update.message.reply_text(f"❌ Formato incorreto. Use: {command_text} ASIN")
        return
    
    asin = args[0].upper()
    await update.message.reply_text(f"🔍 Buscando produto com ASIN {asin}...")
    logger.info(f"Buscando ASIN: {asin}")
    
    # Diretório onde os arquivos de produtos estão armazenados
    data_dir = "/app/data"
    
    # Buscar produto em todos os arquivos de produtos
    found = False
    results = []
    
    try:
        # Listar todos os arquivos products_*.json no diretório de dados
        import os
        import json
        
        logger.info(f"Verificando diretório: {data_dir}")
        
        if os.path.exists(data_dir) and os.path.isdir(data_dir):
            logger.info(f"Diretório {data_dir} existe")
            files = os.listdir(data_dir)
            logger.info(f"Arquivos no diretório: {files}")
            
            product_files = [f for f in files if f.startswith("products_") and f.endswith(".json")]
            logger.info(f"Arquivos de produtos encontrados: {product_files}")
            
            if not product_files:
                await update.message.reply_text("⚠️ Nenhum arquivo de produtos encontrado.")
                return
            
            for product_file in product_files:
                # Extrair nome da conta do nome do arquivo
                account_id = product_file.replace("products_", "").replace(".json", "")
                file_path = os.path.join(data_dir, product_file)
                
                logger.info(f"Verificando arquivo: {file_path}")
                
                try:
                    # Verificar se o arquivo existe e pode ser lido
                    if not os.path.exists(file_path):
                        logger.warning(f"Arquivo não encontrado: {file_path}")
                        continue
                    
                    # Ler o arquivo JSON
                    with open(file_path, 'r') as f:
                        try:
                            products = json.load(f)
                            logger.info(f"Arquivo {product_file} contém {len(products)} produtos")
                            
                            # Verificar se o ASIN está no arquivo
                            if asin in products:
                                found = True
                                product_info = products[asin]
                                
                                # Extrair informações do produto
                                price = product_info.get("price", "?")
                                title = product_info.get("product_title", "Sem título")
                                last_updated = product_info.get("last_updated", "?")
                                
                                # Formatar data se disponível
                                if last_updated and last_updated != "?":
                                    try:
                                        dt = datetime.fromisoformat(last_updated)
                                        last_updated = dt.strftime("%Y-%m-%d %H:%M")
                                    except:
                                        pass
                                
                                # Limitar título para não ficar muito grande
                                if len(title) > 40:
                                    title = title[:37] + "..."
                                
                                results.append(
                                    f"**Conta:** {account_id}\n" +
                                    f"**Preço:** R$ {price}\n" +
                                    f"**Atualizado em:** {last_updated}\n" +
                                    f"**Título:** {title}"
                                )
                                logger.info(f"Produto {asin} encontrado na conta {account_id}")
                        except json.JSONDecodeError as json_err:
                            logger.error(f"Erro ao decodificar JSON em {product_file}: {str(json_err)}")
                except Exception as file_err:
                    logger.error(f"Erro ao processar arquivo {product_file}: {str(file_err)}")
        else:
            logger.error(f"Diretório {data_dir} não existe ou não é um diretório")
            await update.message.reply_text(f"❌ Diretório de dados não encontrado: {data_dir}")
            return
        
        # Enviar resultados da busca
        if found:
            amazon_url = f"https://www.amazon.com.br/dp/{asin}"
            keepa_url = f"https://keepa.com/#!product/12-{asin}"
            
            message = f"🔍 **Produto encontrado**\n\n**ASIN:** {asin}\n\n"
            message += "\n\n---\n\n".join(results)
            message += f"\n\n**Links:**\n[Amazon]({amazon_url}) | [Keepa]({keepa_url})"
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        else:
            await update.message.reply_text(f"❌ Produto com ASIN {asin} não encontrado em nenhuma conta.")
    
    except Exception as e:
        logger.error(f"Erro ao buscar produto: {str(e)}")
        await update.message.reply_text(f"❌ Erro ao buscar produto: {str(e)}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostrar mensagem de ajuda com todos os comandos disponíveis."""
    help_text = (
        "🤖 **Comandos do Keepa Bot**\n\n"
        
        "**Comandos Básicos:**\n"
        "• `/start` - Iniciar o bot\n"
        "• `/status` - Mostrar status atual do bot\n"
        "• `/help` - Exibir esta mensagem de ajuda\n\n"
        
        "**Comandos de Gestão de Sessões:**\n"
        "• `/start_keepa [CONTA]` - Iniciar sessão Keepa para uma conta\n"
        "• `/test_account CONTA` - Testar login em uma conta específica\n"
        "• `/accounts` - Listar todas as contas configuradas\n"
        "• `/sessions` - Mostrar status detalhado das sessões ativas\n"
        "• `/close_sessions` - Fechar todas as sessões ativas\n\n"
        
        "**Comandos de Produtos:**\n"
        "• `/add ASIN PREÇO` - Adicionar produto a uma conta aleatória (não excedendo 4999 produtos)\n"
        "• `/update ASIN PREÇO [CONTA]` - Atualizar manualmente o preço de um produto\n"
        "• `/delete ASIN [CONTA]` - Excluir rastreamento de um produto\n"
        "• `/search ASIN` - Buscar em qual conta o produto está rastreado\n"
        "• `/clear` - Limpar cache de posts rastreados\n\n"
        
        "**Banco de Dados de Produtos:**\n"
        "• `/product ASIN [CONTA]` - Buscar informações de um produto específico\n"
        "• `/product_stats` - Mostrar estatísticas do banco de dados de produtos\n"
        "• `/export_products [CONTA]` - Exportar produtos para arquivo JSON\n"
        "• `/import_products` - Importar produtos de um arquivo JSON anexado\n"
        "• `/debug_products CONTA` - Diagnóstico do banco de dados de produtos\n\n"
        
        "**Comandos de Backup:**\n"
        "• `/backup` - Criar backup dos dados e logs\n"
        "• `/list_backups` - Listar backups disponíveis\n"
        "• `/download_backup NOME` - Baixar um backup específico\n"
        "• `/delete_backup NOME` - Excluir um backup específico\n\n"
        
        "• `/queue_tasks` - Adicionar produtos a partir de um arquivo .txt\n"
        "• `/tasks_status` - Verificar o status das tarefas em segundo plano\n"
        "• `/pause_tasks` - Pausar o processamento de tarefas\n"
        "• `/resume_tasks` - Retomar o processamento de tarefas\n"
        "• `/clear_tasks` - Limpar a fila de tarefas\n"
        
        "**Comandos Avançados:**\n"
        "• `/recover` - Recuperar mensagens ausentes usando Pyrogram\n\n"
        
        "📝 **Nota:** A maioria dos comandos administrativos só pode ser executada pelo administrador configurado."
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Manipulador para documentos enviados ao bot
    Armazena o último documento para uso com comandos
    """
    # Guarda o documento para uso futuro
    document = update.message.document
    if document:
        context.bot_data['last_document'] = document
        context.bot_data['last_document_time'] = datetime.now()
        
        file_name = document.file_name
        
        # Verificar se é um arquivo .txt e se deve processar automaticamente
        if file_name.lower().endswith('.txt'):
            # Informar ao usuário que pode usar o comando /queue_tasks
            await update.message.reply_text(
                f"📄 Arquivo {file_name} recebido!\n\n"
                f"Para adicionar produtos deste arquivo à fila de tarefas, "
                f"use o comando /queue_tasks"
            )

# Atualização da função setup_handlers para incluir os novos comandos
def setup_handlers(application):
    """Configurar todos os manipuladores do bot"""
    # Manipuladores de comando
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_cache_command))
    application.add_handler(CommandHandler("start_keepa", start_keepa_command))
    application.add_handler(CommandHandler("update", update_price_manual_command))
    application.add_handler(CommandHandler("delete", delete_product_command))
    application.add_handler(CommandHandler("test_account", test_account_command))
    application.add_handler(CommandHandler("accounts", list_accounts_command))
    application.add_handler(CommandHandler("close_sessions", close_sessions_command))
    application.add_handler(CommandHandler("sessions", sessions_status_command))
    application.add_handler(CommandHandler("add", add_product_command))
    
    # Comandos de backup
    application.add_handler(CommandHandler("backup", create_backup_command))
    application.add_handler(CommandHandler("list_backups", list_backups_command))
    application.add_handler(CommandHandler("download_backup", download_backup_command))
    application.add_handler(CommandHandler("delete_backup", delete_backup_command))
    
    # Comandos do banco de dados de produtos
    application.add_handler(CommandHandler("product", get_product_command))
    application.add_handler(CommandHandler("product_stats", product_stats_command))
    application.add_handler(CommandHandler("export_products", export_products_command))
    application.add_handler(CommandHandler("import_products", import_products_command))
    application.add_handler(CommandHandler("debug_products", debug_products_command))
    application.add_handler(CommandHandler("find", search_product_command))
    application.add_handler(CommandHandler("search", search_product_command))

    
    # Registrar handlers de callback para o comando add_product
    register_product_handlers(application)
    
    # Registrar handlers de tarefas em segundo plano
    register_task_handlers(application)
    
    # Registrar handler para documentos
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Adicionar o comando de recuperação com Pyrogram
    application.add_handler(CommandHandler("recover", start_recovery_command))
    
    # Manipulador de mensagens
    application.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION, 
        process_message
    ))
    
    
    logger.info("Manipuladores configurados")
        

async def get_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Buscar informações detalhadas de um produto específico pelo ASIN."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode buscar produtos.")
        return
    
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ Formato incorreto. Use: /product ASIN [CONTA]")
        return
    
    asin = args[0].upper()
    account_id = args[1] if len(args) > 1 else None
    
    # Se foi fornecida uma conta, buscar apenas nessa conta
    if account_id:
        if account_id not in settings.KEEPA_ACCOUNTS:
            await update.message.reply_text(f"❌ Conta '{account_id}' não encontrada.")
            return
        
        product_info = product_db.get_product(account_id, asin)
        
        if not product_info:
            await update.message.reply_text(f"❌ Produto {asin} não encontrado para conta '{account_id}'.")
            return
        
        # Formatar informações do produto
        price = product_info.get("price", "?")
        title = product_info.get("product_title", "Sem título")
        last_updated = product_info.get("last_updated", "?")
        
        # Formatar data se disponível
        if last_updated and last_updated != "?":
            try:
                dt = datetime.fromisoformat(last_updated)
                last_updated = dt.strftime("%Y-%m-%d %H:%M")
            except:
                pass
        
        amazon_url = f"https://www.amazon.com.br/dp/{asin}"
        keepa_url = f"https://keepa.com/#!product/12-{asin}"
        
        message = (
            f"📦 **Informações do Produto**\n\n"
            f"**ASIN:** {asin}\n"
            f"**Título:** {title}\n"
            f"**Preço:** R$ {price}\n"
            f"**Conta:** {account_id}\n"
            f"**Atualizado em:** {last_updated}\n\n"
            f"**Links:**\n"
            f"[Amazon]({amazon_url}) | [Keepa]({keepa_url})"
        )
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    else:
        # Buscar produto em todas as contas
        found = False
        for acc_id in settings.KEEPA_ACCOUNTS.keys():
            product_info = product_db.get_product(acc_id, asin)
            
            if product_info:
                found = True
                
                # Formatar informações do produto
                price = product_info.get("price", "?")
                title = product_info.get("product_title", "Sem título")
                last_updated = product_info.get("last_updated", "?")
                
                # Formatar data se disponível
                if last_updated and last_updated != "?":
                    try:
                        dt = datetime.fromisoformat(last_updated)
                        last_updated = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                
                amazon_url = f"https://www.amazon.com.br/dp/{asin}"
                keepa_url = f"https://keepa.com/#!product/12-{asin}"
                
                message = (
                    f"📦 **Informações do Produto**\n\n"
                    f"**ASIN:** {asin}\n"
                    f"**Título:** {title}\n"
                    f"**Preço:** R$ {price}\n"
                    f"**Conta:** {acc_id}\n"
                    f"**Atualizado em:** {last_updated}\n\n"
                    f"**Links:**\n"
                    f"[Amazon]({amazon_url}) | [Keepa]({keepa_url})"
                )
                
                await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        
        if not found:
            await update.message.reply_text(f"❌ Produto {asin} não encontrado em nenhuma conta.")