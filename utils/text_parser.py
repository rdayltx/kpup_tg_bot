import re
import logging

from utils.logger import get_logger

logger = get_logger(__name__)

def extract_asin_from_text(text):
    """
    Extrair ASIN da Amazon do texto
    """
    if not text:
        return None
        
    # Padrão regex para URLs da Amazon
    amazon_url_pattern = r'https?://(?:www\.)?amazon\.com\.br/(?:[^/]+/)?(?:dp|gp/product|gp/aw/d|exec/obidos/asin|o)/([A-Z0-9]{10})'
    
    amazon_match = re.search(amazon_url_pattern, text)
    if amazon_match:
        return amazon_match.group(1).upper()
    
    # Também procurar por ASINs puros no texto (só por garantia)
    asin_pattern = r'\b([A-Z0-9]{10})\b'
    asin_match = re.search(asin_pattern, text)
    if asin_match:
        return asin_match.group(1)
    
    return None

def extract_source_from_text(text):
    """
    Extrair informação da fonte do texto
    """
    if not text:
        return "Desconhecido"
        
    # Padrão regex para fonte
    source_pattern = r'Fonte:\s*(\w+)'
    
    source_match = re.search(source_pattern, text)
    if source_match:
        return source_match.group(1)
    
    return "Desconhecido"

def extract_price_from_comment(comment):
    """
    Extrair preço do texto do comentário
    
    Procura por padrões como "R$ 99,99", "99.99", etc.
    Adiciona ".00" para números inteiros.
    """
    if not comment:
        return None
        
    # Padrões comuns de preço para valores decimais
    decimal_patterns = [
        r'R\$\s*(\d+[,.]\d+)',  # R$ 99,99 ou R$ 99.99
        r'(\d+[,.]\d+)\s*reais',  # 99,99 reais ou 99.99 reais
        r'(\d+[,.]\d+)',  # 99,99 ou 99.99 (genérico)
    ]
    
    # Padrões para valores inteiros
    integer_patterns = [
        r'R\$\s*(\d+)(?![,.]\d)',  # R$ 99 (sem decimal)
        r'(\d+)\s*reais(?![,.]\d)',  # 99 reais (sem decimal)
        r'(?<!\d[,.])(\d+)(?![,.]\d)',  # 99 (inteiro genérico)
    ]
    
    # Verificar padrões decimais primeiro
    for pattern in decimal_patterns:
        match = re.search(pattern, comment)
        if match:
            price = match.group(1).replace(',', '.')  # Normalizar para formato com ponto
            return price
    
    # Então verificar padrões inteiros
    for pattern in integer_patterns:
        match = re.search(pattern, comment)
        if match:
            return match.group(1) + ".00"  # Adicionar ".00" para valores inteiros
    
    # Se nenhum padrão corresponder
    return None

def extract_account_identifier(comment):
    """
    Extrair identificador de conta do comentário
    
    Formato: "ASIN, preço, identificador"
    O identificador é a terceira parte após a segunda vírgula
    """
    if not comment:
        return None
    
    logger.info(f"Extraindo identificador de conta de: '{comment}'")
    
    # Dividir por vírgula e verificar se temos pelo menos 3 partes
    parts = comment.strip().split(',')
    if len(parts) >= 3:
        # O identificador é a terceira parte, sem espaços em branco
        identifier = parts[2].strip()
        logger.info(f"Identificador de conta encontrado: '{identifier}'")
        return identifier
    
    logger.info("Nenhum identificador de conta encontrado no comentário")
    return None