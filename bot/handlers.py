import logging
import os
from telegram import Update, InputFile
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes
from config.settings import load_settings
from keepa.browser import initialize_driver
from keepa.api import login_to_keepa, update_keepa_product
from data.data_manager import load_post_info, save_post_info, clean_old_entries
# Import driver_sessions from message_processor to share the same sessions
from bot.message_processor import process_message, driver_sessions, post_info
# Import backup functionality
from utils.backup import create_backup, list_backups, delete_backup, auto_cleanup_backups

from utils.logger import get_logger

logger = get_logger(__name__)
settings = load_settings()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send message when the /start command is issued."""
    await update.message.reply_text("Bot started! I will capture ASINs, comments and update prices on Keepa.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current bot configuration status."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can check status.")
        return
    
    # Get available accounts
    accounts_info = "\n".join([f"• {account}" for account in settings.KEEPA_ACCOUNTS.keys()])
    if not accounts_info:
        accounts_info = "No accounts configured"
    
    status_message = (
        f"🤖 **Bot Status:**\n\n"
        f"💬 **Source Chat:** {settings.SOURCE_CHAT_ID or 'Not configured'}\n"
        f"📩 **Destination Chat:** {settings.DESTINATION_CHAT_ID or 'Not configured'}\n"
        f"👤 **Admin ID:** {settings.ADMIN_ID or 'Not configured'}\n"
        f"📊 **Tracked posts:** {len(post_info)}\n"
        f"🔐 **Keepa Accounts:**\n{accounts_info}\n"
        f"🔄 **Default Account:** {settings.DEFAULT_KEEPA_ACCOUNT}\n"
        f"🔄 **Update Alerts:** {'Yes' if settings.UPDATE_EXISTING_TRACKING else 'No'}"
    )
    
    await update.message.reply_text(status_message)

async def test_account_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test login for a specific Keepa account."""
    global driver_sessions
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can test accounts.")
        return
    
    try:
        args = context.args
        if not args:
            accounts_list = ", ".join(settings.KEEPA_ACCOUNTS.keys())
            await update.message.reply_text(f"❌ Please specify an account to test. Available accounts: {accounts_list}")
            return
        
        account_identifier = args[0]
        
        if account_identifier not in settings.KEEPA_ACCOUNTS:
            await update.message.reply_text(f"❌ Account '{account_identifier}' not found in configuration.")
            return
        
        await update.message.reply_text(f"Testing login for account '{account_identifier}'...")
        
        driver = initialize_driver()
        success = login_to_keepa(driver, account_identifier)
        
        if success:
            # Store the session for future use
            driver_sessions[account_identifier] = driver
            await update.message.reply_text(f"✅ Login successful for account '{account_identifier}'!")
        else:
            await update.message.reply_text(f"❌ Login failed for account '{account_identifier}'. Check the logs for details.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error testing account: {str(e)}")

async def start_keepa_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start Keepa session."""
    global driver_sessions
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can start the Keepa session.")
        return
    
    # Check if we have an account specified
    args = context.args
    account_identifier = args[0] if args else settings.DEFAULT_KEEPA_ACCOUNT
    
    await update.message.reply_text(f"Starting Keepa session for account '{account_identifier}'...")
    
    try:
        driver = initialize_driver()
        success = login_to_keepa(driver, account_identifier)
        
        if success:
            # Store the session for future use
            driver_sessions[account_identifier] = driver
            await update.message.reply_text(f"✅ Keepa session started successfully for account '{account_identifier}'!")
        else:
            await update.message.reply_text(f"❌ Failed to start Keepa session for account '{account_identifier}'. Check the logs.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error starting Keepa session: {str(e)}")

async def update_price_manual_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually update price for a product."""
    global driver_sessions
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can manually update prices.")
        return
    
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ Incorrect format. Use: /update ASIN PRICE [ACCOUNT]")
            return
        
        asin = args[0].upper()
        price = args[1]
        
        # Check if we have an account specified
        account_identifier = args[2] if len(args) > 2 else settings.DEFAULT_KEEPA_ACCOUNT
        
        await update.message.reply_text(f"Updating ASIN {asin} with price {price} using account '{account_identifier}'...")
        
        # Try to use existing session
        driver = driver_sessions.get(account_identifier)
        
        if driver is None:
            await update.message.reply_text(f"⚠️ Keepa session not started for account '{account_identifier}'. Starting...")
            driver = initialize_driver()
            success = login_to_keepa(driver, account_identifier)
            if not success:
                await update.message.reply_text(f"❌ Failed to start Keepa session for account '{account_identifier}'.")
                return
            driver_sessions[account_identifier] = driver
        
        success = update_keepa_product(driver, asin, price)
        
        if success:
            await update.message.reply_text(f"✅ ASIN {asin} updated successfully with account '{account_identifier}'!")
        else:
            await update.message.reply_text(f"❌ Failed to update ASIN {asin} with account '{account_identifier}'.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error updating price: {str(e)}")

async def list_accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all configured Keepa accounts."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can list accounts.")
        return
    
    if not settings.KEEPA_ACCOUNTS:
        await update.message.reply_text("❌ No Keepa accounts configured.")
        return
    
    accounts_info = "\n".join([f"• {account}" for account in settings.KEEPA_ACCOUNTS.keys()])
    message = (
        f"🔐 **Configured Keepa Accounts:**\n\n"
        f"{accounts_info}\n\n"
        f"Default account: {settings.DEFAULT_KEEPA_ACCOUNT}"
    )
    
    await update.message.reply_text(message)

