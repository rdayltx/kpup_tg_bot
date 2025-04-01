import time
import random
import logging
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from config.settings import load_settings, KeepaAccount

from utils.logger import get_logger

logger = get_logger(__name__)
settings = load_settings()

# Dictionary to store browser sessions for different accounts
browser_sessions = {}

# Wait for element functions
def wait_for_element(driver, selector, by=By.CSS_SELECTOR, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )

def wait_for_visible_element(driver, selector, by=By.CSS_SELECTOR, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, selector))
    )

def click_element(driver, selector, by=By.CSS_SELECTOR):
    element = wait_for_element(driver, selector, by)
    driver.execute_script("arguments[0].click();", element)

def check_element_exists(driver, selector, by=By.CSS_SELECTOR, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        return True
    except TimeoutException:
        return False

def check_element_visible(driver, selector, by=By.CSS_SELECTOR, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((by, selector))
        )
        return True
    except TimeoutException:
        return False

def login_to_keepa(driver, account_identifier=None):
    """
    Login to Keepa website using the specified account identifier
    
    Args:
        driver: Selenium WebDriver instance
        account_identifier: String identifier for the account to use
    
    Returns:
        bool: True if login successful, False otherwise
    """
    # Get the appropriate account credentials
    if account_identifier and account_identifier in settings.KEEPA_ACCOUNTS:
        account = settings.KEEPA_ACCOUNTS[account_identifier]
    elif settings.DEFAULT_KEEPA_ACCOUNT in settings.KEEPA_ACCOUNTS:
        account = settings.KEEPA_ACCOUNTS[settings.DEFAULT_KEEPA_ACCOUNT]
        account_identifier = settings.DEFAULT_KEEPA_ACCOUNT
    else:
        logger.error(f"❌ No valid Keepa account found for identifier: {account_identifier}")
        return False
    
    logger.info(f"Starting Keepa login with account: {account_identifier}...")
    try:
        driver.get("https://keepa.com")
        time.sleep(random.uniform(1, 3))
        logger.info("Login page loaded.")

        # Make login overlay visible
        driver.execute_script('var overlay = document.querySelector("#loginOverlay"); if (overlay) overlay.style.display = "block";')
        logger.info("Login overlay made visible.")

        # Check for CAPTCHA
        if check_element_visible(driver, "iframe[title='reCAPTCHA']", timeout=3):
            logger.warning("⚠️ CAPTCHA detected. Automated mode cannot proceed.")
            driver.save_screenshot("captcha_detected.png")
            return False

        # Fill username
        username_field = wait_for_element(driver, "#username")
        username_field.clear()
        time.sleep(random.uniform(0.5, 1.5))
        username_field.send_keys(account.username)
        logger.info("Username filled.")

        # Fill password
        password_field = wait_for_element(driver, "#password")
        password_field.clear()
        time.sleep(random.uniform(0.5, 1.5))
        password_field.send_keys(account.password)
        logger.info("Password filled.")

        # Click login button
        time.sleep(random.uniform(1, 2))
        click_element(driver, "#submitLogin")
        logger.info("Login button clicked. Waiting for authentication...")
        
        # Wait for page to load or OTP to appear
        WebDriverWait(driver, 10).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )
        time.sleep(2)  # Additional buffer

        # Check for login errors
        if check_element_visible(driver, "#loginError") and driver.find_element(By.ID, "loginError").text:
            logger.error(f"❌ Login error: {driver.find_element(By.ID, 'loginError').text}")
            return False
        
        # Check if OTP is required
        if check_element_visible(driver, "#sectionLoginOtp"):
            logger.warning("⚠️ OTP authentication required!")
            logger.warning("Please check your email for the OTP sent by Keepa.")
            return False
        
        logger.info(f"✅ Login successful with account: {account_identifier}!")
        return True
    
    except Exception as e:
        logger.error(f"❌ Error during login: {str(e)}")
        driver.save_screenshot("login_error.png")
        return False

def update_keepa_product(driver, asin, price):
    """
    Update price target for a product in Keepa
    """
    logger.info(f"Updating product ASIN {asin} with price {price}")
    
    try:
        # Navigate to product page
        driver.get(f"https://keepa.com/#!product/12-{asin}")
        
        # Check if page loaded correctly
        try:
            wait_for_element(driver, "#productInfoBox", timeout=10)
        except TimeoutException:
            logger.warning(f"⚠️ Product page for {asin} did not load correctly")
            return False

        # Click on tracking tab
        try:
            click_element(driver, "#tabTrack")
            time.sleep(3)  # Wait for animations
        except Exception as e:
            logger.error(f"❌ Failed to access tracking tab: {str(e)}")
            return False

        # Check if tracking already exists
        if settings.UPDATE_EXISTING_TRACKING and check_element_exists(driver, "#updateTracking"):
            logger.info("🔄 Existing alert found, updating...")
            try:
                click_element(driver, "#updateTracking")
                time.sleep(2)  # Wait for loading
                
                # Find and fill price field
                price_container = wait_for_element(
                    driver,
                    "//label[contains(.,'Amazon')]/ancestor::div[contains(@class,'mdc-text-field')]//input",
                    By.XPATH
                )
                driver.execute_script(f"""
                    var input = arguments[0];
                    input.value = '';
                    input.value = '{price}';
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change'));
                """, price_container)
                
                # Submit update
                btn_submit = wait_for_element(driver, "#submitTracking", timeout=8)
                driver.execute_script("arguments[0].click();", btn_submit)
                logger.info(f"✅ Alert successfully updated for {asin}")
                time.sleep(4)
                return True
            except Exception as e:
                logger.error(f"❌ Error updating alert: {str(e)}")
                return False
        elif check_element_exists(driver, "#updateTracking"):
            logger.info(f"✅ Alert already exists for {asin}, but was not updated")
            return True

        # Create new alert
        try:
            # Find price field using label
            price_container = wait_for_element(
                driver,
                "//label[contains(.,'Amazon')]/ancestor::div[contains(@class,'mdc-text-field')]//input",
                By.XPATH
            )
            
            # Fill value
            driver.execute_script(f"""
                var input = arguments[0];
                input.value = '';
                input.value = '{price}';
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change'));
            """, price_container)
            
            # Try to create new alert
            btn_submit = wait_for_element(driver, "#submitTracking", timeout=8)
            driver.execute_script("arguments[0].click();", btn_submit)
            logger.info(f"✅ New alert created for {asin}")
            time.sleep(4)  # Wait for confirmation
            return True
        except Exception as e:
            logger.error(f"❌ Error creating alert: {str(e)}")
            return False

    except Exception as e:
        logger.error(f"❌ Critical error: {str(e)}")
        screenshot_path = os.path.join(os.getcwd(), f"error_{asin}.png")
        driver.save_screenshot(screenshot_path)
        return False