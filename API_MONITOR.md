# FirstCry API Monitor

This monitor reads the same listing API FirstCry calls while the Hot Wheels
page lazy-loads:

```text
https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging
```

The monitor merges the stock-relevant visible sort feeds by default because
FirstCry can publish newly stocked cards to one sort before another. The default
set is `popularity`, `NewArrivals`, `HighestDiscount`, and `Rating`.
The response exposes each product's `CrntStock` quantity. For products where
the listing API claims stock is available, the monitor also calls
`CommonService.svc/getProduct/pid={pid}/uid=0` and confirms the matching
`PColor[].CS` value before checking FirstCry's cart product-count API with an
isolated synthetic cart cookie. The cart check catches products that still look
available upstream but are removed when added to cart. This check does not use
or modify your browser cart.

After listing discovery, the monitor also probes small numeric gaps between
listed product IDs. FirstCry sometimes keeps cartable Hot Wheels product pages
live inside those gaps even when they are missing as standalone listing rows.
Gap products still must pass the product API and cart-count checks before they
show as in stock.

The monitor also keeps a local `known_products.json` cache of product IDs it
has seen before and cart-probes those IDs on later runs. This catches products
that FirstCry hides from the listing and product page add-to-cart button while
still accepting them through carousel/reorder add-to-cart paths. To seed old
order or recently viewed products, create `watchlist.txt` beside `run.bat` and
paste one product ID or FirstCry product URL per line. Both local files are
ignored by git.

The dashboard is centered on buyability, not the product page button:

- `Cart Accepted`: accepted by the cart product-count API. This is the main
  dashboard count and the only state that triggers a buyable alert.
- `Cart Pending`: listing/product API stock is positive, but cart validation still
  rejects the item. These products may become cartable after FirstCry's stock
  data finishes propagating.

For cart-accepted products, the dashboard shows `ADD TO CART` instead of an
open-product action. The button asks the local Flask app to open/reuse a
Selenium Chrome window with the `selenium_profile` browser profile, merges the
product into FirstCry's cart cookie format (`NO^{product_id}^1^0`), and opens
FirstCry's cart in that window. This is necessary because browser security
prevents a local `127.0.0.1` dashboard page from directly setting
`firstcry.com` cookies in your normal tab.

## Run

Double-click `run.bat`, then open:

```text
http://127.0.0.1:5000
```

Override the port with `FLASK_PORT` if another local app is already using
`5000`.

## Important Caveat

FirstCry's listing API response includes a server-side `TTL` value. The monitor
logs that value because the listing may serve cached stock data. Product API
and cart confirmation remove many stale positives, but a `Cart Pending` product
can still become buyable after FirstCry finishes propagating stock internally.

## Optional Environment Variables

- `FIRSTCRY_API_POLL_INTERVAL`: seconds between API scrape cycles, default `60`
- `FIRSTCRY_API_TIMEOUT`: HTTP timeout in seconds, default `20`
- `FIRSTCRY_API_VERIFY_DETAIL_STOCK`: set to `0` to disable product API
  stock confirmation, default enabled
- `FIRSTCRY_API_VERIFY_CART_STOCK`: set to `0` to disable isolated cart API
  stock confirmation, default enabled
- `FIRSTCRY_API_DETAIL_TIMEOUT`: product API HTTP timeout in seconds,
  default `10`
- `FIRSTCRY_API_CART_TIMEOUT`: cart API HTTP timeout in seconds, default `10`
- `FIRSTCRY_API_DETAIL_WORKERS`: concurrent product API checks, default `8`
- `FIRSTCRY_API_MAX_PAGES`: maximum pagination safety limit, default `30`
- `FIRSTCRY_API_MIN_PARSE_RATIO`: minimum listing API completeness ratio before
  rejecting a snapshot, default `0.95`
- `FIRSTCRY_API_MISSING_CONFIRMATIONS`: missing snapshots required before a
  returning product alerts as restocked, default `2`
- `FIRSTCRY_API_SORT_EXPRESSIONS`: comma-separated listing sorts to merge,
  default `popularity,NewArrivals,HighestDiscount,Rating`
- `FIRSTCRY_API_DISCOVER_GAP_PRODUCTS`: set to `0` to disable direct product
  probing for small gaps between listed product IDs, default enabled
- `FIRSTCRY_API_GAP_PRODUCT_MAX_GAP`: largest numeric product-ID gap to probe,
  default `20`
- `FIRSTCRY_API_GAP_PRODUCT_MAX_CANDIDATES`: maximum gap product IDs to probe
  per scrape, default `300`
- `FIRSTCRY_API_GAP_PRODUCT_WORKERS`: concurrent gap product API checks,
  default `12`
- `FIRSTCRY_API_PROBE_KNOWN_PRODUCTS`: set to `0` to disable cart probing for
  previously seen and watchlisted product IDs, default enabled
- `FIRSTCRY_API_KNOWN_PRODUCTS_FILE`: local product cache path, default
  `known_products.json`
- `FIRSTCRY_API_WATCHLIST_FILE`: optional product ID/URL watchlist path,
  default `watchlist.txt`
- `FIRSTCRY_API_KNOWN_PRODUCT_MAX_IDS`: maximum known/watchlist/current
  out-of-stock IDs to cart-probe per scrape, default `1000`
- `FIRSTCRY_API_KNOWN_PRODUCT_WORKERS`: concurrent known product cart checks,
  default `12`
- `FIRSTCRY_CART_BROWSER_PROFILE`: Selenium Chrome profile directory used by
  the dashboard `ADD TO CART` action, default `selenium_profile`
- `FLASK_PORT`: dashboard port, default `5000`
