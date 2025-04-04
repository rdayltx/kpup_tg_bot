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
    
    Procura por padrões como "R$ 99,99", "99.99", "2.672,10", etc.
    Normaliza para o formato com ponto decimal.
    """
    if not comment:
        return None
    
    logger.info(f"Tentando extrair preço do comentário: '{comment}'")
    
    # Primeiro tenta extrair qualquer número do texto
    price_patterns = [
        # Formato brasileiro com vírgula como decimal e possível ponto como separador de milhar
        r'R\$\s*([\d\.]+,\d+)',  # R$ 2.672,10 ou R$ 99,99
        r'([\d\.]+,\d+)',  # 2.672,10 ou 99,99 (sem R$)
        
        # Formato com ponto como decimal
        r'R\$\s*(\d+\.\d+)',  # R$ 99.99
        r'(\d+\.\d+)',  # 99.99 (sem R$)
        
        # Números inteiros
        r'R\$\s*(\d+)',  # R$ 99
        r'(\d+)',  # 99 (sem R$)
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, comment)
        if match:
            price_str = match.group(1)
            logger.info(f"Padrão de preço encontrado: '{price_str}'")
            
            # Se tiver vírgula, é formato brasileiro
            if ',' in price_str:
                # Remover pontos (separadores de milhar) e substituir vírgula por ponto
                normalized_price = price_str.replace('.', '').replace(',', '.')
                logger.info(f"Preço normalizado (formato BR): '{normalized_price}'")
                return normalized_price
            
            # Se já tiver ponto, já está no formato correto
            elif '.' in price_str:
                logger.info(f"Preço já no formato correto: '{price_str}'")
                return price_str
            
            # Se for número inteiro, adicionar .00
            else:
                logger.info(f"Preço inteiro normalizado: '{price_str}.00'")
                return price_str + ".00"
    
    # Se ainda não encontrou, procurar por padrões específicos no início do comentário (ASIN, preço)
    parts = comment.strip().split(',', 2)
    if len(parts) >= 2:
        # O segundo item deve ser o preço
        price_part = parts[1].strip()
        logger.info(f"Tentando extrair preço da segunda parte do comentário: '{price_part}'")
        
        # Tentar converter diretamente
        try:
            # Remover tudo que não é dígito, ponto ou vírgula
            price_part = re.sub(r'[^\d\.,]', '', price_part)
            
            # Se tiver vírgula, é formato brasileiro
            if ',' in price_part:
                normalized_price = price_part.replace('.', '').replace(',', '.')
                
                # Verificar se é um número válido
                float(normalized_price)  # Isso vai lançar ValueError se não for válido
                
                logger.info(f"Preço extraído da segunda parte: '{normalized_price}'")
                return normalized_price
            
            # Se já tiver ponto, já está no formato correto
            elif '.' in price_part:
                # Verificar se é um número válido
                float(price_part)  # Isso vai lançar ValueError se não for válido
                
                logger.info(f"Preço extraído da segunda parte (formato com ponto): '{price_part}'")
                return price_part
            
            # Se for apenas dígitos, adicionar .00
            elif price_part.isdigit():
                logger.info(f"Preço inteiro extraído da segunda parte: '{price_part}.00'")
                return price_part + ".00"
            
        except ValueError:
            logger.warning(f"Não foi possível converter para número: '{price_part}'")
    
    logger.warning(f"Nenhum padrão de preço encontrado em: '{comment}'")
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