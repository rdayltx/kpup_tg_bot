import random
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler
from config.settings import load_settings
from data.product_database import product_db
from utils.logger import get_logger
from keepa.browser import initialize_driver
from keepa.api import login_to_keepa, update_keepa_product
from utils.retry import async_retry
from keepa.browser_session_manager import browser_manager

logger = get_logger(__name__)
settings = load_settings()

# Adicionar um handler para callbacks de botões inline
async def add_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manipulador de callback para botões no comando add_product."""
    query = update.callback_query
    await query.answer()
    
    # Extrair dados do callback
    data = query.data.split('_')
    action = data[0]
    asin = data[1]
    price = data[2]
    
    if action == "update":
        # O usuário escolheu atualizar o produto existente
        existing_account = data[3]
        await query.edit_message_text(f"Atualizando ASIN {asin} com preço {price} na conta existente '{existing_account}'...")
        
        # Usar o processo existente para atualizar o produto
        success, product_title = await update_product_in_account(context, existing_account, asin, price)
        
        if success:
            amazon_url = f"https://www.amazon.com.br/dp/{asin}"
            keepa_url = f"https://keepa.com/#!product/12-{asin}"
            
            product_info = f"✅ ASIN {asin} atualizado com sucesso!\n\n"
            if product_title:
                product_info += f"📦 Produto: {product_title}\n"
            product_info += f"💰 Preço atualizado: R$ {price}\n"
            product_info += f"🔐 Conta: {existing_account}\n\n"
            product_info += f"🔗 Links: [Amazon]({amazon_url}) | [Keepa]({keepa_url})"
            
            await query.edit_message_text(product_info, parse_mode="Markdown", disable_web_page_preview=True)
        else:
            await query.edit_message_text(f"❌ Falha ao atualizar ASIN {asin} na conta '{existing_account}'.")
    
    elif action == "force":
        # O usuário escolheu forçar a adição como um novo produto
        await query.edit_message_text(f"Adicionando ASIN {asin} com preço {price} em uma nova conta...")
        
        # Chamar a função para adicionar em uma nova conta
        await add_new_product(update, context, asin, price, is_query=True, query=query)
    
    elif action == "cancel":
        # O usuário cancelou a operação
        await query.edit_message_text("Operação cancelada pelo usuário.")

@async_retry(max_attempts=2)
async def update_product_in_account(context, account_id, asin, price):
    """Atualizar produto em uma conta específica."""
    session = await browser_manager.get_session(account_id)
    driver = None
    
    if session and session.is_logged_in:
        driver = session.driver
        logger.info(f"Usando sessão existente para a conta {account_id}")
        
        success, product_title = update_keepa_product(driver, asin, price)
        
        if success:
            # Atualizar o banco de dados de produtos
            product_db.update_product(account_id, asin, price, product_title)
            logger.info(f"✅ Banco de dados de produtos atualizado para ASIN {asin}, conta {account_id}")
            return True, product_title
        else:
            return False, None
    else:
        # Criar uma nova instância de driver para esta operação
        driver = initialize_driver(account_id)
        
        try:
            success = login_to_keepa(driver, account_id)
            if not success:
                logger.error(f"❌ Falha ao fazer login no Keepa com conta '{account_id}'.")
                return False, None
            
            success, product_title = update_keepa_product(driver, asin, price)
            
            if success:
                # Atualizar o banco de dados de produtos
                product_db.update_product(account_id, asin, price, product_title)
                logger.info(f"✅ Banco de dados de produtos atualizado para ASIN {asin}, conta {account_id}")
                return True, product_title
            else:
                return False, None
        finally:
            # Importante: Sempre encerrar o driver para liberar recursos
            # Só fechamos o driver se criamos um novo (não fechamos o driver gerenciado pelo SessionManager)
            if driver and not session:
                try:
                    driver.quit()
                    logger.info(f"Sessão do driver Chrome fechada para conta {account_id}")
                except Exception as e:
                    logger.error(f"Erro ao fechar o driver Chrome: {str(e)}")
                    
    return False, None

async def add_new_product(update, context, asin, price, is_query=False, query=None):
    """Adicionar um novo produto a uma conta aleatória."""
    MAX_PRODUCTS_PER_ACCOUNT = 4999
    
    # Obter estatísticas atuais do banco de dados
    stats = product_db.get_statistics()
    
    # Filtrar contas abaixo do limite
    available_accounts = []
    for account_id, account_stats in stats["accounts"].items():
        product_count = account_stats["product_count"]
        if product_count < MAX_PRODUCTS_PER_ACCOUNT:
            available_accounts.append((account_id, product_count))
    
    if not available_accounts:
        message = "❌ Todas as contas atingiram o limite de 4999 produtos."
        if is_query:
            await query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return
    
    # Ordenar contas pelo número de produtos (menos produtos primeiro)
    available_accounts.sort(key=lambda x: x[1])
    
    # Selecionar aleatoriamente uma conta dentre as 3 menos utilizadas (se disponíveis)
    selection_pool = available_accounts[:min(3, len(available_accounts))]
    chosen_account, current_count = random.choice(selection_pool)
    
    message = f"🔄 Adicionando ASIN {asin} com preço {price} à conta '{chosen_account}' (atualmente com {current_count} produtos)..."
    if is_query:
        await query.edit_message_text(message)
    else:
        await update.message.reply_text(message)
    
    # Tentar usar uma sessão existente do gerenciador
    session = await browser_manager.get_session(chosen_account)
    driver = None
    
    if session and session.is_logged_in:
        driver = session.driver
        logger.info(f"Usando sessão existente para a conta {chosen_account}")
        
        success, product_title = update_keepa_product(driver, asin, price)
        
        if success:
            # Atualizar o banco de dados de produtos
            product_db.update_product(chosen_account, asin, price, product_title)
            logger.info(f"✅ Banco de dados de produtos atualizado para ASIN {asin}, conta {chosen_account}")
            
            # Obter URL da Amazon e Keepa para o produto
            amazon_url = f"https://www.amazon.com.br/dp/{asin}"
            keepa_url = f"https://keepa.com/#!product/12-{asin}"
            
            product_info = f"✅ ASIN {asin} adicionado com sucesso!\n\n"
            if product_title:
                product_info += f"📦 Produto: {product_title}\n"
            product_info += f"💰 Preço: R$ {price}\n"
            product_info += f"🔐 Conta: {chosen_account}\n"
            product_info += f"📊 Status: {current_count + 1}/{MAX_PRODUCTS_PER_ACCOUNT} produtos\n\n"
            product_info += f"🔗 Links: [Amazon]({amazon_url}) | [Keepa]({keepa_url})"
            
            if is_query:
                await query.edit_message_text(product_info, parse_mode="Markdown", disable_web_page_preview=True)
            else:
                await update.message.reply_text(product_info, parse_mode="Markdown", disable_web_page_preview=True)
        else:
            message = f"❌ Falha ao adicionar ASIN {asin} à conta '{chosen_account}'."
            if is_query:
                await query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
    else:
        # Criar uma nova instância de driver para esta operação
        driver = initialize_driver(chosen_account)
        
        try:
            success = login_to_keepa(driver, chosen_account)
            if not success:
                message = f"❌ Falha ao fazer login no Keepa com conta '{chosen_account}'."
                if is_query:
                    await query.edit_message_text(message)
                else:
                    await update.message.reply_text(message)
                return
            
            success, product_title = update_keepa_product(driver, asin, price)
            
            if success:
                # Atualizar o banco de dados de produtos
                product_db.update_product(chosen_account, asin, price, product_title)
                logger.info(f"✅ Banco de dados de produtos atualizado para ASIN {asin}, conta {chosen_account}")
                
                # Obter URL da Amazon e Keepa para o produto
                amazon_url = f"https://www.amazon.com.br/dp/{asin}"
                keepa_url = f"https://keepa.com/#!product/12-{asin}"
                
                product_info = f"✅ ASIN {asin} adicionado com sucesso!\n\n"
                if product_title:
                    product_info += f"📦 Produto: {product_title}\n"
                product_info += f"💰 Preço: R$ {price}\n"
                product_info += f"🔐 Conta: {chosen_account}\n"
                product_info += f"📊 Status: {current_count + 1}/{MAX_PRODUCTS_PER_ACCOUNT} produtos\n\n"
                product_info += f"🔗 Links: [Amazon]({amazon_url}) | [Keepa]({keepa_url})"
                
                if is_query:
                    await query.edit_message_text(product_info, parse_mode="Markdown", disable_web_page_preview=True)
                else:
                    await update.message.reply_text(product_info, parse_mode="Markdown", disable_web_page_preview=True)
            else:
                message = f"❌ Falha ao adicionar ASIN {asin} à conta '{chosen_account}'."
                if is_query:
                    await query.edit_message_text(message)
                else:
                    await update.message.reply_text(message)
        finally:
            # Importante: Sempre encerrar o driver para liberar recursos
            # Só fechamos o driver se criamos um novo (não fechamos o driver gerenciado pelo SessionManager)
            if driver and not session:
                try:
                    driver.quit()
                    logger.info(f"Sessão do driver Chrome fechada para conta {chosen_account}")
                except Exception as e:
                    logger.error(f"Erro ao fechar o driver Chrome: {str(e)}")

@async_retry(max_attempts=2)
async def add_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adicionar produto aleatoriamente a uma conta que não tenha atingido o limite de 4999 produtos, verificando duplicação."""
    
    # if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
    #     await update.message.reply_text("Desculpe, apenas o administrador pode adicionar produtos.")
    #     return
    
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ Formato incorreto. Use: /add ASIN PREÇO")
            return
        
        asin = args[0].upper()
        price = args[1]
        
        # Verificar formato do preço (converter para garantir que está em formato correto)
        try:
            # Verificar se é convertível para float
            float_price = float(price.replace(',', '.'))
            # Converter de volta para string com 2 casas decimais
            price = f"{float_price:.2f}"
            # Garantir que usa . como separador decimal (não ,)
            price = price.replace(",", ".")
        except ValueError:
            await update.message.reply_text(f"❌ Preço inválido: {price}. Use formato numérico como 99.90")
            return
        
        # Verificar se o produto já existe em alguma conta
        existing_account = None
        product_info = None
        
        # Buscar em todas as contas
        for acc_id in settings.KEEPA_ACCOUNTS.keys():
            product_data = product_db.get_product(acc_id, asin)
            if product_data:
                existing_account = acc_id
                product_info = product_data
                break
        
        if existing_account:
            # Produto já existe, perguntar o que fazer
            current_price = product_info.get("price", "?")
            title = product_info.get("product_title", "Produto")
            
            # Criar teclado inline com opções
            keyboard = [
                [
                    InlineKeyboardButton("Atualizar Preço", callback_data=f"update_{asin}_{price}_{existing_account}"),
                    InlineKeyboardButton("Adicionar Mesmo Assim", callback_data=f"force_{asin}_{price}"),
                ],
                [InlineKeyboardButton("Cancelar", callback_data=f"cancel_{asin}_{price}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Mostrar mensagem informativa com botões
            await update.message.reply_text(
                f"⚠️ Este produto já existe na conta '{existing_account}'!\n\n"
                f"📦 Produto: {title}\n"
                f"🏷️ ASIN: {asin}\n"
                f"💰 Preço atual: R$ {current_price}\n"
                f"💰 Novo preço: R$ {price}\n\n"
                f"O que deseja fazer?",
                reply_markup=reply_markup
            )
        else:
            # Produto não existe, adicionar normalmente
            await add_new_product(update, context, asin, price)
    
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao adicionar produto: {str(e)}")
        # Repassar a exceção para o mecanismo de retry
        raise

# Função para registrar os handlers
def register_product_handlers(application):
    """Registrar handlers para comandos de produto"""
    application.add_handler(CallbackQueryHandler(add_product_callback, pattern=r'^(update|force|cancel)_'))