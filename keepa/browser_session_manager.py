import os
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
from selenium.webdriver import Chrome

from utils.logger import get_logger
from keepa.browser import initialize_driver
from keepa.api import login_to_keepa
from config.settings import load_settings

logger = get_logger(__name__)
settings = load_settings()

class BrowserSession:
    """Classe para gerenciar uma sessão de navegador Chrome"""
    
    def __init__(self, account_identifier: str, driver: Chrome):
        self.account_identifier = account_identifier
        self.driver = driver
        self.last_used = datetime.now()
        self.is_logged_in = False
    
    def refresh_timestamp(self):
        """Atualizar o timestamp de último uso"""
        self.last_used = datetime.now()
    
    def is_expired(self, max_idle_time: int = 3600) -> bool:
        """
        Verificar se a sessão está expirada (não usada por muito tempo)
        
        Args:
            max_idle_time: Tempo máximo de inatividade em segundos (padrão: 1 hora)
            
        Returns:
            bool: True se a sessão estiver expirada, False caso contrário
        """
        idle_time = (datetime.now() - self.last_used).total_seconds()
        return idle_time > max_idle_time
    
    def close(self):
        """Fechar a sessão do navegador"""
        try:
            if self.driver:
                self.driver.quit()
                logger.info(f"Sessão de navegador fechada para conta: {self.account_identifier}")
        except Exception as e:
            logger.error(f"Erro ao fechar sessão de navegador para conta {self.account_identifier}: {str(e)}")

class BrowserSessionManager:
    """Gerenciador de sessões de navegador para diferentes contas"""
    
    def __init__(self):
        self.sessions: Dict[str, BrowserSession] = {}
        self.cleanup_running = False
    
    async def get_session(self, account_identifier: str) -> Optional[BrowserSession]:
        """
        Obter uma sessão de navegador para a conta especificada
        Se a sessão não existir ou estiver expirada, cria uma nova
        
        Args:
            account_identifier: Identificador da conta
            
        Returns:
            BrowserSession: Sessão de navegador para a conta
        """
        # Verificar se já temos uma sessão válida
        if account_identifier in self.sessions:
            session = self.sessions[account_identifier]
            
            # Verificar se a sessão está expirada
            if session.is_expired():
                logger.info(f"Sessão expirada para conta {account_identifier}, criando nova sessão")
                session.close()
                del self.sessions[account_identifier]
            else:
                # Atualizar timestamp e retornar sessão existente
                session.refresh_timestamp()
                return session
        
        # Criar nova sessão
        try:
            logger.info(f"Criando nova sessão de navegador para conta {account_identifier}")
            driver = initialize_driver(account_identifier)
            
            # Tentar fazer login
            login_success = login_to_keepa(driver, account_identifier)
            
            if login_success:
                logger.info(f"Login bem-sucedido para conta {account_identifier}")
                session = BrowserSession(account_identifier, driver)
                session.is_logged_in = True
                self.sessions[account_identifier] = session
                
                # Iniciar limpeza automática se ainda não estiver rodando
                if not self.cleanup_running:
                    asyncio.create_task(self._background_cleanup())
                
                return session
            else:
                logger.error(f"Falha no login para conta {account_identifier}, fechando driver")
                driver.quit()
                return None
                
        except Exception as e:
            logger.error(f"Erro ao criar sessão para conta {account_identifier}: {str(e)}")
            return None
    
    def close_session(self, account_identifier: str) -> bool:
        """
        Fechar uma sessão específica
        
        Args:
            account_identifier: Identificador da conta
            
        Returns:
            bool: True se a sessão foi fechada com sucesso, False caso contrário
        """
        if account_identifier in self.sessions:
            try:
                self.sessions[account_identifier].close()
                del self.sessions[account_identifier]
                logger.info(f"Sessão fechada para conta {account_identifier}")
                return True
            except Exception as e:
                logger.error(f"Erro ao fechar sessão para conta {account_identifier}: {str(e)}")
                return False
        return False
    
    def close_all_sessions(self) -> int:
        """
        Fechar todas as sessões
        
        Returns:
            int: Número de sessões fechadas
        """
        count = 0
        for account_id in list(self.sessions.keys()):
            if self.close_session(account_id):
                count += 1
        
        logger.info(f"{count} sessões de navegador fechadas")
        return count
    
    async def _background_cleanup(self):
        """
        Tarefa em background para limpar sessões expiradas periodicamente
        """
        self.cleanup_running = True
        try:
            while True:
                # Verificar sessões a cada 15 minutos
                await asyncio.sleep(15 * 60)
                
                closed_count = 0
                for account_id in list(self.sessions.keys()):
                    if self.sessions[account_id].is_expired():
                        if self.close_session(account_id):
                            closed_count += 1
                
                if closed_count > 0:
                    logger.info(f"Limpeza automática: {closed_count} sessões expiradas fechadas")
        except Exception as e:
            logger.error(f"Erro na limpeza automática de sessões: {str(e)}")
        finally:
            self.cleanup_running = False

# Instância global do gerenciador de sessões
browser_manager = BrowserSessionManager()