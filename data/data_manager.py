import json
import os
import shutil
from datetime import datetime, timedelta
from utils.timezone_config import get_brazil_datetime, localize_datetime
from config.settings import load_settings
from utils.logger import get_logger

# Inicializar logger
logger = get_logger(__name__)

# Carregar configurações
settings = load_settings()

def load_post_info():
    """
    Carregar dados do arquivo JSON
    """
    try:
        with open(settings.DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_post_info(post_info):
    """
    Salvar dados no arquivo JSON e criar cópia local
    """
    # Salvar no local padrão (dentro do container)
    with open(settings.DATA_FILE, "w") as f:
        json.dump(post_info, f, indent=2)
    
    # Criar uma cópia em um local alternativo mapeado ao host
    try:
        # Definir locais alternativos para salvar o arquivo
        local_copies = [
            "/app/data/post_info.json",  # Diretório de dados mapeado ao host
            "./data/post_info.json"      # Caso o caminho relativo esteja configurado
        ]
        
        # Tentar salvar em cada um dos locais alternativos
        for local_path in local_copies:
            try:
                # Garantir que o diretório exista
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                
                # Copiar o arquivo ou salvar diretamente
                if os.path.exists(settings.DATA_FILE):
                    shutil.copy2(settings.DATA_FILE, local_path)
                else:
                    with open(local_path, "w") as f:
                        json.dump(post_info, f, indent=2)
                
                logger.info(f"Cópia local de post_info.json criada em: {local_path}")
            except Exception as copy_err:
                logger.warning(f"Não foi possível criar cópia local em {local_path}: {str(copy_err)}")
    except Exception as e:
        logger.error(f"Erro ao criar cópias locais de post_info.json: {str(e)}")

def clean_old_entries(post_info):
    """
    Limpar entradas com mais de 2 dias
    """
    now = get_brazil_datetime()
    two_days_ago = now - timedelta(days=2)
    cleaned_info = {}
    
    for msg_id, data in post_info.items():
        try:
            timestamp = data["timestamp"]
            # Converter string ISO para datetime
            if isinstance(timestamp, str):
                try:
                    # Tentar converter com timezone
                    timestamp_dt = datetime.fromisoformat(timestamp)
                    # Localizar para o timezone do Brasil se não tiver timezone
                    timestamp_dt = localize_datetime(timestamp_dt)
                except ValueError:
                    # Fallback para o formato antigo
                    import dateutil.parser
                    timestamp_dt = dateutil.parser.parse(timestamp)
                    timestamp_dt = localize_datetime(timestamp_dt)
            else:
                # Já é um objeto datetime
                timestamp_dt = localize_datetime(timestamp)
                
            if timestamp_dt >= two_days_ago:
                cleaned_info[msg_id] = data
        except Exception as e:
            logger.error(f"Erro ao processar timestamp para mensagem {msg_id}: {str(e)}")
            # Manter a entrada por segurança
            cleaned_info[msg_id] = data
            
    return cleaned_info