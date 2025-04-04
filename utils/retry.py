import functools
import asyncio
import time
import random
from utils.logger import get_logger

logger = get_logger(__name__)

def async_retry(max_attempts=3, delay=5, backoff=2, jitter=0.1):
    """
    Decorador para repetir funções assíncronas em caso de falha com backoff exponencial.
    
    Args:
        max_attempts (int): Número máximo de tentativas
        delay (int): Atraso inicial entre tentativas em segundos
        backoff (float): Fator de multiplicação do atraso a cada tentativa
        jitter (float): Fator de aleatoriedade para evitar concorrência (entre 0 e 1)
        
    Returns:
        Função decorada com mecanismo de retry
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            attempt = 1
            
            while attempt <= max_attempts:
                try:
                    if attempt > 1:
                        logger.info(f"Tentativa {attempt}/{max_attempts} para {func.__name__}")
                    
                    return await func(*args, **kwargs)
                    
                except Exception as e:
                    last_exception = e
                    wait_time = delay * (backoff ** (attempt - 1))
                    
                    # Adicionar variação aleatória (jitter)
                    jitter_amount = wait_time * jitter
                    wait_time = wait_time + random.uniform(-jitter_amount, jitter_amount)
                    
                    logger.warning(f"Tentativa {attempt}/{max_attempts} para {func.__name__} falhou: {str(e)}")
                    
                    if attempt < max_attempts:
                        logger.info(f"Aguardando {wait_time:.2f} segundos antes da próxima tentativa...")
                        await asyncio.sleep(wait_time)
                
                attempt += 1
            
            # Se chegou aqui, todas as tentativas falharam
            logger.error(f"Todas as {max_attempts} tentativas para {func.__name__} falharam")
            raise last_exception
            
        return wrapper
    return decorator

def sync_retry(max_attempts=3, delay=5, backoff=2, jitter=0.1):
    """
    Decorador para repetir funções síncronas em caso de falha com backoff exponencial.
    
    Args:
        max_attempts (int): Número máximo de tentativas
        delay (int): Atraso inicial entre tentativas em segundos
        backoff (float): Fator de multiplicação do atraso a cada tentativa
        jitter (float): Fator de aleatoriedade para evitar concorrência (entre 0 e 1)
        
    Returns:
        Função decorada com mecanismo de retry
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            attempt = 1
            
            while attempt <= max_attempts:
                try:
                    if attempt > 1:
                        logger.info(f"Tentativa {attempt}/{max_attempts} para {func.__name__}")
                    
                    return func(*args, **kwargs)
                    
                except Exception as e:
                    last_exception = e
                    wait_time = delay * (backoff ** (attempt - 1))
                    
                    # Adicionar variação aleatória (jitter)
                    jitter_amount = wait_time * jitter
                    wait_time = wait_time + random.uniform(-jitter_amount, jitter_amount)
                    
                    logger.warning(f"Tentativa {attempt}/{max_attempts} para {func.__name__} falhou: {str(e)}")
                    
                    if attempt < max_attempts:
                        logger.info(f"Aguardando {wait_time:.2f} segundos antes da próxima tentativa...")
                        time.sleep(wait_time)
                
                attempt += 1
            
            # Se chegou aqui, todas as tentativas falharam
            logger.error(f"Todas as {max_attempts} tentativas para {func.__name__} falharam")
            raise last_exception
            
        return wrapper
    return decorator