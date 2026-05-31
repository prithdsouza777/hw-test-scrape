# Experimental FirstCry API Monitor

The existing Selenium monitor remains unchanged. This branch adds an optional
browser-free dashboard that reads the same listing API FirstCry calls while the
Hot Wheels page lazy-loads:

```text
https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging
```

The response exposes each product's `CrntStock` quantity. For products where
the listing API claims stock is available, the monitor also fetches the
product-detail page and confirms `ProductDetailJSON.PInfo.CurSt` before showing
that product as in stock. This reduces the stale listing false positives that
can happen while FirstCry is publishing a restock.

## Run

Double-click `run_api.bat`, then open:

```text
http://127.0.0.1:5001
```

`run_api.bat` uses port `5001`, so it can run beside the existing Selenium
dashboard on port `5000` while you compare signals.

## Important Caveat

FirstCry's listing API response includes a server-side `TTL` value. The
alternative monitor logs that value because the listing may serve cached stock
data. Detail-page confirmation should remove many stale positives, but this is
still an experimental second signal and should be compared against the existing
Selenium monitor before replacing the current workflow.

## Optional Environment Variables

- `FIRSTCRY_API_POLL_INTERVAL`: seconds between API scrape cycles, default `60`
- `FIRSTCRY_API_TIMEOUT`: HTTP timeout in seconds, default `20`
- `FIRSTCRY_API_VERIFY_DETAIL_STOCK`: set to `0` to disable product-detail
  stock confirmation, default enabled
- `FIRSTCRY_API_DETAIL_TIMEOUT`: product-detail HTTP timeout in seconds,
  default `10`
- `FIRSTCRY_API_DETAIL_WORKERS`: concurrent detail-page checks, default `8`
- `FIRSTCRY_API_MAX_PAGES`: maximum pagination safety limit, default `30`
- `FIRSTCRY_API_MISSING_CONFIRMATIONS`: missing snapshots required before a
  returning product alerts as restocked, default `2`
- `FLASK_PORT`: experimental dashboard port, default `5000`
