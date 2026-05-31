# Experimental FirstCry API Monitor

The existing Selenium monitor remains unchanged. This branch adds an optional
browser-free dashboard that reads the same listing API FirstCry calls while the
Hot Wheels page lazy-loads:

```text
https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging
```

The response exposes each product's `CrntStock` quantity. This lets the
alternative monitor distinguish a newly listed zero-stock card from an actual
zero-to-positive restock without inferring stock from rendered buttons.

## Run

Double-click `run_api.bat`, then open:

```text
http://127.0.0.1:5000
```

Run either `run.bat` or `run_api.bat`, not both at the same time, because both
dashboards use port `5000`.

## Important Caveat

FirstCry's listing API response includes a server-side `TTL` value. The
alternative monitor logs that value because the API may serve cached stock
data. Treat this as an experimental second signal and compare it against the
existing Selenium monitor before replacing the current workflow.

## Optional Environment Variables

- `FIRSTCRY_API_POLL_INTERVAL`: seconds between API scrape cycles, default `60`
- `FIRSTCRY_API_TIMEOUT`: HTTP timeout in seconds, default `20`
- `FIRSTCRY_API_MAX_PAGES`: maximum pagination safety limit, default `30`
- `FIRSTCRY_API_MISSING_CONFIRMATIONS`: missing snapshots required before a
  returning product alerts as restocked, default `2`
- `FLASK_PORT`: experimental dashboard port, default `5000`
