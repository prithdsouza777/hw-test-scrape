import json
import logging
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from inspect import Parameter, signature
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from colorama import Fore, Style, init

from product_tracker import ProductTracker

init()

LOGGER = logging.getLogger(__name__)

LISTING_URL = (
    "https://www.firstcry.com/hotwheels/5/0/113"
    "?sort=popularity&q=ard-hotwheels&ref2=q_ard_hotwheels&asid=53241"
)
API_URL = (
    "https://www.firstcry.com/svcs/SearchResult.svc/"
    "GetSearchResultProductsPaging"
)
PRODUCT_DETAIL_API_URL = (
    "https://www.firstcry.com/svcs/CommonService.svc/getProduct/pid={product_id}/uid=0"
)
CART_PRODUCT_COUNT_URL = (
    "https://csc.fcappservices.in/ShoppingCart/ShoppingCart.svc/json/"
    "GetCartProductCount"
)
IMAGE_BASE_URL = "https://cdn.fcglcdn.com/brainbees/images/products/219x265/"
PAGE_SIZE = 20
CURRENT_PRODUCT_DETAIL_JSON_PATTERN = re.compile(
    r"(?:^|[;,]|\bvar\s+)\s*CurrentProductDetailJSON\s*="
)
PRODUCT_ID_PATTERN = re.compile(r"(?:/|^)(\d{5,})(?:/product-detail\b|$)")
STANDALONE_PRODUCT_ID_PATTERN = re.compile(r"\b\d{5,}\b")


class ApiScrapeError(RuntimeError):
    """Raised when the listing API cannot safely replace the last snapshot."""


@dataclass(frozen=True)
class ApiFetchResult:
    expected_products: int
    raw_products: int
    unique_products: int
    pages_fetched: int
    ttl_seconds: int | None
    elapsed_seconds: float
    sort_expressions: tuple[str, ...] = ()


def _env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        LOGGER.warning("Ignoring invalid %s value; using %s", name, default)
        return float(default)


def _env_int(name, default):
    try:
        return max(1, int(os.getenv(name, default)))
    except ValueError:
        LOGGER.warning("Ignoring invalid %s value; using %s", name, default)
        return int(default)


def _env_list(name, default):
    raw_value = os.getenv(name, default)
    values = tuple(
        value.strip() for value in raw_value.split(",") if value.strip()
    )
    if values:
        return values
    LOGGER.warning("Ignoring empty %s value; using %s", name, default)
    return tuple(value.strip() for value in default.split(",") if value.strip())


