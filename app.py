import datetime
import logging
import os
import threading
import time

from flask import Flask, jsonify, render_template

from monitor_api import (
    MISSING_CONFIRMATION_SNAPSHOTS,
    POLL_INTERVAL_SECONDS,
    fetch_api_products,
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
        snapshot = tracker.snapshot()
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
