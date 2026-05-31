import logging
import os
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from colorama import Fore, Style, init
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

init()

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.firstcry.com"
URL = (
    "https://www.firstcry.com/hotwheels/5/0/113"
    "?sort=popularity&q=ard-hotwheels&ref2=q_ard_hotwheels&asid=53241"
)

PRODUCT_CARD_SELECTOR = "div.list_block"
PRODUCT_LINK_SELECTOR = 'a[href*="/product-detail"]'
PRODUCT_ID_PATTERN = re.compile(r"/(\d+)/product-detail(?:/|$)", re.IGNORECASE)
CATALOG_COUNT_PATTERN = re.compile(r"\(([\d,]+)\s+Items?\)", re.IGNORECASE)
OUT_OF_STOCK_TERMS = ("out of stock", "sold out", "notify me")
DISABLED_MARKERS = ("disabled", "disable", "outofstock", "out-of-stock")


class ScrapeError(RuntimeError):
    """Raised when a listing scrape cannot safely replace the last snapshot."""


@dataclass(frozen=True)
class ScrollResult:
    observed_cards: int
    expected_cards: int | None
    elapsed_seconds: float
    reached_expected_count: bool


def _env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        LOGGER.warning("Ignoring invalid %s value; using %s", name, default)
        return float(default)


PAGE_LOAD_TIMEOUT_SECONDS = _env_float("FIRSTCRY_PAGE_LOAD_TIMEOUT", 30)
CARD_WAIT_TIMEOUT_SECONDS = _env_float("FIRSTCRY_CARD_WAIT_TIMEOUT", 10)
MAX_SCROLL_SECONDS = _env_float("FIRSTCRY_MAX_SCROLL_SECONDS", 60)
SCROLL_SETTLE_SECONDS = _env_float("FIRSTCRY_SCROLL_SETTLE_SECONDS", 6)
SCROLL_POLL_SECONDS = _env_float("FIRSTCRY_SCROLL_POLL_SECONDS", 1)
MIN_PARSE_RATIO = _env_float("FIRSTCRY_MIN_PARSE_RATIO", 0.9)
POLL_INTERVAL_SECONDS = _env_float("FIRSTCRY_POLL_INTERVAL", 15)


def setup_driver():
    chrome_options = Options()

    user_agent = os.getenv("FIRSTCRY_USER_AGENT")
    if user_agent:
        chrome_options.add_argument(f"--user-agent={user_agent}")
        LOGGER.info("Using configured browser user-agent")

    proxy = os.getenv("FIRSTCRY_PROXY")
    if proxy:
        chrome_options.add_argument(f"--proxy-server={proxy}")
        LOGGER.info("Using configured proxy")

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
    return driver


def close_driver(driver):
    if driver is None:
        return

    try:
        driver.quit()
    except WebDriverException:
        LOGGER.debug("WebDriver was already unavailable while closing", exc_info=True)


def parse_catalog_count(text):
    match = CATALOG_COUNT_PATTERN.search(text or "")
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _get_expected_product_count(driver):
    try:
        text = driver.find_element(By.CSS_SELECTOR, ".list_rightp").text
    except WebDriverException:
        text = driver.page_source
    return parse_catalog_count(text)


def _get_product_card_count(driver):
    return len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR))


def _click_show_more_if_visible(driver):
    return driver.execute_script(
        """
        const container = document.querySelector('.showmoredivs');
        if (!container || getComputedStyle(container).display === 'none') {
            return false;
        }
        const link = container.querySelector('a');
        if (!link) {
            return false;
        }
        link.click();
        return true;
        """
    )


def scroll_to_bottom(
    driver,
    max_seconds=MAX_SCROLL_SECONDS,
    settle_seconds=SCROLL_SETTLE_SECONDS,
    poll_seconds=SCROLL_POLL_SECONDS,
):
    try:
        WebDriverWait(driver, CARD_WAIT_TIMEOUT_SECONDS).until(
            lambda current_driver: _get_product_card_count(current_driver) > 0
        )
    except TimeoutException as exc:
        raise ScrapeError("Timed out waiting for FirstCry product cards") from exc

    started_at = time.monotonic()
    last_change_at = started_at
    expected_cards = _get_expected_product_count(driver)
    observed_cards = _get_product_card_count(driver)
    last_height = driver.execute_script("return document.body.scrollHeight")

    while time.monotonic() - started_at < max_seconds:
        if expected_cards and observed_cards >= expected_cards:
            break

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(poll_seconds)

        current_height = driver.execute_script("return document.body.scrollHeight")
        current_cards = _get_product_card_count(driver)
        if current_height != last_height or current_cards != observed_cards:
            last_change_at = time.monotonic()
            last_height = current_height
            observed_cards = current_cards
            continue

        if time.monotonic() - last_change_at < settle_seconds:
            continue

        if expected_cards:
            _click_show_more_if_visible(driver)
        else:
            break

    elapsed_seconds = time.monotonic() - started_at
    return ScrollResult(
        observed_cards=observed_cards,
        expected_cards=expected_cards,
        elapsed_seconds=elapsed_seconds,
        reached_expected_count=bool(expected_cards and observed_cards >= expected_cards),
    )


def _normalize_url(value):
    return urljoin(BASE_URL, (value or "").strip())


