import threading
import time
import datetime
from flask import Flask, render_template, jsonify
from monitor_selenium import setup_driver, scroll_to_bottom, parse_page, URL

app = Flask(__name__)

# Global state
current_products = {}
alerts = []
monitored_products = [] # List of products to show in the monitor section
last_updated = "Never"
is_scraping = False

def scraper_loop():
    global current_products, alerts, monitored_products, last_updated, is_scraping
    
    print("Starting background scraper...")
    driver = setup_driver()
    seen_products = {}
    first_run = True
    
    try:
        while True:
            is_scraping = True
            start_time = time.time()
            print(f"Scraping... {datetime.datetime.now().strftime('%H:%M:%S')}")
            
            try:
                driver.get(URL)
                scroll_to_bottom(driver)
                html = driver.page_source
                fetched_products = parse_page(html)
                
                # Update global products
                current_products = fetched_products
                last_updated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Check for alerts
                for pid, data in fetched_products.items():
                    if pid not in seen_products:
                        # Only alert for NEW items if they are IN STOCK
                        if not first_run and data['in_stock']:
                            alert = {
                                'type': 'NEW',
                                'message': f"New Product: {data['name']}",
                                'link': data['link'],
                                'time': datetime.datetime.now().strftime("%H:%M:%S")
                            }
                            alerts.insert(0, alert)
                            if len(alerts) > 50:
                                alerts.pop()
                            
                            # Add to monitored products
                            # Check if already exists to avoid duplicates (though pid check handles most)
                            if not any(p['link'] == data['link'] for p in monitored_products):
                                data['alert_type'] = 'NEW'
                                data['alert_time'] = datetime.datetime.now().strftime("%H:%M:%S")
                                monitored_products.insert(0, data)
                                if len(monitored_products) > 20: # Keep last 20
                                    monitored_products.pop()

                        seen_products[pid] = data
                    else:
                        old_data = seen_products[pid]
                        # Alert if it WAS out of stock and IS NOW in stock
                        if not old_data['in_stock'] and data['in_stock']:
                            alert = {
                                'type': 'STOCK',
                                'message': f"Back in Stock: {data['name']}",
                                'link': data['link'],
                                'time': datetime.datetime.now().strftime("%H:%M:%S")
                            }
                            alerts.insert(0, alert)
                            if len(alerts) > 50:
                                alerts.pop()
                            
                            # Add to monitored products
                            if not any(p['link'] == data['link'] for p in monitored_products):
                                data['alert_type'] = 'STOCK'
                                data['alert_time'] = datetime.datetime.now().strftime("%H:%M:%S")
                                monitored_products.insert(0, data)
                                if len(monitored_products) > 20:
                                    monitored_products.pop()
                        
                        seen_products[pid] = data
                
                # Remove out-of-stock items from monitored_products
                monitored_products = [
                    p for p in monitored_products 
                    if p['link'] in current_products and current_products[p['link']]['in_stock']
                ]

                first_run = False
                
            except Exception as e:
                print(f"Error in scraper loop: {e}")
            
            is_scraping = False
            
            # Calculate time taken
            end_time = time.time()
            duration = end_time - start_time
            print(f"Scrape finished in {duration:.1f} seconds.")
            
            # Target interval: 10 seconds
            # Sleep = Target - Duration
            # But sleep at least 1 second to be safe
            sleep_time = max(1.0, 10.0 - duration)
            print(f"Sleeping for {sleep_time:.1f} seconds (Target interval: 10s)...")
            time.sleep(sleep_time)
            
    except Exception as e:
        print(f"Fatal scraper error: {e}")
    finally:
        driver.quit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    # Filter for only in-stock products
    in_stock_products = {pid: data for pid, data in current_products.items() if data['in_stock']}
    
    return jsonify({
        'products': in_stock_products,
        'monitored_products': monitored_products,
        'alerts': alerts,
        'last_updated': last_updated,
        'is_scraping': is_scraping,
        'total_count': len(in_stock_products)
    })

if __name__ == '__main__':
    # Start scraper thread
    thread = threading.Thread(target=scraper_loop, daemon=True)
    thread.start()
    
    # Run Flask app
    app.run(debug=True, use_reloader=False) # use_reloader=False to prevent double execution of thread
