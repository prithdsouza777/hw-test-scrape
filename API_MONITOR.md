# FirstCry API Monitor

This monitor reads the same listing API FirstCry calls while the Hot Wheels
page lazy-loads:

```text
https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging
```

The response exposes each product's `CrntStock` quantity. For products where
the listing API claims stock is available, the monitor also calls
`CommonService.svc/getProduct/pid={pid}/uid=0` and confirms the matching
`PColor[].CS` value before checking FirstCry's cart product-count API with an
isolated synthetic cart cookie. The cart check catches products that still look
available upstream but are removed when added to cart. This check does not use
or modify your browser cart.

The dashboard separates the signals:

- `In Stock`: accepted by the cart product-count API.
- `Cart Pending`: listing/product API stock is positive, but cart validation still
  rejects the item. These products may become cartable after FirstCry's stock
  data finishes propagating.

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
- `FLASK_PORT`: dashboard port, default `5000`
