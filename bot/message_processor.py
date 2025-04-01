import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config.settings import load_settings
from data.data_manager import load_post_info, save_post_info
from utils.text_parser import extract_asin_from_text, extract_source_from_text, extract_price_from_comment
from keepa.browser import initialize_driver
from keepa.api import login_to_keepa, update_keepa_product

from utils.logger import get_logger

logger = get_logger(__name__)
settings = load_settings()

# Initialize global variables
# This will be shared with handlers.py
driver_sessions = {}
post_info = load_post_info()

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process messages from channel/group and identify posts and comments."""
    global post_info, driver_sessions
    
    if not settings.SOURCE_CHAT_ID:
        return

    message = update.message or update.channel_post
    if not message:
        return

    # Check if message comes from the correct group/channel
    effective_chat_id = str(update.effective_chat.id)
    sender_chat_id = str(message.sender_chat.id) if message.sender_chat else None

    if effective_chat_id != settings.SOURCE_CHAT_ID and sender_chat_id != settings.SOURCE_CHAT_ID:
        return

    message_id = message.message_id
    message_text = message.text or message.caption or ""

    logger.info(f"Processing message {message_id}: {message_text[:50]}...")

    # Extract ASIN and source if this is a product post
    asin = extract_asin_from_text(message_text)
    
    if asin:
        source = extract_source_from_text(message_text)
        logger.info(f"Post with ASIN found: {asin}, Source: {source}")
        
        # Store original post with ASIN, Source and timestamp
        post_info[str(message_id)] = {
            "asin": asin,
            "source": source,
            "timestamp": datetime.now().isoformat()
        }
        save_post_info(post_info)
    
    # Check if this is a comment on a tracked post
    elif message.reply_to_message:
        replied_message = message.reply_to_message
        replied_message_id = str(replied_message.message_id)

        # Check if original post is tracked
        if replied_message_id in post_info:
            asin = post_info[replied_message_id]["asin"]
            source = post_info[replied_message_id]["source"]
            comment = message_text.strip()
            
            logger.info(f"Comment identified for ASIN {asin}: {comment}")
            logger.info(f"Source from original post: {source}")
            
            # Extract price from comment
            price = extract_price_from_comment(comment)
            
            # Use source as account identifier if it exists in our accounts
            account_identifier = None
            if source in settings.KEEPA_ACCOUNTS:
                account_identifier = source
                logger.info(f"Using source as account identifier: {account_identifier}")
            else:
                # If source is not a valid account, check if there's a third part in the comment
                parts = comment.strip().split(',')
                if len(parts) >= 3:
                    potential_account = parts[2].strip()
                    if potential_account in settings.KEEPA_ACCOUNTS:
                        account_identifier = potential_account
                        logger.info(f"Using comment part as account identifier: {account_identifier}")
            
            # If still no valid account, use default
            if not account_identifier:
                account_identifier = settings.DEFAULT_KEEPA_ACCOUNT
                logger.info(f"No valid account found, using default: {account_identifier}")
            
            if price:
                logger.info(f"Price extracted from comment: {price}")
                
                # Update price on Keepa
                update_success = False
                driver = None
                
                # Check if we have an existing session for this account
                if account_identifier in driver_sessions:
                    driver = driver_sessions[account_identifier]
                    try:
                        # Test if session is still valid
                        driver.current_url
                        update_success = update_keepa_product(driver, asin, price)
                    except Exception as e:
                        logger.warning(f"Existing session for '{account_identifier}' is invalid: {str(e)}")
                        # Session expired or browser crashed, we'll create a new one
                        driver = None
                
                # Initialize driver if needed
                if driver is None:
                    try:
                        driver = initialize_driver(account_identifier)
                        login_success = login_to_keepa(driver, account_identifier)
                        
                        if login_success:
                            # Store the session for future use
                            driver_sessions[account_identifier] = driver
                            
                            update_success = update_keepa_product(driver, asin, price)
                            if update_success:
                                logger.info(f"✅ ASIN {asin} successfully updated on Keepa with price {price} using account {account_identifier}")
                                
                                # Notify admin
                                if settings.ADMIN_ID:
                                    await context.bot.send_message(
                                        chat_id=settings.ADMIN_ID,
                                        text=f"✅ ASIN {asin} updated with price {price} using account {account_identifier}"
                                    )
                            else:
                                logger.error(f"❌ Failed to update ASIN {asin} on Keepa")
                                
                                # Notify admin
                                if settings.ADMIN_ID:
                                    await context.bot.send_message(
                                        chat_id=settings.ADMIN_ID,
                                        text=f"❌ Failed to update ASIN {asin} on Keepa using account {account_identifier}"
                                    )
                        else:
                            logger.error(f"❌ Failed to login to Keepa with account {account_identifier}")
                            
                            # Notify admin
                            if settings.ADMIN_ID:
                                await context.bot.send_message(
                                    chat_id=settings.ADMIN_ID,
                                    text=f"❌ Failed to login to Keepa with account {account_identifier}"
                                )
                    except Exception as e:
                        logger.error(f"❌ Error updating price on Keepa: {str(e)}")
                        
                        # Notify admin
                        if settings.ADMIN_ID:
                            await context.bot.send_message(
                                chat_id=settings.ADMIN_ID,
                                text=f"❌ Error updating price on Keepa with account {account_identifier}: {str(e)}"
                            )
                
                # Format message as requested: "ASIN, Comment, Source"
                result_message = f"{asin}, {comment}, {source}"
                
                # Send to destination group
                try:
                    if settings.DESTINATION_CHAT_ID:
                        await context.bot.send_message(
                            chat_id=settings.DESTINATION_CHAT_ID,
                            text=result_message
                        )
                        logger.info(f"Information sent to chat {settings.DESTINATION_CHAT_ID}")
                except Exception as e:
                    logger.error(f"Error sending message to destination group: {e}")
                    if settings.ADMIN_ID:
                        await context.bot.send_message(
                            chat_id=settings.ADMIN_ID,
                            text=f"❌ Error sending message to destination group: {e}"
                        )
            else:
                logger.warning(f"⚠️ Could not extract price from comment: {comment}")
                
                # Notify admin
                if settings.ADMIN_ID:
                    await context.bot.send_message(
                        chat_id=settings.ADMIN_ID,
                        text=f"⚠️ Could not extract price from comment for ASIN {asin}: {comment}"
                    )