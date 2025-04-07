import random
import logging
from telegram import Update
from telegram.ext import ContextTypes
from config.settings import load_settings
from data.product_database import product_db
from utils.logger import get_logger
from keepa.browser import initialize_driver
from keepa.api import login_to_keepa, update_keepa_product
from utils.retry import async_retry
from telegram.ext import CommandHandler
from keepa.browser_session_manager import browser_manager

logger = get_logger(__name__)
settings = load_settings()

@async_retry(max_attempts=2)
async def add_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adicionar produto aleatoriamente a uma conta que não tenha atingido o limite de 4999 produtos."""
    
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Desculpe, apenas o administrador pode adicionar produtos.")
        return
    
    MAX_PRODUCTS_PER_ACCOUNT = 4999
    
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
        
        # Obter estatísticas atuais do banco de dados
        stats = product_db.get_statistics()
        
        # Filtrar contas abaixo do limite
        available_accounts = []
        for account_id, account_stats in stats["accounts"].items():
            product_count = account_stats["product_count"]
            if product_count < MAX_PRODUCTS_PER_ACCOUNT:
                available_accounts.append((account_id, product_count))
        
        if not available_accounts:
            await update.message.reply_text("❌ Todas as contas atingiram o limite de 4999 produtos.")
            return
        
        # Ordenar contas pelo número de produtos (menos produtos primeiro)
        available_accounts.sort(key=lambda x: x[1])
        
        # Selecionar aleatoriamente uma conta dentre as 3 menos utilizadas (se disponíveis)
        selection_pool = available_accounts[:min(3, len(available_accounts))]
        chosen_account, current_count = random.choice(selection_pool)
        
        await update.message.reply_text(f"🔄 Adicionando ASIN {asin} com preço {price} à conta '{chosen_account}' (atualmente com {current_count} produtos)...")
        
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
                
                await update.message.reply_text(product_info, parse_mode="Markdown", disable_web_page_preview=True)
            else:
                await update.message.reply_text(f"❌ Falha ao adicionar ASIN {asin} à conta '{chosen_account}'.")
        else:
            # Criar uma nova instância de driver para esta operação
            driver = initialize_driver(chosen_account)
            
            try:
                success = login_to_keepa(driver, chosen_account)
                if not success:
                    await update.message.reply_text(f"❌ Falha ao fazer login no Keepa com conta '{chosen_account}'.")
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
                    
                    await update.message.reply_text(product_info, parse_mode="Markdown", disable_web_page_preview=True)
                else:
                    await update.message.reply_text(f"❌ Falha ao adicionar ASIN {asin} à conta '{chosen_account}'.")
            finally:
                # Importante: Sempre encerrar o driver para liberar recursos
                # Só fechamos o driver se criamos um novo (não fechamos o driver gerenciado pelo SessionManager)
                if driver and not session:
                    try:
                        driver.quit()
                        logger.info(f"Sessão do driver Chrome fechada para conta {chosen_account}")
                    except Exception as e:
                        logger.error(f"Erro ao fechar o driver Chrome: {str(e)}")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao adicionar produto: {str(e)}")
        # Repassar a exceção para o mecanismo de retry
        raise
    
command_add_product = add_product_command