async def clear_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear cache of tracked posts."""
    global post_info
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can use this command.")
        return
    
    post_info.clear()
    save_post_info(post_info)
    await update.message.reply_text("✅ Post cache cleared.")

async def close_sessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Close all browser sessions."""
    global driver_sessions
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can use this command.")
        return
    
    # Close all sessions
    for account, driver in driver_sessions.items():
        try:
            driver.quit()
            logger.info(f"Session closed for account: {account}")
        except Exception as e:
            logger.error(f"Error closing session for account {account}: {str(e)}")
    
    # Clear the sessions dictionary
    driver_sessions.clear()
    await update.message.reply_text("✅ All browser sessions closed.")

# New backup commands
async def create_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a backup of the bot data and logs."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can create backups.")
        return
    
    await update.message.reply_text("🔄 Creating backup... This may take a moment.")
    
    try:
        backup_path = create_backup()
        
        if backup_path:
            # Send the backup file
            with open(backup_path, 'rb') as backup_file:
                await update.message.reply_document(
                    document=InputFile(backup_file),
                    caption=f"✅ Backup created successfully: {os.path.basename(backup_path)}"
                )
            
            # Auto-cleanup old backups
            deleted = auto_cleanup_backups(max_backups=10)
            if deleted > 0:
                await update.message.reply_text(f"🧹 Auto-cleanup: Removed {deleted} old backup(s).")
        else:
            await update.message.reply_text("❌ Failed to create backup. Check the logs for details.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error creating backup: {str(e)}")

async def list_backups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all available backups."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can view backups.")
        return
    
    try:
        backups = list_backups()
        
        if not backups:
            await update.message.reply_text("📂 No backups found.")
            return
        
        # Format the backup list
        backup_list = []
        for i, backup in enumerate(backups, 1):
            creation_time = backup["creation_time"].strftime("%Y-%m-%d %H:%M:%S")
            backup_list.append(f"{i}. {backup['filename']} - {creation_time} - {backup['size_mb']} MB")
        
        await update.message.reply_text(
            f"📂 **Available Backups ({len(backups)}):**\n\n" + 
            "\n".join(backup_list) + 
            "\n\nTo download a backup, use: `/download_backup FILENAME`"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error listing backups: {str(e)}")

async def download_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download a specific backup file."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can download backups.")
        return
    
    try:
        args = context.args
        if not args:
            await update.message.reply_text("❌ Please specify a backup filename to download.")
            return
        
        filename = args[0]
        
        # Check if the file exists
        backup_dir = "/app/backups"
        backup_path = os.path.join(backup_dir, filename)
        
        if not os.path.exists(backup_path):
            # Try to list available backups
            backups = list_backups()
            available_files = "\n".join([f"• {b['filename']}" for b in backups[:5]])
            
            message = f"❌ Backup file not found: {filename}\n\n"
            if available_files:
                message += f"Available backups (showing max 5):\n{available_files}\n\nUse /list_backups for full list."
            else:
                message += "No backup files found."
            
            await update.message.reply_text(message)
            return
        
        # Send the backup file
        await update.message.reply_text(f"🔄 Preparing to send backup: {filename}")
        
        with open(backup_path, 'rb') as backup_file:
            await update.message.reply_document(
                document=InputFile(backup_file),
                caption=f"✅ Backup: {filename}"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error downloading backup: {str(e)}")

async def delete_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a specific backup file."""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Sorry, only the administrator can delete backups.")
        return
    
    try:
        args = context.args
        if not args:
            await update.message.reply_text("❌ Please specify a backup filename to delete.")
            return
        
        filename = args[0]
        
        # Delete the backup
        success = delete_backup(filename)
        
        if success:
            await update.message.reply_text(f"✅ Backup deleted successfully: {filename}")
        else:
            # Try to list available backups
            backups = list_backups()
            available_files = "\n".join([f"• {b['filename']}" for b in backups[:5]])
            
            message = f"❌ Failed to delete backup: {filename}\n\n"
            if available_files:
                message += f"Available backups (showing max 5):\n{available_files}\n\nUse /list_backups for full list."
            else:
                message += "No backup files found."
            
            await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"❌ Error deleting backup: {str(e)}")

def setup_handlers(application):
    """Set up all bot handlers"""
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("clear", clear_cache_command))
    application.add_handler(CommandHandler("start_keepa", start_keepa_command))
    application.add_handler(CommandHandler("update", update_price_manual_command))
    application.add_handler(CommandHandler("test_account", test_account_command))
    application.add_handler(CommandHandler("accounts", list_accounts_command))
    application.add_handler(CommandHandler("close_sessions", close_sessions_command))
    
    # Backup commands
    application.add_handler(CommandHandler("backup", create_backup_command))
    application.add_handler(CommandHandler("list_backups", list_backups_command))
    application.add_handler(CommandHandler("download_backup", download_backup_command))
    application.add_handler(CommandHandler("delete_backup", delete_backup_command))
    
    # Message handler
    application.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION, 
        process_message
    ))
    
    logger.info("Handlers set up")