import os
import shutil
import tarfile
import glob
from utils.timezone_config import get_brazil_datetime
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)

def create_backup(backup_dir="/app/backups", data_dir="/app/data", logs_dir="/app/logs"):
    """
    Criar um backup abrangente dos dados e logs da aplicação
    
    Args:
        backup_dir (str): Diretório para armazenar backups
        data_dir (str): Diretório contendo dados da aplicação
        logs_dir (str): Diretório contendo logs da aplicação
        
    Returns:
        str: Caminho do arquivo de backup ou None se o backup falhar
    """
    try:
        # Garantir que o diretório de backup exista
        os.makedirs(backup_dir, exist_ok=True)
        
        # Criar um timestamp para o nome do arquivo de backup
        # Usar timezone do Brasil
        timestamp = get_brazil_datetime().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"keepa_bot_backup_{timestamp}.tar.gz"
        backup_path = os.path.join(backup_dir, backup_filename)
        
        logger.info(f"Criando backup abrangente: {backup_filename}")
        
        # Verificar possíveis localizações de post_info.json
        post_info_paths = [
            os.path.join(os.getcwd(), "post_info.json"),  # Raiz do projeto
            os.path.join(data_dir, "post_info.json"),     # Diretório de dados
            "/app/post_info.json"                         # Raiz do container
        ]
        
        post_info_path = None
        for path in post_info_paths:
            if os.path.exists(path):
                post_info_path = path
                logger.info(f"post_info.json encontrado em: {path}")
                break
        
        # Criar um tarball com dados, logs, e outros arquivos importantes
        with tarfile.open(backup_path, "w:gz") as tar:
            # Adicionar diretório de dados
            if os.path.exists(data_dir):
                logger.info(f"Adicionando diretório de dados ao backup: {data_dir}")
                tar.add(data_dir, arcname="data")
            
            # Adicionar diretório de logs
            if os.path.exists(logs_dir):
                logger.info(f"Adicionando diretório de logs ao backup: {logs_dir}")
                tar.add(logs_dir, arcname="logs")
            
            # Adicionar post_info.json especificamente (garantindo que seja incluído mesmo se não estiver no data_dir)
            if post_info_path:
                logger.info(f"Adicionando post_info.json ao backup de: {post_info_path}")
                tar.add(post_info_path, arcname="post_info.json")
            else:
                logger.warning("post_info.json não encontrado em nenhuma localização conhecida")
            
            # Adicionar arquivo .env (sem credenciais nos logs)
            env_path = os.path.join(os.getcwd(), ".env")
            if os.path.exists(env_path):
                logger.info(f"Adicionando configuração .env ao backup")
                tar.add(env_path, arcname=".env")
            
            # Adicionar quaisquer capturas de tela que possam ter sido geradas
            for screenshot in glob.glob(os.path.join(os.getcwd(), "*.png")):
                logger.info(f"Adicionando captura de tela ao backup: {os.path.basename(screenshot)}")
                tar.add(screenshot, arcname=os.path.basename(screenshot))
            
            # Procurar por post_info.json na raiz se não encontrado anteriormente
            if not post_info_path:
                for root, _, files in os.walk("/"):
                    for name in files:
                        if name == "post_info.json":
                            file_path = os.path.join(root, name)
                            if os.access(file_path, os.R_OK):
                                logger.info(f"Encontrado post_info.json em: {file_path}")
                                tar.add(file_path, arcname="post_info.json")
                                break
        
        logger.info(f"Backup abrangente criado com sucesso: {backup_path}")
        return backup_path
    
    except Exception as e:
        logger.error(f"Erro ao criar backup: {str(e)}")
        return None

# O resto do código permanece igual...
def list_backups(backup_dir="/app/backups"):
    """
    Listar todos os arquivos de backup no diretório de backup
    
    Args:
        backup_dir (str): Diretório contendo backups
        
    Returns:
        list: Lista de nomes de arquivos de backup com horários de criação
    """
    try:
        # Garantir que o diretório de backup exista
        os.makedirs(backup_dir, exist_ok=True)
        
        # Obter todos os arquivos .tar.gz no diretório de backup
        backup_files = []
        for filename in os.listdir(backup_dir):
            if filename.endswith(".tar.gz") and filename.startswith("keepa_bot_backup_"):
                file_path = os.path.join(backup_dir, filename)
                
                # Obter hora de criação do arquivo
                creation_time = os.path.getctime(file_path)
                creation_datetime = datetime.fromtimestamp(creation_time)
                
                # Obter tamanho do arquivo
                file_size = os.path.getsize(file_path)
                file_size_mb = file_size / (1024 * 1024)  # Converter para MB
                
                backup_files.append({
                    "filename": filename,
                    "path": file_path,
                    "creation_time": creation_datetime,
                    "size_mb": round(file_size_mb, 2)
                })
        
        # Ordenar por hora de criação (mais recentes primeiro)
        backup_files.sort(key=lambda x: x["creation_time"], reverse=True)
        
        return backup_files
    
    except Exception as e:
        logger.error(f"Erro ao listar backups: {str(e)}")
        return []

def delete_backup(backup_filename, backup_dir="/app/backups"):
    """
    Excluir um arquivo de backup específico
    
    Args:
        backup_filename (str): Nome do arquivo de backup a ser excluído
        backup_dir (str): Diretório contendo backups
        
    Returns:
        bool: True se a exclusão foi bem-sucedida, False caso contrário
    """
    try:
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # Verificar se o arquivo existe e é um arquivo de backup
        if not os.path.exists(backup_path):
            logger.error(f"Arquivo de backup não encontrado: {backup_filename}")
            return False
        
        if not backup_filename.startswith("keepa_bot_backup_") or not backup_filename.endswith(".tar.gz"):
            logger.error(f"Não é um arquivo de backup válido: {backup_filename}")
            return False
        
        # Excluir o arquivo
        os.remove(backup_path)
        logger.info(f"Backup excluído com sucesso: {backup_filename}")
        return True
    
    except Exception as e:
        logger.error(f"Erro ao excluir backup: {str(e)}")
        return False

def auto_cleanup_backups(backup_dir="/app/backups", max_backups=10):
    """
    Limpar automaticamente backups antigos, mantendo apenas os mais recentes
    
    Args:
        backup_dir (str): Diretório contendo backups
        max_backups (int): Número máximo de backups para manter
        
    Returns:
        int: Número de backups excluídos
    """
    try:
        backups = list_backups(backup_dir)
        
        # Se tivermos mais backups que o máximo, excluir os mais antigos
        if len(backups) > max_backups:
            # Obter os backups a serem excluídos (mais antigos primeiro)
            backups_to_delete = backups[max_backups:]
            
            # Excluir cada backup
            deleted_count = 0
            for backup in backups_to_delete:
                if delete_backup(backup["filename"], backup_dir):
                    deleted_count += 1
            
            logger.info(f"Limpeza automática excluiu {deleted_count} backups antigos")
            return deleted_count
        
        return 0
    
    except Exception as e:
        logger.error(f"Erro durante a limpeza automática: {str(e)}")
        return 0