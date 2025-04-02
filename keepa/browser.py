import os
import time
import random
import logging
import uuid
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from utils.logger import get_logger

logger = get_logger(__name__)

def find_chromedriver_manually():
    """
    Find the ChromeDriver executable path manually.
    """
    try:
        # Check environment variable first
        chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
        if chromedriver_path and os.path.exists(chromedriver_path) and os.access(chromedriver_path, os.X_OK):
            logger.info(f"Found chromedriver from environment variable at: {chromedriver_path}")
            return chromedriver_path
            
        # Try to find chromedriver in the system
        result = subprocess.run(['which', 'chromedriver'], capture_output=True, text=True)
        if result.returncode == 0:
            chromedriver_path = result.stdout.strip()
            logger.info(f"Found chromedriver at: {chromedriver_path}")
            return chromedriver_path
        
        # Look in common directories
        common_paths = [
            "/usr/local/bin/chromedriver",
            "/usr/bin/chromedriver",
            os.path.expanduser("~/.wdm/drivers/chromedriver")
        ]
        
        for path in common_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                logger.info(f"Found chromedriver at: {path}")
                return path
        
        # Search in the ~/.wdm directory recursively
        wdm_dir = os.path.expanduser("~/.wdm")
        if os.path.exists(wdm_dir):
            for root, _, files in os.walk(wdm_dir):
                for file in files:
                    if file == "chromedriver" or file == "chromedriver.exe":
                        file_path = os.path.join(root, file)
                        if os.access(file_path, os.X_OK):
                            logger.info(f"Found chromedriver at: {file_path}")
                            return file_path
        
        return None
    except Exception as e:
        logger.error(f"Error finding chromedriver: {str(e)}")
        return None

def initialize_driver(account_identifier=None):
    """
    Initialize Selenium WebDriver for Chrome
    
    Args:
        account_identifier: Optional identifier to create separate data directories for different accounts
    
    Returns:
        WebDriver: Configured Chrome WebDriver instance
    """
    # Generate a session identifier
    session_id = account_identifier or str(uuid.uuid4())[:8]
    
    # Configure Chrome options
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Configure Chrome data directory - use unique directory for each account
    chrome_data_dir = os.getenv("CHROME_USER_DATA_DIR", f"/tmp/chrome-data-{session_id}")
    chrome_options.add_argument(f"--user-data-dir={chrome_data_dir}")
    
    # Additional configurations to avoid detection
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    # Try to create and configure driver
    try:
        # First try direct path from environment variable
        chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
        if chromedriver_path and os.path.exists(chromedriver_path):
            logger.info(f"Using ChromeDriver from environment path: {chromedriver_path}")
            service = Service(executable_path=chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info(f"Successfully initialized Chrome using path from environment: {chromedriver_path}")
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info(f"Browser session initialized for account: {account_identifier}")
            return driver
    except Exception as e:
        logger.warning(f"Failed to initialize Chrome using environment path: {str(e)}")
    
    # Try finding chromedriver manually
    chromedriver_path = find_chromedriver_manually()
    
    if chromedriver_path:
        try:
            service = Service(executable_path=chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info(f"Successfully initialized Chrome using manual path: {chromedriver_path}")
            
            # Disable webdriver flag
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info(f"Browser session initialized for account: {account_identifier}")
            return driver
        except Exception as e:
            logger.error(f"Error using manual chromedriver path: {str(e)}")
            raise Exception(f"Failed to initialize Chrome. Error: {str(e)}")
    else:
        # Last resort: Try using built-in Chrome
        try:
            logger.info("Attempting to use webdriver_manager as last resort...")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info("Successfully initialized Chrome using ChromeDriverManager")
            
            # Disable webdriver flag
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info(f"Browser session initialized for account: {account_identifier}")
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize Chrome with all methods. Error: {str(e)}")
            raise Exception(f"Failed to initialize Chrome with all methods. Error: {str(e)}")