def _extract_product_id(link):
    match = PRODUCT_ID_PATTERN.search(urlparse(link).path)
    return match.group(1) if match else link


def _get_product_name(block, link_tag):
    titled_link = block.select_one(f"{PRODUCT_LINK_SELECTOR}[title]")
    if titled_link and titled_link.get("title", "").strip():
        return titled_link["title"].strip()

    image = block.find("img", alt=True)
    if image and image.get("alt", "").strip():
        return image["alt"].strip()

    return link_tag.get_text(" ", strip=True)


def _is_disabled(tag):
    if tag.has_attr("disabled") or tag.get("aria-disabled", "").lower() == "true":
        return True

    classes = " ".join(tag.get("class", [])).lower()
    style = tag.get("style", "").replace(" ", "").lower()
    return any(marker in classes for marker in DISABLED_MARKERS) or "display:none" in style


def _is_in_stock(block):
    text = block.get_text(" ", strip=True).lower()
    if any(term in text for term in OUT_OF_STOCK_TERMS):
        return False
    return any(not _is_disabled(tag) for tag in block.select(".ga_bn_btn_addcart"))


def _get_image_url(block):
    image = block.find("img")
    if not image:
        return ""

    for attribute in ("src", "data-src", "data-original"):
        value = image.get(attribute)
        if value:
            return _normalize_url(value)
    return ""


def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    products = {}

    for index, block in enumerate(soup.select(PRODUCT_CARD_SELECTOR)):
        try:
            link_tag = block.select_one(PRODUCT_LINK_SELECTOR)
            if not link_tag:
                continue

            link = _normalize_url(link_tag.get("href"))
            name = _get_product_name(block, link_tag)
            if not link or not name:
                raise ValueError("product card is missing its link or name")

            product_id = _extract_product_id(link)
            products[product_id] = {
                "id": product_id,
                "name": name,
                "in_stock": _is_in_stock(block),
                "link": link,
                "image": _get_image_url(block),
            }
        except (AttributeError, TypeError, ValueError) as exc:
            LOGGER.warning("Skipping malformed FirstCry product card %s: %s", index, exc)

    return products


def scrape_products(driver, url=URL):
    driver.get(url)
    scroll_result = scroll_to_bottom(driver)
    products = parse_page(driver.page_source)

    if not products:
        raise ScrapeError("FirstCry returned no parseable product cards")

    if (
        scroll_result.expected_cards
        and scroll_result.observed_cards < scroll_result.expected_cards
    ):
        raise ScrapeError(
            "FirstCry lazy loading stopped early: "
            f"found {scroll_result.observed_cards} of "
            f"{scroll_result.expected_cards} product cards"
        )

    if (
        scroll_result.expected_cards
        and len(products) / scroll_result.expected_cards < MIN_PARSE_RATIO
    ):
        raise ScrapeError(
            "Too many FirstCry product cards could not be parsed: "
            f"parsed {len(products)} of about {scroll_result.expected_cards}"
        )

    LOGGER.info(
        "Scraped %s products from %s rendered cards in %.1fs",
        len(products),
        scroll_result.observed_cards,
        scroll_result.elapsed_seconds,
    )
    return products, scroll_result


def monitor():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    LOGGER.info("Starting Selenium monitor for %s", URL)

    driver = None
    seen_products = {}
    first_run = True

    try:
        while True:
            started_at = time.monotonic()
            try:
                if driver is None:
                    LOGGER.info("Initializing WebDriver")
                    driver = setup_driver()

                current_products, _ = scrape_products(driver)

                missing_ids = seen_products.keys() - current_products.keys()
                for product_id in missing_ids:
                    seen_products[product_id]["in_stock"] = False

                count_new = 0
                count_back_in_stock = 0
                for product_id, data in current_products.items():
                    old_data = seen_products.get(product_id)
                    if old_data is None:
                        if not first_run and data["in_stock"]:
                            print(
                                f"{Fore.GREEN}[NEW PRODUCT] {data['name']} - "
                                f"{data['link']}{Style.RESET_ALL}"
                            )
                            count_new += 1
                    elif not old_data["in_stock"] and data["in_stock"]:
                        print(
                            f"{Fore.GREEN}[BACK IN STOCK] {data['name']} - "
                            f"{data['link']}{Style.RESET_ALL}"
                        )
                        count_back_in_stock += 1

                    seen_products[product_id] = data

                if first_run:
                    print(
                        f"{Fore.BLUE}Initial check complete. Tracking "
                        f"{len(seen_products)} products.{Style.RESET_ALL}"
                    )
                    first_run = False
                elif count_new == 0 and count_back_in_stock == 0:
                    print(
                        f"{Fore.WHITE}No changes. Tracking "
                        f"{len(seen_products)} products.{Style.RESET_ALL}"
                    )
            except (ScrapeError, WebDriverException) as exc:
                LOGGER.error("Scrape failed: %s", exc)
                close_driver(driver)
                driver = None

            duration = time.monotonic() - started_at
            time.sleep(max(1.0, POLL_INTERVAL_SECONDS - duration))
    except KeyboardInterrupt:
        print(f"\n{Fore.CYAN}Stopping monitor.{Style.RESET_ALL}")
    finally:
        close_driver(driver)


if __name__ == "__main__":
    monitor()
