import json
import os
import logging
from utils.timezone_config import get_brazil_datetime, datetime_to_isoformat
from config.settings import load_settings
from utils.logger import get_logger
from datetime import datetime, timedelta

logger = get_logger(__name__)
settings = load_settings()

class ProductDatabase:
    """
    Gerencia bancos de dados separados de produtos e preços por conta
    
    Cada conta tem seu próprio arquivo JSON:
    - /app/data/products_Premium.json
    - /app/data/products_Meraxes.json
    - etc.
    
    Estrutura de cada banco de dados:
    {
        "B07XYZ1234": {
            "price": "129.90",
            "last_updated": "2025-04-06T12:34:56",
            "product_title": "Nome do Produto"
        },
        ...
    }
    """
    
    def __init__(self, base_dir="/app/data"):
        """
        Inicializar o gerenciador de banco de dados
        
        Args:
            base_dir (str): Diretório base para armazenar os arquivos de banco de dados
        """
        self.data_dir = base_dir
        # Cache para databases carregados
        self.cached_databases = {}
        # Garantir que o diretório de dados exista
        os.makedirs(self.data_dir, exist_ok=True)
        
    def _get_db_file_path(self, account_id):
        """
        Obter o caminho do arquivo para uma conta específica
        
        Args:
            account_id (str): Identificador da conta
            
        Returns:
            str: Caminho completo do arquivo
        """
        return os.path.join(self.data_dir, f"products_{account_id}.json")
        
    def _load_account_database(self, account_id):
        """
        Carregar dados do arquivo JSON de uma conta específica
        
        Args:
            account_id (str): Identificador da conta
            
        Returns:
            dict: Dados carregados ou dicionário vazio se o arquivo não existir
        """
        try:
            # Verificar se já está em cache
            if account_id in self.cached_databases:
                return self.cached_databases[account_id]
                
            file_path = self._get_db_file_path(account_id)
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    data = json.load(f)
                    self.cached_databases[account_id] = data
                    return data
            # Se o arquivo não existe, inicializar com dicionário vazio
            self.cached_databases[account_id] = {}
            return {}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro ao carregar banco de dados para conta {account_id}: {str(e)}")
            self.cached_databases[account_id] = {}
            return {}
    
    def _save_account_database(self, account_id):
        """
        Salvar dados no arquivo JSON de uma conta específica
        
        Args:
            account_id (str): Identificador da conta
            
        Returns:
            bool: True se o salvamento foi bem-sucedido, False caso contrário
        """
        try:
            # Verificar se a conta está em cache
            if account_id not in self.cached_databases:
                logger.warning(f"Tentando salvar banco de dados não carregado para conta {account_id}")
                return False
                
            file_path = self._get_db_file_path(account_id)
            
            # Garantir que o diretório exista
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, "w") as f:
                json.dump(self.cached_databases[account_id], f, indent=2)
            
            logger.info(f"Banco de dados para conta {account_id} salvo com sucesso em {file_path}")
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar banco de dados para conta {account_id}: {str(e)}")
            return False
    
    def update_product(self, account_id, asin, price, product_title=None):
        """
        Atualizar informações de um produto
        
        Args:
            account_id (str): Identificador da conta
            asin (str): ASIN do produto
            price (str): Preço atualizado
            product_title (str, opcional): Título do produto
            
        Returns:
            bool: True se a atualização foi bem-sucedida, False caso contrário
        """
        try:
            # Carregar banco de dados da conta (ou criar se não existir)
            account_db = self._load_account_database(account_id)
            
            # Registrar o carregamento para diagnóstico
            logger.info(f"Banco de dados carregado para conta {account_id} com {len(account_db)} produtos")
            
            # Verificar se já existe esse produto
            old_price = None
            if asin in account_db:
                old_price = account_db.get(asin, {}).get("price")
                logger.info(f"Produto {asin} encontrado com preço atual: {old_price}")
            
            # Atualizar informações do produto
            account_db[asin] = {
                "price": price,
                "last_updated": datetime_to_isoformat(get_brazil_datetime()),
            }
            
            # Adicionar título do produto se fornecido
            if product_title:
                account_db[asin]["product_title"] = product_title
            
            # Atualizar o cache
            self.cached_databases[account_id] = account_db
            
            # Verificar estado do banco de dados antes de salvar
            logger.info(f"Banco de dados antes de salvar: {len(account_db)} produtos, contém {asin}: {asin in account_db}")
            
            # Salvar o banco de dados da conta explicitamente no arquivo
            try:
                file_path = self._get_db_file_path(account_id)
                
                # Garantir que o diretório exista
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                # Salvar diretamente no arquivo
                with open(file_path, "w") as f:
                    json.dump(account_db, f, indent=2)
                
                # Verificar se o arquivo foi salvo corretamente
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    logger.info(f"Arquivo salvo: {file_path}, tamanho: {file_size} bytes")
                
                logger.info(f"Banco de dados para conta {account_id} salvo explicitamente em {file_path}")
            except Exception as save_err:
                logger.error(f"Erro ao salvar arquivo para conta {account_id}: {str(save_err)}")
                return False
            
            # Registrar a atualização
            if old_price is not None:
                logger.info(f"Produto {asin} atualizado com sucesso para conta {account_id}. Preço: {old_price} -> {price}")
            else:
                logger.info(f"Produto {asin} adicionado com sucesso para conta {account_id}. Preço: {price}")
            
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar produto {asin} para conta {account_id}: {str(e)}")
            return False
    
    def delete_product(self, account_id, asin):
        """
        Excluir um produto do banco de dados
        
        Args:
            account_id (str): Identificador da conta
            asin (str): ASIN do produto
            
        Returns:
            bool: True se a exclusão foi bem-sucedida, False caso contrário
        """
        try:
            # Carregar banco de dados da conta
            account_db = self._load_account_database(account_id)
            
            # Verificar se o produto existe
            if asin in account_db:
                # Obter informações para log
                product_info = account_db[asin]
                
                # Excluir o produto
                del account_db[asin]
                
                # Salvar o banco de dados da conta
                save_result = self._save_account_database(account_id)
                
                # Registrar a exclusão
                logger.info(f"Produto {asin} excluído com sucesso para conta {account_id}. Preço anterior: {product_info.get('price')}")
                
                return save_result
            else:
                logger.warning(f"Produto {asin} não encontrado para conta {account_id}")
                return False
        except Exception as e:
            logger.error(f"Erro ao excluir produto {asin} para conta {account_id}: {str(e)}")
            return False
    
    def get_product(self, account_id, asin):
        """
        Obter informações de um produto
        
        Args:
            account_id (str): Identificador da conta
            asin (str): ASIN do produto
            
        Returns:
            dict: Informações do produto ou None se não encontrado
        """
        try:
            # Carregar banco de dados da conta
            account_db = self._load_account_database(account_id)
            
            # Verificar se o produto existe
            if asin in account_db:
                return account_db[asin]
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar produto {asin} para conta {account_id}: {str(e)}")
            return None
    
    def get_all_products(self, account_id=None):
        """
        Obter todos os produtos de uma conta ou de todas as contas
        
        Args:
            account_id (str, opcional): Identificador da conta ou None para todas
            
        Returns:
            dict: Dicionário com todos os produtos da conta ou de todas as contas
        """
        try:
            if account_id:
                # Retornar produtos de uma conta específica
                return self._load_account_database(account_id)
            else:
                # Retornar produtos de todas as contas
                result = {}
                # Obter todas as contas das configurações
                account_ids = settings.KEEPA_ACCOUNTS.keys()
                
                for acc_id in account_ids:
                    result[acc_id] = self._load_account_database(acc_id)
                return result
        except Exception as e:
            logger.error(f"Erro ao buscar produtos: {str(e)}")
            return {}
    
    def get_statistics(self):
        """
        Obter estatísticas do banco de dados
        
        Returns:
            dict: Dicionário com estatísticas (produtos por conta, total, etc.)
        """
        stats = {
            "total_products": 0,
            "accounts": {},
            "last_update": None
        }
        
        try:
            # Obter todas as contas das configurações
            account_ids = settings.KEEPA_ACCOUNTS.keys()
            
            for account_id in account_ids:
                # Carregar banco de dados da conta
                account_db = self._load_account_database(account_id)
                
                # Contar produtos
                product_count = len(account_db)
                stats["accounts"][account_id] = {
                    "product_count": product_count,
                    "last_update": None
                }
                stats["total_products"] += product_count
                
                # Encontrar última atualização da conta
                latest_update = None
                for asin, product_info in account_db.items():
                    update_time = product_info.get("last_updated")
                    if update_time:
                        if latest_update is None or update_time > latest_update:
                            latest_update = update_time
                
                stats["accounts"][account_id]["last_update"] = latest_update
                
                # Atualizar última atualização global
                if latest_update and (stats["last_update"] is None or latest_update > stats["last_update"]):
                    stats["last_update"] = latest_update
            
            return stats
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas do banco de dados: {str(e)}")
            return stats
            
    def import_database(self, json_file):
        """
        Importar banco de dados de produtos de um arquivo JSON
        
        Args:
            json_file (str): Caminho para o arquivo JSON
            
        Returns:
            bool: True se a importação foi bem-sucedida, False caso contrário
            dict: Estatísticas da importação (produtos importados, produtos por conta)
        """
        stats = {
            "success": False,
            "products_imported": 0,
            "accounts": {}
        }
        
        try:
            if not os.path.exists(json_file):
                logger.error(f"Arquivo não encontrado: {json_file}")
                return False, stats
            
            with open(json_file, "r") as f:
                imported_data = json.load(f)
            
            # Verificar se é um dicionário válido
            if not isinstance(imported_data, dict):
                logger.error(f"Formato inválido. Esperado um dicionário, recebido: {type(imported_data).__name__}")
                return False, stats
            
            # Contar produtos antes da importação
            before_stats = self.get_statistics()
            before_count = before_stats["total_products"]
            
            # Para cada conta no arquivo importado
            for account_id, products in imported_data.items():
                # Carregar banco de dados da conta
                account_db = self._load_account_database(account_id)
                
                # Contar produtos antes da importação para esta conta
                account_before = len(account_db)
                
                # Adicionar produtos ao banco de dados da conta
                account_db.update(products)
                
                # Salvar o banco de dados da conta
                self._save_account_database(account_id)
                
                # Contar produtos após a importação para esta conta
                account_after = len(account_db)
                account_imported = account_after - account_before
                
                # Registrar estatísticas para esta conta
                stats["accounts"][account_id] = account_imported
            
            # Calcular estatísticas globais
            after_stats = self.get_statistics()
            after_count = after_stats["total_products"]
            
            # Produtos realmente importados
            stats["products_imported"] = after_count - before_count
            stats["success"] = True
            
            logger.info(f"Banco de dados importado com sucesso. {stats['products_imported']} produtos importados")
            return True, stats
        except Exception as e:
            logger.error(f"Erro ao importar banco de dados: {str(e)}")
            return False, stats
    
    def clear_cache(self):
        """
        Limpar o cache de bancos de dados
        """
        self.cached_databases.clear()
        logger.info("Cache de bancos de dados limpo")

# Instância global do banco de dados
product_db = ProductDatabase()