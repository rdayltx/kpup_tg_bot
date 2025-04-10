import os
import logging
import tempfile
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from config.settings import load_settings
from utils.logger import get_logger
from background_tasks import task_manager
from utils.timezone_config import get_brazil_datetime, format_brazil_datetime  # Importações corretas

logger = get_logger(__name__)
settings = load_settings()

async def queue_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para adicionar produtos a partir de um arquivo .txt"""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Este comando é exclusivo para administradores.")
        return
    
    # Verificar se um arquivo foi enviado junto com o comando
    if not update.message.document and not context.bot_data.get('last_document'):
        await update.message.reply_text(
            "❌ Por favor, envie um arquivo .txt junto com o comando no formato:\n"
            "ASIN1,preço1\n"
            "ASIN2,preço2\n"
            "..."
        )
        return
    
    # Usar o documento anexado a esta mensagem ou o último documento enviado
    document = update.message.document
    if not document:
        # Tentar obter o último documento enviado
        document = context.bot_data.get('last_document')
        if not document:
            await update.message.reply_text("❌ Nenhum arquivo encontrado. Por favor, envie um arquivo .txt")
            return
    else:
        # Armazenar este documento para referência futura
        context.bot_data['last_document'] = document
    
    file_name = document.file_name
    
    # Verificar se é um arquivo .txt
    if not file_name.lower().endswith('.txt'):
        await update.message.reply_text("❌ Por favor, envie um arquivo no formato .txt")
        return
    
    await update.message.reply_text("🔄 Processando arquivo de produtos...")
    
    try:
        # Baixar o arquivo
        file = await context.bot.get_file(document.file_id)
        
        # Criar arquivo temporário
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Baixar para o arquivo temporário
        await file.download_to_drive(temp_path)
        
        # Adicionar à fila de tarefas
        added, skipped, queue_size = task_manager.add_tasks_from_file(temp_path)
        
        # Remover o arquivo temporário
        os.unlink(temp_path)
        
        # Iniciar o processador se não estiver rodando
        if not task_manager.is_running:
            await update.message.reply_text("🔄 Iniciando processador de tarefas em segundo plano...")
            import asyncio
            asyncio.create_task(task_manager.start_background_processing())
        
        await update.message.reply_text(
            f"✅ Arquivo processado com sucesso!\n\n"
            f"📊 Produtos adicionados à fila: {added}\n"
            f"⏭️ Produtos ignorados (já existentes): {skipped}\n"
            f"📋 Total na fila: {queue_size}\n\n"
            f"Os produtos serão adicionados automaticamente quando o bot estiver ocioso."
        )
        
    except Exception as e:
        logger.error(f"Erro ao processar arquivo de tarefas: {str(e)}")
        await update.message.reply_text(f"❌ Erro ao processar arquivo: {str(e)}")

async def tasks_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para verificar o status das tarefas em segundo plano"""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Este comando é exclusivo para administradores.")
        return
    
    status = task_manager.get_status()
    
    # Formatar última execução usando timezone do Brasil
    last_run_formatted = "Nunca"
    if status['last_run_time']:
        try:
            # Assumindo que last_run_time já está em formato ISO com timezone
            from datetime import datetime
            dt = datetime.fromisoformat(status['last_run_time'])
            last_run_formatted = format_brazil_datetime(dt)
        except:
            # Caso haja algum erro, mantém o valor original
            last_run_formatted = status['last_run_time']
    
    status_text = (
        f"📊 **Status das Tarefas em Segundo Plano**\n\n"
        f"🔄 Processador ativo: {'Sim' if status['is_running'] else 'Não'}\n"
        f"⏸️ Processamento pausado: {'Sim' if status['is_paused'] else 'Não'}\n"
        f"📋 Tarefas na fila: {status['queue_size']}\n"
        f"🔍 Tarefa atual: {status['current_task'] or 'Nenhuma'}\n\n"
        f"📈 **Estatísticas**\n"
        f"🔢 Total processado: {status['task_count']}\n"
        f"✅ Sucessos: {status['success_count']}\n"
        f"❌ Falhas: {status['fail_count']}\n"
        f"⏱️ Última execução: {last_run_formatted}"
    )
    
    if 'tasks_with_attempts' in status:
        status_text += f"\n📝 Tarefas com tentativas: {status['tasks_with_attempts']}"
    
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def pause_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para pausar o processamento de tarefas"""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Este comando é exclusivo para administradores.")
        return
    
    task_manager.pause_processing()
    
    # Informar horário usando timezone do Brasil
    horario_atual = format_brazil_datetime(get_brazil_datetime())
    
    await update.message.reply_text(
        f"⏸️ Processamento de tarefas pausado às {horario_atual}."
    )

async def resume_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para retomar o processamento de tarefas"""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Este comando é exclusivo para administradores.")
        return
    
    task_manager.resume_processing()
    
    # Iniciar o processador se não estiver rodando
    if not task_manager.is_running:
        import asyncio
        asyncio.create_task(task_manager.start_background_processing())
    
    # Informar horário usando timezone do Brasil
    horario_atual = format_brazil_datetime(get_brazil_datetime())
    
    await update.message.reply_text(
        f"▶️ Processamento de tarefas retomado às {horario_atual}."
    )

async def clear_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando para limpar a fila de tarefas"""
    if not settings.ADMIN_ID or str(update.effective_user.id) != settings.ADMIN_ID:
        await update.message.reply_text("Este comando é exclusivo para administradores.")
        return
    
    cleared = task_manager.clear_queue()
    
    # Informar horário usando timezone do Brasil
    horario_atual = format_brazil_datetime(get_brazil_datetime())
    
    await update.message.reply_text(
        f"🧹 Fila de tarefas limpa às {horario_atual}. {cleared} tarefas removidas."
    )

def register_task_handlers(application):
    """Registrar os manipuladores de comandos de tarefas"""
    application.add_handler(CommandHandler("queue_tasks", queue_tasks_command))
    application.add_handler(CommandHandler("tasks_status", tasks_status_command))
    application.add_handler(CommandHandler("pause_tasks", pause_tasks_command))
    application.add_handler(CommandHandler("resume_tasks", resume_tasks_command))
    application.add_handler(CommandHandler("clear_tasks", clear_tasks_command))
    
    logger.info("Manipuladores de comandos de tarefas registrados")