REQUEST_TIMEOUT_SECONDS = _env_float("FIRSTCRY_API_TIMEOUT", 20)
DETAIL_TIMEOUT_SECONDS = _env_float("FIRSTCRY_API_DETAIL_TIMEOUT", 10)
CART_TIMEOUT_SECONDS = _env_float("FIRSTCRY_API_CART_TIMEOUT", 10)
POLL_INTERVAL_SECONDS = _env_float("FIRSTCRY_API_POLL_INTERVAL", 60)
MAX_PAGES = _env_int("FIRSTCRY_API_MAX_PAGES", 30)
DETAIL_WORKERS = _env_int("FIRSTCRY_API_DETAIL_WORKERS", 8)
MIN_API_PARSE_RATIO = _env_float("FIRSTCRY_API_MIN_PARSE_RATIO", 0.95)
MISSING_CONFIRMATION_SNAPSHOTS = _env_int("FIRSTCRY_API_MISSING_CONFIRMATIONS", 2)
LISTING_SORT_EXPRESSIONS = _env_list(
    "FIRSTCRY_API_SORT_EXPRESSIONS",
    "popularity,NewArrivals,HighestDiscount,Rating",
)
VERIFY_GAP_PRODUCTS = os.getenv("FIRSTCRY_API_DISCOVER_GAP_PRODUCTS", "1").lower() not in {
    "0",
    "false",
    "no",
}
GAP_PRODUCT_MAX_GAP = _env_int("FIRSTCRY_API_GAP_PRODUCT_MAX_GAP", 20)
GAP_PRODUCT_MAX_CANDIDATES = _env_int("FIRSTCRY_API_GAP_PRODUCT_MAX_CANDIDATES", 300)
GAP_PRODUCT_WORKERS = _env_int("FIRSTCRY_API_GAP_PRODUCT_WORKERS", 12)
VERIFY_KNOWN_PRODUCTS = os.getenv("FIRSTCRY_API_PROBE_KNOWN_PRODUCTS", "1").lower() not in {
    "0",
    "false",
    "no",
}
KNOWN_PRODUCT_WORKERS = _env_int("FIRSTCRY_API_KNOWN_PRODUCT_WORKERS", 12)
KNOWN_PRODUCT_MAX_IDS = _env_int("FIRSTCRY_API_KNOWN_PRODUCT_MAX_IDS", 1000)
KNOWN_PRODUCTS_PATH = Path(
    os.getenv(
        "FIRSTCRY_API_KNOWN_PRODUCTS_FILE",
        Path(__file__).with_name("known_products.json"),
    )
)
WATCHLIST_PATH = Path(
    os.getenv(
        "FIRSTCRY_API_WATCHLIST_FILE",
        Path(__file__).with_name("watchlist.txt"),
    )
)
VERIFY_DETAIL_STOCK = os.getenv("FIRSTCRY_API_VERIFY_DETAIL_STOCK", "1").lower() not in {
    "0",
    "false",
    "no",
}
VERIFY_CART_STOCK = os.getenv("FIRSTCRY_API_VERIFY_CART_STOCK", "1").lower() not in {
    "0",
    "false",
    "no",
}
USER_AGENT = os.getenv(
    "FIRSTCRY_API_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FirstCryStockMonitor/1.0",
)

API_PARAMS = {
    "PageSize": PAGE_SIZE,
    "SortExpression": "popularity",
    "OnSale": "5",
    "SearchString": "brand",
    "SubCatId": "",
    "BrandId": "",
    "Price": "",
    "Age": "",
    "Color": "",
    "OptionalFilter": "",
    "OutOfStock": "",
    "Type1": "",
    "Type2": "",
    "Type3": "",
    "Type4": "",
    "Type5": "",
    "Type6": "",
    "Type7": "",
    "Type8": "",
    "Type9": "",
    "Type10": "",
    "Type11": "",
    "Type12": "",
    "Type13": "",
    "Type14": "",
    "Type15": "",
    "combo": "",
    "discount": "",
    "searchwithincat": "",
    "ProductidQstr": "",
    "searchrank": "",
    "pmonths": "",
    "cgen": "",
    "PriceQstr": "",
    "DiscountQstr": "",
    "sorting": "",
    "MasterBrand": "113",
    "Rating": "",
    "Offer": "",
    "skills": "",
    "material": "",
    "curatedcollections": "",
    "measurement": "",
    "gender": "",
    "exclude": "",
    "premium": "",
    "pcode": "0",
    "isclub": "0",
    "deliverytype": "",
    "author": "",
    "booktype": "",
    "character": "",
    "collection": "",
    "format": "",
    "genre": "",
    "booklanguage": "",
    "publication": "",
    "skill": "",
}


def _parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_expected_count(value):
    if isinstance(value, list):
        value = value[0] if value else None
    count = _parse_int(value, default=-1)
    return count if count >= 0 else None


def _slugify(value):
    slug = (value or "").lower().replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-") or "product"


def _build_product_link(product_id, name):
    return (
        f"https://www.firstcry.com/hot-wheels/{_slugify(name)}/"
        f"{product_id}/product-detail"
    )


def _build_image_url(images):
    first_image = (images or "").split(";", 1)[0].strip()
    if not first_image:
        return ""
    image_name = re.sub(r"\.[^.]+$", ".webp", first_image)
    return IMAGE_BASE_URL + image_name


