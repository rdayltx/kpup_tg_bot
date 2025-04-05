import re
import logging

from utils.logger import get_logger

logger = get_logger(__name__)


def should_ignore_message(text):
    """
    Verifica se a mensagem contém palavras-chave que devem ser ignoradas pelo bot.
    
    Args:
        text (str): Texto da mensagem a ser verificado
        
    Returns:
        bool: True se a mensagem deve ser ignorada, False caso contrário
    """
    ignore_keywords = ["recente", "marketplace"]
    
    # Converter para lowercase para comparação insensível a maiúsculas/minúsculas
    lower_text = text.lower()
    
    # Verificar se alguma palavra-chave está presente no texto
    for keyword in ignore_keywords:
        if keyword.lower() in lower_text:
            return True
            
    return False

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
    
    Procura por padrões como "R$ 99,99", "99.99", "2.672,10", "1.100", etc.
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
        
        # Números com ponto que podem ser separadores de milhar no formato brasileiro
        r'R\$\s*([\d\.]+)(?!\d)',  # R$ 1.100 (sem casas decimais)
        r'([\d\.]+)(?!\d)',  # 1.100 (sem R$ e sem casas decimais)
        
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
                logger.info(f"Preço normalizado (formato BR com vírgula): '{normalized_price}'")
                return normalized_price
            
            # Se tiver ponto, precisamos determinar se é separador de milhar ou decimal
            elif '.' in price_str:
                # Contar dígitos após o último ponto
                parts = price_str.split('.')
                last_part = parts[-1]
                
                # Se o último ponto tiver 0, 1 ou 2 dígitos após ele, provavelmente é um decimal
                if len(last_part) <= 2:
                    logger.info(f"Interpretando ponto como decimal: '{price_str}'")
                    return price_str
                # Se tiver 3 dígitos após o último ponto, é provavelmente um separador de milhar brasileiro
                else:
                    # Precisamos verificar se existe mais de um ponto
                    if len(parts) > 2:
                        # Múltiplos pontos, provavelmente são todos separadores de milhar
                        normalized_price = price_str.replace('.', '')
                        logger.info(f"Preço com múltiplos pontos, tratando como separador de milhar: '{normalized_price}.00'")
                        return normalized_price + ".00"
                    else:
                        # Verificar padrões específicos de valores comuns no Brasil
                        # Se o valor for como 1.100, 1.200, etc. (x.y00)
                        if len(price_str) >= 5 and re.match(r'\d+\.\d00$', price_str):
                            normalized_price = price_str.replace('.', '')
                            logger.info(f"Preço no formato brasileiro x.y00, tratando como separador de milhar: '{normalized_price}.00'")
                            return normalized_price + ".00"
                        # Assumindo que se houver mais de 2 dígitos após o ponto, é um separador de milhar
                        normalized_price = price_str.replace('.', '')
                        logger.info(f"Preço com 3+ dígitos após o ponto, tratando como separador de milhar: '{normalized_price}.00'")
                        return normalized_price + ".00"
            
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
            
            # Se tiver ponto, precisamos determinar se é separador de milhar ou decimal
            elif '.' in price_part:
                # Contar dígitos após o último ponto
                parts = price_part.split('.')
                last_part = parts[-1]
                
                # Se o último ponto tiver 0, 1 ou 2 dígitos após ele, provavelmente é um decimal
                if len(last_part) <= 2:
                    # Verificar se é um número válido
                    float(price_part)  # Isso vai lançar ValueError se não for válido
                    logger.info(f"Preço no formato com ponto como decimal: '{price_part}'")
                    return price_part
                # Se tiver 3 dígitos após o último ponto, é provavelmente um separador de milhar brasileiro
                else:
                    normalized_price = price_part.replace('.', '')
                    # Verificar se é um número válido
                    float(normalized_price)  # Isso vai lançar ValueError se não for válido
                    logger.info(f"Preço no formato brasileiro com ponto como separador de milhar: '{normalized_price}.00'")
                    return normalized_price + ".00"
            
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