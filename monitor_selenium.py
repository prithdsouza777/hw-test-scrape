import time
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from colorama import init, Fore, Style
from fake_useragent import UserAgent
import random

init()

URL = "https://www.firstcry.com/hotwheels/5/0/113?sort=popularity&q=ard-hotwheels&ref2=q_ard_hotwheels&asid=53241"

# Add your proxies here in the format "ip:port" or "user:pass@ip:port"
# Example: "142.93.12.3:8080"
PROXIES = [] 

seen_products = {}

def setup_driver():
    chrome_options = Options()
    
    # 1. User-Agent Rotation
    try:
        ua = UserAgent()
        user_agent = ua.random
        chrome_options.add_argument(f'user-agent={user_agent}')
        print(f"{Fore.MAGENTA}Using User-Agent: {user_agent[:50]}...{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}Could not set fake UA: {e}. Using default.{Style.RESET_ALL}")

    # 2. Proxy Rotation
    if PROXIES:
        proxy = random.choice(PROXIES)
        chrome_options.add_argument(f'--proxy-server={proxy}')
        print(f"{Fore.MAGENTA}Using Proxy: {proxy}{Style.RESET_ALL}")

    chrome_options.add_argument("--headless") # Run in headless mode
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--log-level=3") # Suppress logs
    
    # Suppress "DevTools listening on..."
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def scroll_to_bottom(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    while True:
        # Scroll down to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

        # Wait to load page
        time.sleep(1)

        # Calculate new scroll height and compare with last scroll height
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            # Try one more small scroll or wait a bit longer to be sure
            time.sleep(1.5)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
        last_height = new_height

def parse_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    products = {}
    
    # FirstCry list block structure
    # <div class="list_block ...">
    #   <div class="image_block"> ... <a href="..."> ... </a> ... </div>
    #   <div class="info_block"> ... </div>
    # </div>
    
    blocks = soup.find_all('div', class_='list_block')
    
    for block in blocks:
        try:
            # Find link
            link_tag = block.find('a', href=True)
            if not link_tag:
                continue
                
            href = link_tag['href']
            
            # Extract ID
            # href example: https://www.firstcry.com/hot-wheels/.../product-detail...
            # We can use the href as a unique key if ID extraction is flaky
            
            # Name
            title_tag = block.find('a', title=True)
            name = title_tag['title'] if title_tag else link_tag.text.strip()
            
            # If name is still empty, try image alt
            if not name:
                img = block.find('img', alt=True)
                if img:
                    name = img['alt']
            
            # Stock Status Logic
            # Check for "Add to Cart" button class
            # Based on debug: 'ga_bn_btn_addcart' indicates in stock
            add_to_cart_btn = block.find('div', class_='ga_bn_btn_addcart')
            
            # Also check for explicit out of stock text just in case
            block_text = block.text.lower()
            text_indicates_oos = "out of stock" in block_text or "sold out" in block_text or "notify me" in block_text
            
            # Final decision: In stock if Add to Cart is present AND no explicit OOS text
            # (Sometimes Add to Cart might be present but disabled/hidden, but usually it's removed)
            is_in_stock = bool(add_to_cart_btn) and not text_indicates_oos
            
            # Use href as ID for simplicity and uniqueness
            pid = href
            
            # Image URL
            img_tag = block.find('img', src=True)
            image_url = img_tag['src'] if img_tag else ''

            products[pid] = {
                'name': name,
                'in_stock': is_in_stock,
                'link': href,
                'image': image_url
            }
            
        except Exception as e:
            continue
            
    return products

def monitor():
    print(f"{Fore.CYAN}Starting Selenium monitor for: {URL}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Initializing WebDriver...{Style.RESET_ALL}")
    
    driver = setup_driver()
    
    print(f"{Fore.CYAN}Driver ready. Press Ctrl+C to stop.{Style.RESET_ALL}")
    
    first_run = True
    
    try:
        while True:
            print(f"{Fore.YELLOW}Checking... {time.strftime('%H:%M:%S')}{Style.RESET_ALL}")
            
            driver.get(URL)
            scroll_to_bottom(driver)
            
            html = driver.page_source
            current_products = parse_page(html)
            
            if not current_products:
                print(f"{Fore.RED}No products found. Check selectors.{Style.RESET_ALL}")
            
            count_new = 0
            count_back_in_stock = 0
            
            for pid, data in current_products.items():
                if pid not in seen_products:
                    if not first_run:
                        print(f"{Fore.GREEN}[NEW PRODUCT] {data['name']} - {data['link']}{Style.RESET_ALL}")
                        count_new += 1
                    seen_products[pid] = data
                else:
                    old_data = seen_products[pid]
                    if not old_data['in_stock'] and data['in_stock']:
                        print(f"{Fore.GREEN}[BACK IN STOCK] {data['name']} - {data['link']}{Style.RESET_ALL}")
                        count_back_in_stock += 1
                    
                    seen_products[pid] = data
            
            if first_run:
                print(f"{Fore.BLUE}Initial check complete. Tracking {len(seen_products)} products.{Style.RESET_ALL}")
                first_run = False
            else:
                if count_new == 0 and count_back_in_stock == 0:
                    print(f"{Fore.WHITE}No changes. Tracking {len(seen_products)} products.{Style.RESET_ALL}")
            
            time.sleep(10)
            
    except KeyboardInterrupt:
        print(f"\n{Fore.CYAN}Stopping monitor.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Unexpected error: {e}{Style.RESET_ALL}")
    finally:
        driver.quit()

if __name__ == "__main__":
    monitor()
