#!/usr/bin/env python3
"""
Ponto de entrada principal para o Bot de Telegram do Amazon Keepa
"""
import os
import asyncio
import logging
from bot.handlers import setup_handlers
from config.settings import load_settings
from data.data_manager import clean_old_entries, load_post_info, save_post_info
from telegram.ext import Application
from utils.logger import setup_logging, get_logger
from utils.timezone_config import configure_timezone
from datetime import datetime, timedelta 
from utils.backup import create_backup, auto_cleanup_backups
from utils.missing_products import retrieve_missing_products
from keepa.browser_session_manager import browser_manager
from background_tasks import start_background_task_manager

# Configurar timezone para Brasil antes de qualquer operação
configure_timezone()

# Configurar logging aprimorado
setup_logging(console_output=True, file_output=True)
logger = get_logger(__name__)

async def retrieve_missing_products_on_startup(application, settings, post_info):
    """
    Recuperar produtos ausentes na inicialização
    """
    if settings.SOURCE_CHAT_ID:
        logger.info("Verificando posts de produtos ausentes...")
        try:
            updated_post_info = await retrieve_missing_products(
                application.bot,
                settings.SOURCE_CHAT_ID,
                post_info
            )
            
            # Salvar alterações, mesmo que não haja alterações aparentes
            # Isso garante que temos um arquivo de dados atualizado
            save_post_info(updated_post_info)
            
            # Verificar quantos posts foram adicionados
            new_count = len(updated_post_info) - len(post_info)
            if new_count > 0:
                logger.info(f"Informações de posts atualizadas com {new_count} produtos ausentes. Agora rastreando {len(updated_post_info)} posts")
            else:
                logger.info(f"Nenhum post de produto ausente encontrado. Mantendo {len(updated_post_info)} posts")
            
            return updated_post_info
        except Exception as e:
            logger.error(f"Erro ao recuperar produtos ausentes: {str(e)}")
            # Garantir que salvamos o estado atual mesmo em caso de erro
            save_post_info(post_info)
            return post_info
    return post_info

def main() -> None:
    """Iniciar o bot."""
    logger.info("Iniciando Bot de Telegram do Keepa...")
    
    # Carregar configurações
    settings = load_settings()
    logger.info("Configurações carregadas com sucesso")
    
    # Carregar e limpar dados
    post_info = load_post_info()
    post_info = clean_old_entries(post_info)
    save_post_info(post_info)
    logger.info(f"Dados carregados e limpos. Rastreando {len(post_info)} posts")
    
    # Criar backup na inicialização
    try:
        backup_path = create_backup()
        if backup_path:
            logger.info(f"Backup de inicialização criado com sucesso em: {backup_path}")
            deleted = auto_cleanup_backups(max_backups=10)
            if deleted > 0:
                logger.info(f"Limpeza automática: Removidos {deleted} backup(s) antigo(s)")
        else:
            logger.warning("Falha ao criar backup de inicialização")
    except Exception as e:
        logger.error(f"Erro ao criar backup de inicialização: {str(e)}")
    
    # Criar aplicação
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    logger.info("Aplicação do Telegram inicializada")
    
    # Configurar manipuladores
    setup_handlers(application)
    logger.info("Manipuladores configurados com sucesso")
    
    # Registrar a função de recuperação para ser executada após a inicialização
    async def startup_tasks(application):
        logger.info("Executando tarefas pós-inicialização...")
        await retrieve_missing_products_on_startup(application, settings, post_info)
        
        # Iniciar o gerenciador de tarefas em segundo plano
        await start_background_task_manager()
        logger.info("Gerenciador de tarefas em segundo plano iniciado")
    
    application.post_init = startup_tasks
    
    # Iniciar polling
    logger.info("Bot iniciado. Ouvindo por atualizações...")
    application.run_polling()
    
if __name__ == "__main__":
    main()