import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

# Define color codes for different log levels
LOG_COLORS = {
    'DEBUG': Fore.CYAN,
    'INFO': Fore.GREEN,
    'WARNING': Fore.YELLOW,
    'ERROR': Fore.RED,
    'CRITICAL': Fore.MAGENTA + Style.BRIGHT
}

# Define symbols for different log levels
LOG_SYMBOLS = {
    'DEBUG': '🔍',
    'INFO': 'ℹ️',
    'WARNING': '⚠️',
    'ERROR': '❌',
    'CRITICAL': '🔥'
}

# Define custom log format
LOG_FORMAT = '%(asctime)s - %(symbol)s %(colored_levelname)s - %(name)s - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Define log file location
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'keepa_bot.log')

class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors and symbols to log messages"""
    
    def format(self, record):
        # Save the original format
        levelname = record.levelname
        
        # Add the colored levelname and symbol to the record
        record.colored_levelname = LOG_COLORS.get(levelname, '') + levelname + Style.RESET_ALL
        record.symbol = LOG_SYMBOLS.get(levelname, '')
        
        # Call the original formatter's format method
        return super().format(record)

def setup_logging(log_level=logging.INFO, console_output=True, file_output=True, max_file_size=10*1024*1024, backup_count=5):
    """
    Setup logging configuration
    
    Args:
        log_level (int): The logging level (e.g., logging.INFO)
        console_output (bool): Whether to output logs to console
        file_output (bool): Whether to output logs to file
        max_file_size (int): Maximum size of each log file in bytes
        backup_count (int): Number of backup log files to keep
    """
    # Create logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatters
    colored_formatter = ColoredFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s', datefmt=DATE_FORMAT)
    
    # Add console handler if requested
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(colored_formatter)
        root_logger.addHandler(console_handler)
    
    # Add file handler if requested
    if file_output:
        # Create logs directory if it doesn't exist
        os.makedirs(LOG_DIR, exist_ok=True)
        
        # Create rotating file handler
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=max_file_size,
            backupCount=backup_count
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    return root_logger

def get_logger(name):
    """
    Get a logger with the specified name
    
    Args:
        name (str): The name of the logger
        
    Returns:
        logging.Logger: The logger
    """
    return logging.getLogger(name)