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

MAX_PRODUCTS_PER_ACCOUNT = 4995

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
            cls._instance.task_metadata = {}  # Novo: armazenar metadados de tentativas por tarefa
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
        # Limpar também os metadados de tarefas
        self.task_metadata = {}
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
            "tasks_with_attempts": len(self.task_metadata) if hasattr(self, 'task_metadata') else 0
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
            
            # Inicializar metadados para esta tarefa se não existir
            task_key = f"{asin}_{price}"
            if not hasattr(self, 'task_metadata'):
                self.task_metadata = {}
                
            if task_key not in self.task_metadata:
                self.task_metadata[task_key] = {
                    'attempts': 0,
                    'tried_accounts': set(),
                    'accounts_with_limit': set(),  # Nova propriedade para contas com limite atingido
                    'last_attempt': None
                }
            
            # Atualizar metadados da tarefa
            self.task_metadata[task_key]['attempts'] += 1
            self.task_metadata[task_key]['last_attempt'] = datetime.now()
            
            # Verificar se atingiu número máximo de tentativas
            max_attempts = 5  # Limite de tentativas para o mesmo ASIN
            if self.task_metadata[task_key]['attempts'] > max_attempts:
                logger.warning(f"ASIN {asin} excedeu o limite de {max_attempts} tentativas. Removendo da fila.")
                self.fail_count += 1
                if task_key in self.task_metadata:
                    del self.task_metadata[task_key]
                self.save_queue()
                return True  # Tarefa processada (descartada por excesso de tentativas)
            
            try:
                logger.info(f"Processando tarefa: adicionar ASIN {asin} com preço {price} (tentativa {self.task_metadata[task_key]['attempts']})")
                
                # Algoritmo para escolher conta menos utilizada
                accounts_usage = {}
                eligible_accounts = []
                tried_accounts = self.task_metadata[task_key]['tried_accounts']
                accounts_with_limit = self.task_metadata[task_key]['accounts_with_limit']
                
                # Verificar cada conta e sua contagem de produtos
                for account_id in settings.KEEPA_ACCOUNTS.keys():
                    # Pular contas que já foram tentadas para este ASIN
                    if account_id in tried_accounts and len(tried_accounts) < len(settings.KEEPA_ACCOUNTS):
                        logger.info(f"Pulando conta {account_id} pois já foi tentada para o ASIN {asin}")
                        continue
                    
                    # Pular contas que já atingiram o limite para este ASIN
                    if account_id in accounts_with_limit:
                        logger.info(f"Pulando conta {account_id} pois já atingiu o limite de rastreamento para o ASIN {asin}")
                        continue
                        
                    products = product_db.get_all_products(account_id)
                    product_count = len(products) if products else 0
                    accounts_usage[account_id] = product_count
                    
                    # Verificar se está abaixo do limite seguro
                    if product_count < MAX_PRODUCTS_PER_ACCOUNT:
                        eligible_accounts.append((account_id, product_count))
                
                # Verificar se há contas elegíveis
                if not eligible_accounts:
                    # Se já tentamos todas as contas disponíveis ou todas atingiram limite
                    total_accounts = len(settings.KEEPA_ACCOUNTS)
                    if len(tried_accounts) + len(accounts_with_limit) >= total_accounts:
                        logger.warning(f"Todas as contas foram tentadas ou atingiram limite para ASIN {asin}. Removendo da fila.")
                        self.fail_count += 1
                        if task_key in self.task_metadata:
                            del self.task_metadata[task_key]
                        return True  # Tarefa processada (falha em todas as contas)
                    else:
                        logger.warning("Todas as contas elegíveis atingiram o limite seguro de produtos. Recolocando na fila.")
                        self.queue.append((asin, price))
                        self.save_queue()
                        # Pausar o processamento temporariamente para evitar ciclos infinitos
                        self.is_paused = True
                        logger.info("Processamento de tarefas pausado devido a todas as contas estarem no limite")
                        return False
                
                # Ordenar contas elegíveis pelo número de produtos (menos produtos primeiro)
                eligible_accounts.sort(key=lambda x: x[1])
                
                # Selecionar uma conta que não tenha sido tentada anteriormente se possível
                untried_accounts = [(acc_id, count) for acc_id, count in eligible_accounts 
                                    if acc_id not in tried_accounts]
                
                # Escolher uma conta das não tentadas, ou das elegíveis se todas já foram tentadas
                selection_pool = untried_accounts if untried_accounts else eligible_accounts
                
                # Escolher uma conta aleatória entre as 3 menos utilizadas (se disponíveis)
                selection_pool = selection_pool[:min(3, len(selection_pool))]
                chosen_account, current_count = random.choice(selection_pool)
                
                # Adicionar à lista de contas tentadas
                self.task_metadata[task_key]['tried_accounts'].add(chosen_account)
                
                logger.info(f"Escolhida conta {chosen_account} com {current_count}/{MAX_PRODUCTS_PER_ACCOUNT} produtos (tentativa {self.task_metadata[task_key]['attempts']})")
                
                # Verificação final para garantir que não ultrapassamos o limite
                if current_count >= MAX_PRODUCTS_PER_ACCOUNT:
                    logger.warning(f"Conta {chosen_account} atingiu limite de produtos. Recolocando na fila.")
                    # Recolocar na fila
                    self.queue.append((asin, price))
                    self.save_queue()
                    return False
                
                # Verificar se o produto já existe
                if product_db.get_product(chosen_account, asin):
                    logger.info(f"ASIN {asin} já existe na conta {chosen_account}")
                    self.success_count += 1
                    if task_key in self.task_metadata:
                        del self.task_metadata[task_key]
                    return True
                
                # Obter uma sessão do navegador
                session = await browser_manager.get_session(chosen_account)
                
                if session and session.is_logged_in:
                    # Usar a sessão existente
                    success, product_title, error_code = update_keepa_product(session.driver, asin, price)
                    
                    if success:
                        # Adicionar ao banco de dados
                        product_db.update_product(chosen_account, asin, price, product_title)
                        logger.info(f"✅ ASIN {asin} adicionado com sucesso à conta {chosen_account}")
                        self.success_count += 1
                        # Limpar metadados já que teve sucesso
                        if task_key in self.task_metadata:
                            del self.task_metadata[task_key]
                    else:
                        logger.error(f"❌ Falha ao adicionar ASIN {asin} à conta {chosen_account}")
                        
                        # Verificar código de erro específico
                        if error_code == "LIMIT_REACHED":
                            logger.warning(f"Conta {chosen_account} atingiu limite de rastreamento (5000). "
                                        f"Marcando como não elegível e tentando outra conta na próxima execução.")
                            # Adicionar à lista de contas com limite atingido para este ASIN
                            self.task_metadata[task_key]['accounts_with_limit'].add(chosen_account)
                            # Recolocar na fila para tentar com outra conta
                            self.queue.append((asin, price))
                        elif error_code == "PAGE_ERROR":
                            logger.warning(f"Erro de página para ASIN {asin}. Tentando novamente mais tarde.")
                            # Recolocar no final da fila
                            self.queue.append((asin, price))
                            self.fail_count += 1
                        elif error_code == "FORM_ERROR":
                            logger.warning(f"Erro no formulário para ASIN {asin}. Tentando novamente mais tarde.")
                            # Recolocar no final da fila
                            self.queue.append((asin, price))
                            self.fail_count += 1
                        else:
                            # Erro genérico
                            logger.warning(f"Erro não categorizado para ASIN {asin}. Tentando novamente mais tarde.")
                            self.queue.append((asin, price))
                            self.fail_count += 1
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
                    logger.info("Processamento pausado. Verificando novamente em 30 segundos.")
                    await asyncio.sleep(30)
                    continue
                
                # Verificar se há tarefas na fila
                if not self.queue:
                    logger.debug("Fila vazia, aguardando 30 segundos")
                    await asyncio.sleep(30)
                    continue
                
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