def _extract_product_ids(value):
    text = str(value or "")
    product_ids = set(PRODUCT_ID_PATTERN.findall(text))
    product_ids.update(STANDALONE_PRODUCT_ID_PATTERN.findall(text))
    return {product_id for product_id in product_ids if product_id.isdigit()}


def _product_id_sort_key(product_id):
    return int(product_id) if str(product_id).isdigit() else str(product_id)


def _normalise_known_product(product):
    if not isinstance(product, dict):
        return None

    product_id = str(product.get("id") or product.get("pid") or "").strip()
    if not product_id.isdigit():
        return None

    name = str(product.get("name") or product.get("pnm") or "").strip()
    link = str(product.get("link") or "").strip()
    image = str(product.get("image") or "").strip()
    return {
        "id": product_id,
        "name": name or f"Hot Wheels Product {product_id}",
        "in_stock": bool(product.get("in_stock", False)),
        "stock_count": max(0, _parse_int(product.get("stock_count"))),
        "link": link or _build_product_link(product_id, name),
        "image": image,
        "stock_signal": product.get("stock_signal", "known_product_store"),
    }


def _supports_sort_expression(page_fetcher):
    try:
        parameters = signature(page_fetcher).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind == Parameter.VAR_KEYWORD
        or parameter.name == "sort_expression"
        for parameter in parameters
    )


def _merge_product_signal(products, product):
    existing = products.get(product["id"])
    if existing is None or product["stock_count"] > existing["stock_count"]:
        products[product["id"]] = product


def _build_gap_product_candidates(products):
    product_ids = sorted(
        int(product_id)
        for product_id in products
        if str(product_id).isdigit()
    )
    candidates = set()
    for previous_id, next_id in zip(product_ids, product_ids[1:]):
        gap_size = next_id - previous_id
        if 1 < gap_size <= GAP_PRODUCT_MAX_GAP:
            candidates.update(
                str(product_id)
                for product_id in range(previous_id + 1, next_id)
                if str(product_id) not in products
            )

    candidates = sorted(candidates, key=int)
    if len(candidates) > GAP_PRODUCT_MAX_CANDIDATES:
        LOGGER.warning(
            "FirstCry gap discovery found %s candidates; limiting to %s",
            len(candidates),
            GAP_PRODUCT_MAX_CANDIDATES,
        )
        candidates = candidates[:GAP_PRODUCT_MAX_CANDIDATES]
    return tuple(candidates)


def load_known_products(path=KNOWN_PRODUCTS_PATH):
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Could not read known product store %s: %s", path, exc)
        return {}

    raw_products = payload.values() if isinstance(payload, dict) else payload
    if not isinstance(raw_products, list) and not hasattr(raw_products, "__iter__"):
        LOGGER.warning("Ignoring unexpected known product store format in %s", path)
        return {}

    known_products = {}
    for raw_product in raw_products:
        product = _normalise_known_product(raw_product)
        if product is not None:
            known_products[product["id"]] = product
    return known_products


