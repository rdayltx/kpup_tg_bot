import asyncio
import os
import time
import random
import logging
from datetime import datetime, timedelta
from config.settings import load_settings
from data.product_database import product_db
from keepa.browser_session_manager import browser_manager
from keepa.api import update_keepa_product
from utils.logger import get_logger

logger = get_logger(__name__)
settings = load_settings()

# Singleton para gerenciar tarefas em background
class BackgroundTaskManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BackgroundTaskManager, cls).__new__(cls)
            cls._instance.is_running = False
            cls._instance.is_paused = False
            cls._instance.queue = []
            cls._instance.current_task = None
            cls._instance.task_count = 0
            cls._instance.success_count = 0
            cls._instance.fail_count = 0
            cls._instance.last_run_time = None
            cls._instance.task_lock = asyncio.Lock()
            cls._instance.queue_file = "/app/data/task_queue.txt"
            cls._instance.load_queue()
        return cls._instance
    
    def load_queue(self):
        """Carregar a fila de tarefas do arquivo"""
        try:
            if os.path.exists(self.queue_file):
                with open(self.queue_file, "r") as f:
                    lines = f.readlines()
                    
                for line in lines:
                    line = line.strip()
                    if line:
                        parts = line.split(",")
                        if len(parts) >= 2:
                            asin = parts[0].strip()
                            price = parts[1].strip()
                            self.queue.append((asin, price))
                
                logger.info(f"Fila de tarefas carregada com {len(self.queue)} itens")
        except Exception as e:
            logger.error(f"Erro ao carregar fila de tarefas: {str(e)}")
    
    def save_queue(self):
        """Salvar a fila de tarefas em um arquivo"""
        try:
            os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
            with open(self.queue_file, "w") as f:
                for asin, price in self.queue:
                    f.write(f"{asin},{price}\n")
            logger.info(f"Fila de tarefas salva com {len(self.queue)} itens restantes")
        except Exception as e:
            logger.error(f"Erro ao salvar fila de tarefas: {str(e)}")
    
    def add_task(self, asin, price):
        """Adicionar uma tarefa à fila"""
        self.queue.append((asin, price))
        self.save_queue()
        return len(self.queue)
    
    def add_tasks_from_file(self, file_path):
        """Adicionar tarefas de um arquivo de texto"""
        added_count = 0
        skipped_count = 0
        
        try:
            with open(file_path, "r") as f:
                lines = f.readlines()
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                    
                parts = line.split(",")
                if len(parts) >= 2:
                    asin = parts[0].strip().upper()
                    price = parts[1].strip().replace(",", ".")
                    
                    # Verificar se o produto já existe em alguma conta
                    exists = False
                    for account in settings.KEEPA_ACCOUNTS.keys():
                        if product_db.get_product(account, asin):
                            exists = True
                            skipped_count += 1
                            break
                    
                    if not exists:
                        self.add_task(asin, price)
                        added_count += 1
            
            self.save_queue()
            return added_count, skipped_count, len(self.queue)
        except Exception as e:
            logger.error(f"Erro ao adicionar tarefas do arquivo: {str(e)}")
            return 0, 0, len(self.queue)
    
    def clear_queue(self):
        """Limpar a fila de tarefas"""
        queue_length = len(self.queue)
        self.queue = []
        self.save_queue()
        return queue_length
    
    def pause_processing(self):
        """Pausar o processamento de tarefas"""
        self.is_paused = True
        logger.info("Processamento de tarefas pausado")
        return True
    
    def resume_processing(self):
        """Retomar o processamento de tarefas"""
        self.is_paused = False
        logger.info("Processamento de tarefas retomado")
        return True
    
    def get_status(self):
        """Obter status atual do processador de tarefas"""
        return {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "queue_size": len(self.queue),
            "current_task": self.current_task,
            "task_count": self.task_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "last_run_time": self.last_run_time,
        }
    
    async def process_single_task(self):
        """Processar uma única tarefa da fila"""
        if not self.queue or self.is_paused:
            return False
        
        async with self.task_lock:
            if not self.queue:
                return False
            
            asin, price = self.queue.pop(0)
            self.current_task = f"{asin} ({price})"
            self.task_count += 1
            
            try:
                logger.info(f"Processando tarefa: adicionar ASIN {asin} com preço {price}")
                
                # Algoritmo para escolher conta menos utilizada
                accounts_usage = {}
                for account_id in settings.KEEPA_ACCOUNTS.keys():
                    products = product_db.get_all_products(account_id)
                    accounts_usage[account_id] = len(products) if products else 0
                
                # Ordenar contas pelo número de produtos (menos produtos primeiro)
                sorted_accounts = sorted(accounts_usage.items(), key=lambda x: x[1])
                
                # Escolher uma conta aleatória entre as 3 menos utilizadas (se disponíveis)
                selection_pool = sorted_accounts[:min(3, len(sorted_accounts))]
                chosen_account, current_count = random.choice(selection_pool)
                
                logger.info(f"Escolhida conta {chosen_account} com {current_count} produtos")
                
                # Verificar se o produto já existe
                if product_db.get_product(chosen_account, asin):
                    logger.info(f"ASIN {asin} já existe na conta {chosen_account}")
                    self.success_count += 1
                    return True
                
                # Obter uma sessão do navegador
                session = await browser_manager.get_session(chosen_account)
                
                if session and session.is_logged_in:
                    # Usar a sessão existente
                    success, product_title = update_keepa_product(session.driver, asin, price)
                    
                    if success:
                        # Adicionar ao banco de dados
                        product_db.update_product(chosen_account, asin, price, product_title)
                        logger.info(f"✅ ASIN {asin} adicionado com sucesso à conta {chosen_account}")
                        self.success_count += 1
                    else:
                        logger.error(f"❌ Falha ao adicionar ASIN {asin} à conta {chosen_account}")
                        self.fail_count += 1
                        # Recolocar na fila para tentar novamente depois
                        self.queue.append((asin, price))
                else:
                    logger.error(f"❌ Não foi possível obter sessão válida para conta {chosen_account}")
                    self.fail_count += 1
                    # Recolocar na fila para tentar novamente depois
                    self.queue.append((asin, price))
                
                # Salvar a fila atualizada
                self.save_queue()
                
                # Registrar o horário da última execução
                self.last_run_time = datetime.now().isoformat()
                
                return True
                
            except Exception as e:
                logger.error(f"Erro ao processar tarefa para ASIN {asin}: {str(e)}")
                self.fail_count += 1
                # Recolocar na fila para tentar novamente depois
                self.queue.append((asin, price))
                self.save_queue()
                return False
    
    async def start_background_processing(self):
        """Iniciar o processamento de tarefas em segundo plano"""
        if self.is_running:
            logger.info("O processador de tarefas já está em execução")
            return False
        
        self.is_running = True
        logger.info("Iniciando processador de tarefas em segundo plano")
        
        try:
            # Loop principal de processamento
            while self.is_running:
                # Verificar se o processamento está pausado
                if self.is_paused:
                    await asyncio.sleep(10)
                    continue
                
                # Verificar se há tarefas na fila
                if not self.queue:
                    logger.debug("Fila vazia, aguardando 30 segundos")
                    await asyncio.sleep(30)
                    continue
                
                # Verificar se o bot está ocioso (sem atividade recente)
                # Aqui usamos um valor fixo, mas poderia verificar atividade do bot
                # Processar uma tarefa
                await self.process_single_task()
                
                # Pausa entre tarefas (5-10 segundos)
                await asyncio.sleep(random.uniform(5, 10))
        
        except Exception as e:
            logger.error(f"Erro no processador de tarefas: {str(e)}")
        finally:
            self.is_running = False
            logger.info("Processador de tarefas finalizado")
            
            # Salvar a fila atual
            self.save_queue()

# Instância global
task_manager = BackgroundTaskManager()

# Função para iniciar o processador de tarefas durante a inicialização do bot
async def start_background_task_manager():
    """Iniciar o gerenciador de tarefas em segundo plano"""
    asyncio.create_task(task_manager.start_background_processing())
    logger.info("Gerenciador de tarefas em segundo plano iniciado")