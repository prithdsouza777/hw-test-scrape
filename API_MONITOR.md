# FirstCry API Monitor

This monitor reads the same listing API FirstCry calls while the Hot Wheels
page lazy-loads:

```text
https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging
```

The monitor merges the stock-relevant visible sort feeds by default because
FirstCry can publish newly stocked cards to one sort before another. The default
set is `popularity`, `NewArrivals`, `BestSeller`, `HighestDiscount`, and
`Rating`.
The response exposes each product's `CrntStock` quantity. For products where
the listing API claims stock is available, the monitor also calls
`CommonService.svc/getProduct/pid={pid}/uid=0` and confirms the matching
`PColor[].CS` value before checking FirstCry's cart product-count API with an
isolated synthetic cart cookie. The cart check catches products that still look
available upstream but are removed when added to cart. This check does not use
or modify your browser cart.

The product API can also expose stocked Hot Wheels sibling variants in
`PColor[]` before those product IDs appear as standalone listing rows. The
monitor inspects variant-capable listing rows and adds only positive Hot Wheels
variant candidates; those candidates still pass through the same product API,
cart-count, and checkout stock verification before they are treated as buyable.

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

For cart-accepted products, the dashboard shows both `VIEW PRODUCT` and
`ADD TO CART`. `VIEW PRODUCT` is a normal `target="_blank"` product page link.
`ADD TO CART` is handled by the local Chrome extension on the dashboard page.
FirstCry's checkout/cart page for an already-added product is
`https://checkout.firstcry.com/pay`.

Load the local unpacked Chrome extension in `firstcry_auto_cart_extension`.
Open your FirstCry orderdetails page once so the extension can remember the
URL. When `ADD TO CART` is clicked, the extension opens that orderdetails page
with the dashboard product ID in the hash, creates a hidden recent-order style
button, calls FirstCry's `sliderproductAddcart(productId, 1, button)` function,
and goes to checkout only after the target product appears in the FirstCry cart
cookie. If that recent-order call does not confirm, the runner writes the same
cart cookie format on `firstcry.com` before checkout. This deliberately bypasses
the visible product-page button because FirstCry can accept a product through
reorder/recently-viewed paths before the PDP UI shows an add button. If
FirstCry's cart system stops accepting the product between the monitor check and
your click, checkout may still remove it; that is the real buyability race.

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
  default `popularity,NewArrivals,BestSeller,HighestDiscount,Rating`
- `FIRSTCRY_API_DISCOVER_GAP_PRODUCTS`: set to `0` to disable direct product
  probing for small gaps between listed product IDs, default enabled
- `FIRSTCRY_API_DISCOVER_VARIANT_PRODUCTS`: set to `0` to disable product API
  sibling variant discovery, default enabled
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
- `FLASK_PORT`: dashboard port, default `5000`
