#!/usr/bin/env python3
"""
Main entry point for the Amazon Keepa Telegram Bot
"""
import os
from bot.handlers import setup_handlers
from config.settings import load_settings
from data.data_manager import clean_old_entries, load_post_info, save_post_info
from telegram.ext import Application
from utils.logger import setup_logging, get_logger

# Configure enhanced logging
setup_logging(console_output=True, file_output=True)
logger = get_logger(__name__)

def main() -> None:
    """Start the bot."""
    logger.info("Starting Keepa Telegram Bot...")
    
    # Load settings
    settings = load_settings()
    logger.info("Settings loaded successfully")
    
    # Load and clean data
    post_info = load_post_info()
    post_info = clean_old_entries(post_info)
    save_post_info(post_info)
    logger.info(f"Data loaded and cleaned. Tracking {len(post_info)} posts")
    
    # Create application
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    logger.info("Telegram application initialized")
    
    # Setup handlers
    setup_handlers(application)
    logger.info("Handlers set up successfully")
    
    # Start polling
    logger.info("Bot started. Listening for updates...")
    application.run_polling()

if __name__ == "__main__":
    main()