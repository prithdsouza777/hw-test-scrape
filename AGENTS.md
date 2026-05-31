# Hot Wheels FirstCry Monitor

## Purpose

This repository monitors the FirstCry Hot Wheels listing for newly listed and
restocked products using FirstCry's listing/product/cart API signals. Keep
scraper changes conservative: FirstCry responses can change without notice, and
a failed scrape must not be treated as a real out-of-stock event.

## Development Rules

- Preserve user-created local files such as `log.xlsx`, browser profiles, and
  inspection scripts unless the requested task explicitly includes them.
- Keep generated files, browser profiles, Python bytecode, and local virtual
  environments out of version control.
- Do not add one-off inspection or auto-buy helper scripts to the repository.
  Keep the supported entry points focused on `run.bat`, `app.py`, and
  `monitor_api.py`.
- Prefer deterministic parser tests with small API/HTML fixtures over tests that
  require live FirstCry requests.
- Validate scraper changes with the live FirstCry listing when network access
  is available.
- Do not swallow parser failures silently. Log enough context to diagnose
  selector drift while continuing past malformed individual product cards.
- Do not replace a known-good product snapshot with an empty scrape.

## Git Commit Convention

Always commit by feature set. Split commits by:

- Layer: frontend, backend, database, config/infra, docs, tests
- Purpose: bug fix, new feature, and refactor are separate commits
- Scope: unrelated areas are separate commits even within one layer

Only bundle everything into a single commit if explicitly requested.
