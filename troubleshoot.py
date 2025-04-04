if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""
Script de solução de problemas para testar a atualização de produtos Keepa
"""
import sys
import os
import time
import logging
import argparse
from dotenv import load_dotenv

# Adicionar o diretório atual ao path para importar os módulos
sys.path.append(os.getcwd())

# Configurar logging básico durante a inicialização
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("troubleshoot.log")
    ]
)

logger = logging.getLogger("troubleshoot")

def main():
    """Função principal"""
    # Carregar variáveis de ambiente
    load_dotenv()
    
    # Definir argumentos de linha de comando
    parser = argparse.ArgumentParser(description='Testar funcionalidades do bot Keepa')
    parser.add_argument('--action', required=True, choices=['login', 'update', 'delete'], 
                        help='Ação a ser executada')
    parser.add_argument('--asin', help='ASIN do produto (obrigatório para update e delete)')
    parser.add_argument('--price', help='Preço a ser definido (obrigatório para update)')
    parser.add_argument('--account', help='Identificador da conta (opcional, usa a padrão se não especificado)')
    
    args = parser.parse_args()
    
    # Importar depois de carregar as variáveis de ambiente para garantir configuração correta
    from config.settings import load_settings
    from keepa.browser import initialize_driver
    from keepa.api import login_to_keepa, update_keepa_product, delete_keepa_tracking
    from utils.logger import setup_logging, get_logger
    
    # Configurar logging aprimorado
    setup_logging(console_output=True, file_output=True)
    logger = get_logger(__name__)
    
    # Carregar configurações
    settings = load_settings()
    
    # Validar argumentos
    if args.action in ['update', 'delete'] and not args.asin:
        logger.error("ASIN é obrigatório para ações de update e delete")
        return 1
    
    if args.action == 'update' and not args.price:
        logger.error("Preço é obrigatório para a ação de update")
        return 1
    
    # Definir o identificador de conta
    account_identifier = args.account or settings.DEFAULT_KEEPA_ACCOUNT
    
    if account_identifier not in settings.KEEPA_ACCOUNTS:
        logger.error(f"Conta '{account_identifier}' não encontrada na configuração")
        return 1
    
    # Inicializar o driver
    try:
        logger.info(f"Iniciando driver para a conta {account_identifier}")
        driver = initialize_driver(account_identifier)
        
        # Tentar fazer login
        logger.info(f"Tentando fazer login com a conta {account_identifier}")
        login_success = login_to_keepa(driver, account_identifier)
        
        if not login_success:
            logger.error(f"Falha ao fazer login no Keepa com a conta {account_identifier}")
            return 1
        
        logger.info(f"Login bem-sucedido com a conta {account_identifier}")
        
        # Executar a ação solicitada
        if args.action == 'login':
            logger.info("Login concluído com sucesso")
            
        elif args.action == 'update':
            logger.info(f"Atualizando ASIN {args.asin} com preço {args.price}")
            success, product_title = update_keepa_product(driver, args.asin, args.price)
            
            if success:
                logger.info(f"✅ ASIN {args.asin} atualizado com sucesso!")
                if product_title:
                    logger.info(f"Título do produto: {product_title}")
            else:
                logger.error(f"❌ Falha ao atualizar ASIN {args.asin}")
                return 1
                
        elif args.action == 'delete':
            logger.info(f"Excluindo rastreamento para ASIN {args.asin}")
            success, product_title = delete_keepa_tracking(driver, args.asin)
            
            if success:
                logger.info(f"✅ Rastreamento do ASIN {args.asin} excluído com sucesso!")
                if product_title:
                    logger.info(f"Título do produto: {product_title}")
            else:
                logger.error(f"❌ Falha ao excluir rastreamento do ASIN {args.asin}")
                return 1
        
        return 0
        
    except Exception as e:
        logger.error(f"Erro durante a execução: {str(e)}")
        return 1
    
    finally:
        # Garantir que o driver seja fechado
        if 'driver' in locals():
            try:
                driver.quit()
                logger.info("Driver fechado com sucesso")
            except Exception as e:
                logger.error(f"Erro ao fechar o driver: {str(e)}")