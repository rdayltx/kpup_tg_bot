import os
from datetime import datetime, timedelta, timezone
import pytz

# Definir o timezone do Brasil (Brasília)
BRAZIL_TIMEZONE = pytz.timezone('America/Sao_Paulo')

def configure_timezone():
    """
    Configurar o timezone do sistema para o Brasil (Brasília)
    """
    # Definir a variável de ambiente TZ
    os.environ['TZ'] = 'America/Sao_Paulo'
    
    # Registrar a configuração de timezone
    print(f"Timezone configurado para: America/Sao_Paulo (UTC-3)")
    
    return True

def get_brazil_datetime():
    """
    Obter a data e hora atual no timezone do Brasil (Brasília)
    
    Returns:
        datetime: Data e hora atual no timezone do Brasil
    """
    return datetime.now(BRAZIL_TIMEZONE)

def format_brazil_datetime(dt):
    """
    Formatar uma data para o formato brasileiro
    
    Args:
        dt: Objeto datetime
        
    Returns:
        str: Data formatada
    """
    # Garantir que a data esteja no timezone correto
    if dt.tzinfo is None:
        dt = BRAZIL_TIMEZONE.localize(dt)
    elif dt.tzinfo != BRAZIL_TIMEZONE:
        dt = dt.astimezone(BRAZIL_TIMEZONE)
    
    # Formatar a data para o formato brasileiro
    return dt.strftime("%d/%m/%Y %H:%M:%S")

def localize_datetime(dt):
    """
    Converter uma datetime sem timezone para o timezone do Brasil
    
    Args:
        dt: Objeto datetime sem timezone
        
    Returns:
        datetime: Objeto datetime com timezone do Brasil
    """
    if dt.tzinfo is None:
        return BRAZIL_TIMEZONE.localize(dt)
    return dt.astimezone(BRAZIL_TIMEZONE)

def datetime_to_isoformat(dt):
    """
    Converter datetime para string ISO format no timezone do Brasil
    
    Args:
        dt: Objeto datetime
        
    Returns:
        str: String ISO format
    """
    localized_dt = localize_datetime(dt)
    return localized_dt.isoformat()