def save_known_products(products, path=KNOWN_PRODUCTS_PATH):
    existing_products = load_known_products(path)
    for product in products.values():
        normalised_product = _normalise_known_product(product)
        if normalised_product is not None:
            existing_products[normalised_product["id"]] = {
                "id": normalised_product["id"],
                "name": normalised_product["name"],
                "link": normalised_product["link"],
                "image": normalised_product["image"],
            }

    try:
        path.write_text(
            json.dumps(existing_products, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError as exc:
        LOGGER.warning("Could not update known product store %s: %s", path, exc)


def load_watchlist_ids(path=WATCHLIST_PATH):
    if not path.exists():
        return set()

    try:
        return _extract_product_ids(path.read_text(encoding="utf-8"))
    except OSError as exc:
        LOGGER.warning("Could not read watchlist %s: %s", path, exc)
        return set()


def _extract_balanced_json(text, start_index):
    depth = 0
    in_string = False
    escaped = False

    for index in range(start_index, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]

    raise ApiScrapeError("FirstCry product detail page has incomplete JSON data")


def parse_api_product(raw_product):
    product_id = str(raw_product.get("PId", "")).strip()
    name = str(raw_product.get("PNm", "")).strip()
    if not product_id or not name:
        raise ApiScrapeError("FirstCry listing API returned a product without an ID or name")

    stock_count = max(0, _parse_int(raw_product.get("CrntStock")))
    return {
        "id": product_id,
        "name": name,
        "in_stock": stock_count > 0,
        "stock_count": stock_count,
        "link": _build_product_link(product_id, name),
        "image": _build_image_url(raw_product.get("Images")),
        "stock_signal": "listing_api",
    }


def _parse_json_assignment(html, pattern, missing_message):
    match = pattern.search(html)
    if not match:
        raise ApiScrapeError(missing_message)

    json_start = html.find("{", match.end())
    if json_start < 0:
        raise ApiScrapeError("FirstCry product detail page is missing JSON data")

    try:
        return json.loads(_extract_balanced_json(html, json_start))
    except json.JSONDecodeError as exc:
        raise ApiScrapeError("FirstCry product detail page has invalid JSON data") from exc


def parse_detail_api_stock_count(payload, product_id):
    product_id = str(product_id)
    try:
        for product in payload.get("PColor") or []:
            if str(product.get("pid")) == product_id:
                return max(0, _parse_int(product.get("CS")))

        product_info = payload["PInfo"]
        if str(product_info.get("pid")) == product_id:
            return max(0, _parse_int(product_info.get("CurSt")))
    except (KeyError, TypeError) as exc:
        raise ApiScrapeError("FirstCry product API returned unexpected stock data") from exc
    raise ApiScrapeError("FirstCry product API returned mismatched product data")


def parse_detail_stock_count(html, product_id):
    try:
        payload = json.loads(html)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        return parse_detail_api_stock_count(payload, product_id)

    product_details = _parse_json_assignment(
        html,
        CURRENT_PRODUCT_DETAIL_JSON_PATTERN,
        "FirstCry product detail page is missing CurrentProductDetailJSON",
    )

    try:
        stock_count = product_details[str(product_id)]["CS"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ApiScrapeError("FirstCry product detail page has unexpected stock data") from exc
    return max(0, _parse_int(stock_count))


def parse_gap_product(payload, product_id):
    product = parse_known_product(payload, product_id)
    if product is None or product["stock_count"] <= 0:
        return None

    return {
        **product,
        "in_stock": True,
        "stock_signal": "gap_product_api",
    }


def parse_known_product(payload, product_id):
    product_id = str(product_id)
    if not isinstance(payload, dict):
        return None

    product_info = payload.get("PInfo") or {}
    if str(product_info.get("pid")) != product_id:
        return None
    if str(product_info.get("BID")) != "113":
        return None

    name = str(product_info.get("pnm") or "").strip()
    if not name or "hot wheel" not in name.lower():
        return None

    try:
        stock_count = parse_detail_api_stock_count(payload, product_id)
    except ApiScrapeError:
        return None

    return {
        "id": product_id,
        "name": name,
        "in_stock": stock_count > 0,
        "stock_count": stock_count,
        "detail_stock_count": stock_count,
        "link": _build_product_link(product_id, name),
        "image": _build_image_url(product_info.get("Img")),
        "stock_signal": "known_product_api",
    }


def fetch_detail_stock_count(product, opener=urlopen):
    request = Request(
        PRODUCT_DETAIL_API_URL.format(product_id=product["id"]),
        headers={
            "Accept": "application/json",
            "Referer": LISTING_URL,
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with opener(request, timeout=DETAIL_TIMEOUT_SECONDS) as response:
            html = response.read().decode("utf-8", errors="replace")
            return parse_detail_stock_count(html, product["id"])
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ApiScrapeError(f"FirstCry product detail request failed: {exc}") from exc


def fetch_gap_product(product_id, opener=urlopen):
    request = Request(
        PRODUCT_DETAIL_API_URL.format(product_id=product_id),
        headers={
            "Accept": "application/json",
            "Referer": LISTING_URL,
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with opener(request, timeout=DETAIL_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
            return parse_gap_product(payload, product_id)
    except json.JSONDecodeError as exc:
        raise ApiScrapeError("FirstCry gap product API returned invalid JSON") from exc
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ApiScrapeError(f"FirstCry gap product request failed: {exc}") from exc


def fetch_known_product_detail(product_id, opener=urlopen):
    request = Request(
        PRODUCT_DETAIL_API_URL.format(product_id=product_id),
        headers={
            "Accept": "application/json",
            "Referer": LISTING_URL,
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with opener(request, timeout=DETAIL_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
            return parse_known_product(payload, product_id)
    except json.JSONDecodeError as exc:
        raise ApiScrapeError("FirstCry known product API returned invalid JSON") from exc
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ApiScrapeError(f"FirstCry known product request failed: {exc}") from exc


def parse_cart_product_count(raw_response):
    try:
        payload = json.loads(raw_response)
        return max(0, _parse_int(payload["GetCartProductCountResult"]))
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ApiScrapeError("FirstCry cart API returned unexpected stock data") from exc


def fetch_cart_product_count(product, opener=urlopen):
    payload = json.dumps(
        {"ProCookie": f"NO^{product['id']}^1^0"},
        separators=(",", ":"),
    ).encode("utf-8")
    request = Request(
        CART_PRODUCT_COUNT_URL,
        data=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "Origin": "https://www.firstcry.com",
            "Referer": product["link"],
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with opener(request, timeout=CART_TIMEOUT_SECONDS) as response:
            return parse_cart_product_count(
                response.read().decode("utf-8", errors="replace")
            )
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ApiScrapeError(f"FirstCry cart API request failed: {exc}") from exc


def fetch_gap_products(products, product_fetcher=fetch_gap_product):
    candidate_ids = _build_gap_product_candidates(products)
    if not candidate_ids:
        return {}

    discovered_products = {}
    max_workers = min(GAP_PRODUCT_WORKERS, len(candidate_ids))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(product_fetcher, product_id): product_id
            for product_id in candidate_ids
        }
        for future in as_completed(futures):
            product_id = futures[future]
            try:
                product = future.result()
            except ApiScrapeError as exc:
                LOGGER.debug(
                    "Could not inspect FirstCry gap product %s: %s",
                    product_id,
                    exc,
                )
                continue
            if product is not None:
                discovered_products[product["id"]] = product

    if discovered_products:
        LOGGER.info(
            "Discovered %s in-stock Hot Wheels products from %s gap candidates",
            len(discovered_products),
            len(candidate_ids),
        )
    return discovered_products


def _build_known_product_probe_map(products, known_products, watchlist_ids):
    probe_products = {}
    for product in known_products.values():
        normalised_product = _normalise_known_product(product)
        if normalised_product is not None:
            probe_products[normalised_product["id"]] = normalised_product
    for product_id in watchlist_ids:
        if str(product_id).isdigit():
            probe_products.setdefault(str(product_id), None)
    for product_id, product in products.items():
        if not product.get("in_stock"):
            probe_products[str(product_id)] = product

    probe_ids = sorted(probe_products, key=_product_id_sort_key)
    if len(probe_ids) > KNOWN_PRODUCT_MAX_IDS:
        LOGGER.warning(
            "FirstCry known product probing found %s IDs; limiting to %s",
            len(probe_ids),
            KNOWN_PRODUCT_MAX_IDS,
        )
        probe_ids = probe_ids[:KNOWN_PRODUCT_MAX_IDS]
    return {product_id: probe_products[product_id] for product_id in probe_ids}


def _probe_known_product(product_id, product, product_fetcher, cart_fetcher):
    if product is None or not product.get("name") or not product.get("link"):
        product = product_fetcher(product_id)
    else:
        product = {**product, "id": str(product_id)}

    if product is None:
        return None

    try:
        cart_product_count = cart_fetcher(product)
    except ApiScrapeError as exc:
        if product.get("detail_stock_count", 0) > 0:
            return {
                **product,
                "pending_cart": True,
                "stock_signal": "known_product_cart_error",
            }
        raise exc

    detail_stock_count = max(0, _parse_int(product.get("detail_stock_count")))
    if cart_product_count > 0:
        return {
            **product,
            "in_stock": True,
            "stock_count": max(detail_stock_count, cart_product_count),
            "cart_product_count": cart_product_count,
            "stock_signal": "known_product_cart_count",
        }
    if detail_stock_count > 0:
        return {
            **product,
            "in_stock": False,
            "stock_count": 0,
            "cart_product_count": cart_product_count,
            "pending_cart": True,
            "stock_signal": "known_product_cart_pending",
        }
    return None


def fetch_known_products(
    products,
    known_products=None,
    watchlist_ids=None,
    product_fetcher=fetch_known_product_detail,
    cart_fetcher=fetch_cart_product_count,
):
    if known_products is None:
        known_products = load_known_products()
    if watchlist_ids is None:
        watchlist_ids = load_watchlist_ids()

    probe_products = _build_known_product_probe_map(
        products,
        known_products,
        watchlist_ids,
    )
    if not probe_products:
        return {}

    discovered_products = {}
    max_workers = min(KNOWN_PRODUCT_WORKERS, len(probe_products))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _probe_known_product,
                product_id,
                product,
                product_fetcher,
                cart_fetcher,
            ): product_id
            for product_id, product in probe_products.items()
        }
        for future in as_completed(futures):
            product_id = futures[future]
            try:
                product = future.result()
            except ApiScrapeError as exc:
                LOGGER.debug(
                    "Could not cart-probe known FirstCry product %s: %s",
                    product_id,
                    exc,
                )
                continue
            if product is not None:
                discovered_products[product["id"]] = product

    if discovered_products:
        LOGGER.info(
            "Cart-probed %s known FirstCry products; %s are buyable or pending",
            len(probe_products),
            len(discovered_products),
        )
    return discovered_products


_DEFAULT_CART_FETCHER = object()


def verify_in_stock_products(
    products,
    detail_fetcher=fetch_detail_stock_count,
    cart_fetcher=_DEFAULT_CART_FETCHER,
):
    in_stock_products = [
        product for product in products.values() if product.get("in_stock")
    ]
    if not in_stock_products:
        return products

    if cart_fetcher is _DEFAULT_CART_FETCHER:
        cart_fetcher = fetch_cart_product_count if VERIFY_CART_STOCK else None

    verified_products = dict(products)
    max_workers = min(DETAIL_WORKERS, len(in_stock_products))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(detail_fetcher, product): product
            for product in in_stock_products
        }

        for future in as_completed(futures):
            product = futures[future]
            try:
                detail_stock_count = future.result()
            except ApiScrapeError as exc:
                LOGGER.warning(
                    "Could not verify detail stock for %s (%s); keeping listing signal: %s",
                    product["id"],
                    product["name"],
                    exc,
                )
                verified_products[product["id"]] = {
                    **product,
                    "stock_signal": "listing_api_product_api_error",
                }
                continue

            verified_product = {
                **product,
                "detail_stock_count": detail_stock_count,
                "stock_count": detail_stock_count,
                "in_stock": detail_stock_count > 0,
                "stock_signal": "product_api_current_stock",
            }
            if detail_stock_count <= 0:
                LOGGER.info(
                    "Detail page rejected stale listing stock for %s (%s)",
                    product["id"],
                    product["name"],
                )
            elif cart_fetcher is not None:
                try:
                    cart_product_count = cart_fetcher(product)
                    verified_product["cart_product_count"] = cart_product_count
                    verified_product["stock_signal"] = "cart_product_count"
                    if cart_product_count <= 0:
                        verified_product["in_stock"] = False
                        verified_product["stock_count"] = 0
                        verified_product["pending_cart"] = True
                        verified_product["stock_signal"] = "cart_pending"
                        LOGGER.info(
                            "Cart API rejected stale product stock for %s (%s)",
                            product["id"],
                            product["name"],
                        )
                except ApiScrapeError as exc:
                    LOGGER.warning(
                        "Could not verify cart stock for %s (%s); keeping detail "
                        "signal: %s",
                        product["id"],
                        product["name"],
                        exc,
                    )
                    verified_product["stock_signal"] = (
                        "product_api_current_stock_cart_error"
                    )
            verified_products[product["id"]] = verified_product

    return verified_products


def _decode_page(raw_response):
    try:
        outer_payload = json.loads(raw_response)
        product_response = outer_payload["ProductResponse"]
        inner_payload = (
            json.loads(product_response)
            if isinstance(product_response, str)
            else product_response
        )
        products = inner_payload["Products"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ApiScrapeError("FirstCry listing API returned an unexpected response") from exc

    if not isinstance(products, list):
        raise ApiScrapeError("FirstCry listing API product data is not a list")

    return {
        "expected_products": _parse_expected_count(inner_payload.get("Count")),
        "products": products,
        "ttl_seconds": _parse_int(outer_payload.get("TTL"), default=-1),
    }


def fetch_api_page(page_number, opener=urlopen, sort_expression=None):
    params = {"PageNo": page_number, **API_PARAMS}
    if sort_expression:
        params["SortExpression"] = sort_expression
    request = Request(
        API_URL + "?" + urlencode(params),
        headers={
            "Accept": "application/json",
            "Referer": LISTING_URL,
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return _decode_page(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ApiScrapeError(f"FirstCry listing API request failed: {exc}") from exc


_DEFAULT_DETAIL_VERIFIER = object()
_DEFAULT_GAP_FETCHER = object()
_DEFAULT_KNOWN_FETCHER = object()


def _fetch_listing_products(page_fetcher, sort_expression):
    first_page = page_fetcher(1)
    expected_products = first_page["expected_products"]
    if expected_products is None:
        raise ApiScrapeError("FirstCry listing API response is missing its product count")
    pages_to_fetch = max(1, math.ceil(expected_products / PAGE_SIZE))
    if pages_to_fetch > MAX_PAGES:
        raise ApiScrapeError(
            f"FirstCry listing API requires {pages_to_fetch} pages; "
            f"configured maximum is {MAX_PAGES}"
        )

    pages = [first_page]
    for page_number in range(2, pages_to_fetch + 1):
        pages.append(page_fetcher(page_number))

    raw_products = []
    ttl_values = []
    for page in pages:
        if (
            page["expected_products"] is not None
            and page["expected_products"] != expected_products
        ):
            raise ApiScrapeError("FirstCry listing API product count changed mid-scrape")
        raw_products.extend(page["products"])
        if page["ttl_seconds"] >= 0:
            ttl_values.append(page["ttl_seconds"])

    if not raw_products:
        raise ApiScrapeError("FirstCry listing API returned no products")

    if (
        len(raw_products) < expected_products
        and len(raw_products) / expected_products < MIN_API_PARSE_RATIO
    ):
        raise ApiScrapeError(
            "FirstCry listing API returned an incomplete snapshot: "
            f"found {len(raw_products)} of {expected_products} products"
        )
    if len(raw_products) < expected_products:
        LOGGER.warning(
            "FirstCry listing API returned a near-complete %s snapshot: "
            "found %s of %s products",
            sort_expression,
            len(raw_products),
            expected_products,
        )

    return {
        "expected_products": expected_products,
        "raw_products": raw_products,
        "pages_fetched": len(pages),
        "ttl_values": ttl_values,
    }


def fetch_api_products(
    page_fetcher=fetch_api_page,
    detail_verifier=_DEFAULT_DETAIL_VERIFIER,
    sort_expressions=None,
    gap_product_fetcher=_DEFAULT_GAP_FETCHER,
    known_product_fetcher=_DEFAULT_KNOWN_FETCHER,
):
    started_at = time.monotonic()
    supports_sort_expression = _supports_sort_expression(page_fetcher)
    if sort_expressions is None:
        sort_expressions = (
            LISTING_SORT_EXPRESSIONS
            if supports_sort_expression
            else (API_PARAMS["SortExpression"],)
        )
    sort_expressions = tuple(sort_expressions)
    if not sort_expressions:
        raise ApiScrapeError("At least one FirstCry listing sort expression is required")

    raw_products = []
    expected_counts = []
    pages_fetched = 0
    ttl_values = []
    for sort_expression in sort_expressions:
        if supports_sort_expression:
            current_page_fetcher = (
                lambda page_number, sort_expression=sort_expression: page_fetcher(
                    page_number,
                    sort_expression=sort_expression,
                )
            )
        else:
            current_page_fetcher = page_fetcher

        snapshot = _fetch_listing_products(current_page_fetcher, sort_expression)
        expected_counts.append(snapshot["expected_products"])
        raw_products.extend(snapshot["raw_products"])
        pages_fetched += snapshot["pages_fetched"]
        ttl_values.extend(snapshot["ttl_values"])

        if not supports_sort_expression:
            break

    products = {}
    for raw_product in raw_products:
        product = parse_api_product(raw_product)
        _merge_product_signal(products, product)

    if gap_product_fetcher is _DEFAULT_GAP_FETCHER:
        gap_product_fetcher = (
            fetch_gap_products
            if VERIFY_GAP_PRODUCTS and page_fetcher is fetch_api_page
            else None
        )
    if gap_product_fetcher is not None:
        for product in gap_product_fetcher(products).values():
            _merge_product_signal(products, product)

    if detail_verifier is _DEFAULT_DETAIL_VERIFIER:
        detail_verifier = verify_in_stock_products if VERIFY_DETAIL_STOCK else None
    if detail_verifier is not None:
        products = detail_verifier(products)

    if known_product_fetcher is _DEFAULT_KNOWN_FETCHER:
        known_product_fetcher = (
            fetch_known_products
            if VERIFY_KNOWN_PRODUCTS and page_fetcher is fetch_api_page
            else None
        )
    if known_product_fetcher is not None:
        for product in known_product_fetcher(products).values():
            _merge_product_signal(products, product)

    if page_fetcher is fetch_api_page:
        save_known_products(products)

    elapsed_seconds = time.monotonic() - started_at
    result = ApiFetchResult(
        expected_products=max(expected_counts),
        raw_products=len(raw_products),
        unique_products=len(products),
        pages_fetched=pages_fetched,
        ttl_seconds=min(ttl_values) if ttl_values else None,
        elapsed_seconds=elapsed_seconds,
        sort_expressions=sort_expressions,
    )
    LOGGER.info(
        "Fetched %s unique API products from %s raw rows across %s pages "
        "and %s sorts in %.1fs (listing TTL: %s)",
        result.unique_products,
        result.raw_products,
        result.pages_fetched,
        len(result.sort_expressions),
        result.elapsed_seconds,
        result.ttl_seconds if result.ttl_seconds is not None else "unknown",
    )
    return products, result


def monitor():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    LOGGER.info("Starting FirstCry listing API monitor")
    tracker = ProductTracker(
        missing_confirmation_snapshots=MISSING_CONFIRMATION_SNAPSHOTS
    )

    try:
        while True:
            started_at = time.monotonic()
            try:
                products, _ = fetch_api_products()
                for event in tracker.update(products):
                    product = event["product"]
                    label = "NEW PRODUCT" if event["type"] == "NEW" else "BACK IN STOCK"
                    print(
                        f"{Fore.GREEN}[{label}] {product['name']} "
                        f"(stock: {product['stock_count']}) - "
                        f"{product['link']}{Style.RESET_ALL}"
                    )
            except ApiScrapeError:
                LOGGER.exception("API scrape failed; retaining the previous snapshot")

            duration = time.monotonic() - started_at
            time.sleep(max(1.0, POLL_INTERVAL_SECONDS - duration))
    except KeyboardInterrupt:
        print(f"\n{Fore.CYAN}Stopping API monitor.{Style.RESET_ALL}")


if __name__ == "__main__":
    monitor()
