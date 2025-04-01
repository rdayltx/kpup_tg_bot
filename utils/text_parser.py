import re
import logging

from utils.logger import get_logger

logger = get_logger(__name__)

def extract_asin_from_text(text):
    """
    Extract Amazon ASIN from text
    """
    if not text:
        return None
        
    # Regex pattern for Amazon URLs
    amazon_url_pattern = r'https?://(?:www\.)?amazon\.com\.br/(?:[^/]+/)?(?:dp|gp/product|gp/aw/d|exec/obidos/asin|o)/([A-Z0-9]{10})'
    
    amazon_match = re.search(amazon_url_pattern, text)
    if amazon_match:
        return amazon_match.group(1).upper()
    
    # Also look for raw ASINs in the text (just in case)
    asin_pattern = r'\b([A-Z0-9]{10})\b'
    asin_match = re.search(asin_pattern, text)
    if asin_match:
        return asin_match.group(1)
    
    return None

def extract_source_from_text(text):
    """
    Extract source information from text
    """
    if not text:
        return "Unknown"
        
    # Regex pattern for source
    source_pattern = r'Fonte:\s*(\w+)'
    
    source_match = re.search(source_pattern, text)
    if source_match:
        return source_match.group(1)
    
    return "Unknown"

def extract_price_from_comment(comment):
    """
    Extract price from comment text
    
    Looks for patterns like "R$ 99,99", "99.99", etc.
    Adds ".00" for integer numbers.
    """
    if not comment:
        return None
        
    # Common price patterns for decimal values
    decimal_patterns = [
        r'R\$\s*(\d+[,.]\d+)',  # R$ 99,99 or R$ 99.99
        r'(\d+[,.]\d+)\s*reais',  # 99,99 reais or 99.99 reais
        r'(\d+[,.]\d+)',  # 99,99 or 99.99 (generic)
    ]
    
    # Patterns for integer values
    integer_patterns = [
        r'R\$\s*(\d+)(?![,.]\d)',  # R$ 99 (no decimal)
        r'(\d+)\s*reais(?![,.]\d)',  # 99 reais (no decimal)
        r'(?<!\d[,.])(\d+)(?![,.]\d)',  # 99 (generic integer)
    ]
    
    # Check decimal patterns first
    for pattern in decimal_patterns:
        match = re.search(pattern, comment)
        if match:
            price = match.group(1).replace(',', '.')  # Normalize to dot format
            return price
    
    # Then check integer patterns
    for pattern in integer_patterns:
        match = re.search(pattern, comment)
        if match:
            return match.group(1) + ".00"  # Add ".00" for integer values
    
    # If no pattern matched
    return None

def extract_account_identifier(comment):
    """
    Extract account identifier from the comment
    
    Format: "ASIN, price, identifier"
    The identifier is the third part after the second comma
    """
    if not comment:
        return None
    
    logger.info(f"Extracting account identifier from: '{comment}'")
    
    # Split by comma and check if we have at least 3 parts
    parts = comment.strip().split(',')
    if len(parts) >= 3:
        # The identifier is the third part, trimmed of whitespace
        identifier = parts[2].strip()
        logger.info(f"Found account identifier: '{identifier}'")
        return identifier
    
    logger.info("No account identifier found in the comment")
    return None