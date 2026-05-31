import datetime
import logging
import os
from pathlib import Path
import threading
import time

from flask import Flask, jsonify, render_template

from monitor_api import (
    FIRSTCRY_CART_COOKIE_NAME,
    FIRSTCRY_CART_URL,
    MISSING_CONFIRMATION_SNAPSHOTS,
    POLL_INTERVAL_SECONDS,
    add_cart_action_metadata,
    fetch_api_products,
    merge_cart_cookie_value,
)
from product_tracker import ProductTracker

LOGGER = logging.getLogger(__name__)

app = Flask(__name__)

tracker = ProductTracker(
    missing_confirmation_snapshots=MISSING_CONFIRMATION_SNAPSHOTS
)
state_lock = threading.Lock()
last_updated = "Never"
last_error = None
last_ttl_seconds = None
catalog_count = 0
is_scraping = False
cart_driver = None
cart_driver_lock = threading.Lock()

CART_BROWSER_PROFILE_PATH = Path(
    os.getenv(
        "FIRSTCRY_CART_BROWSER_PROFILE",
        Path(__file__).with_name("selenium_profile"),
    )
).resolve()


def _decorate_snapshot_products(snapshot):
    snapshot = dict(snapshot)
    snapshot["products"] = {
        product_id: add_cart_action_metadata(product)
        for product_id, product in snapshot.get("products", {}).items()
    }
    snapshot["pending_products"] = {
        product_id: add_cart_action_metadata(product)
        for product_id, product in snapshot.get("pending_products", {}).items()
    }
    snapshot["monitored_products"] = [
        add_cart_action_metadata(product)
        for product in snapshot.get("monitored_products", [])
    ]
    return snapshot


def _create_cart_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument(f"--user-data-dir={CART_BROWSER_PROFILE_PATH}")
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    return webdriver.Chrome(options=options)


def _get_cart_driver():
    global cart_driver

    with cart_driver_lock:
        if cart_driver is not None:
            try:
                cart_driver.current_url
                return cart_driver
            except Exception:
                cart_driver = None

        cart_driver = _create_cart_driver()
        return cart_driver


def add_product_to_firstcry_cart(product):
    product_id = str(product["id"])
    driver = _get_cart_driver()

    driver.get("https://www.firstcry.com/")
    existing_cookie = driver.get_cookie(FIRSTCRY_CART_COOKIE_NAME)
    existing_value = existing_cookie["value"] if existing_cookie else ""
    cart_cookie = merge_cart_cookie_value(existing_value, product_id)

    try:
        driver.delete_cookie(FIRSTCRY_CART_COOKIE_NAME)
    except Exception:
        pass
    driver.add_cookie(
        {
            "name": FIRSTCRY_CART_COOKIE_NAME,
            "value": cart_cookie,
            "domain": ".firstcry.com",
            "path": "/",
            "expiry": int(time.time() + 7 * 24 * 60 * 60),
        }
    )
    driver.execute_script(
        """
        try {
            localStorage.removeItem("CartCookieData");
            localStorage.removeItem("CartCookie");
        } catch (error) {}
        """
    )
    driver.get(FIRSTCRY_CART_URL)
    return cart_cookie


def scraper_loop():
    global catalog_count, is_scraping, last_error, last_ttl_seconds, last_updated

    LOGGER.info("Starting FirstCry listing API dashboard")

    while True:
        started_at = time.monotonic()
        with state_lock:
            is_scraping = True

        try:
            products, result = fetch_api_products()
            now = datetime.datetime.now()
            with state_lock:
                events = tracker.update(products, now=now)
                catalog_count = result.expected_products
                last_updated = now.strftime("%Y-%m-%d %H:%M:%S")
                last_ttl_seconds = result.ttl_seconds
                last_error = None

            for event in events:
                product = event["product"]
                LOGGER.warning(
                    "%s: %s (stock: %s) - %s",
                    event["type"],
                    product["name"],
                    product["stock_count"],
                    product["link"],
                )
        except Exception as exc:
            LOGGER.exception("API scrape failed; retaining the previous snapshot")
            with state_lock:
                last_error = str(exc)
        finally:
            with state_lock:
                is_scraping = False

        duration = time.monotonic() - started_at
        sleep_seconds = max(1.0, POLL_INTERVAL_SECONDS - duration)
        LOGGER.info(
            "API scrape cycle finished in %.1fs; sleeping %.1fs",
            duration,
            sleep_seconds,
        )
        time.sleep(sleep_seconds)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def get_data():
    with state_lock:
        snapshot = _decorate_snapshot_products(tracker.snapshot())
        snapshot.update(
            {
                "source": "firstcry_listing_api",
                "catalog_count": catalog_count,
                "listing_ttl_seconds": last_ttl_seconds,
                "last_updated": last_updated,
                "last_error": last_error,
                "is_scraping": is_scraping,
            }
        )
    return jsonify(snapshot)


@app.route("/api/add-to-cart/<product_id>", methods=["POST"])
def add_to_cart(product_id):
    with state_lock:
        product = tracker.snapshot()["products"].get(str(product_id))

    if product is None:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": (
                        "Product is not currently cart-accepted by the monitor."
                    ),
                }
            ),
            409,
        )

    try:
        cart_cookie = add_product_to_firstcry_cart(add_cart_action_metadata(product))
    except Exception as exc:
        LOGGER.exception("Could not add %s to FirstCry cart", product_id)
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify(
        {
            "ok": True,
            "product_id": str(product_id),
            "cart_cookie": cart_cookie,
            "cart_url": FIRSTCRY_CART_URL,
        }
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    thread = threading.Thread(target=scraper_loop, daemon=True)
    thread.start()

    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(debug=debug, port=port, use_reloader=False)
