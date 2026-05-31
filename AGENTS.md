# Hot Wheels FirstCry Monitor

## Purpose

This repository monitors the FirstCry Hot Wheels listing for newly listed and
restocked products. Keep scraper changes conservative: FirstCry markup can
change without notice, and a failed scrape must not be treated as a real
out-of-stock event.

## Development Rules

- Preserve user-created local files such as `log.xlsx`, `selenium_profile/`,
  and inspection scripts unless the requested task explicitly includes them.
- Keep generated files, browser profiles, Python bytecode, and local virtual
  environments out of version control.
- Do not add one-off Selenium inspection or auto-buy helper scripts to the
  repository. Keep the supported entry points focused on `run.bat`,
  `run_api.bat`, `app.py`, `app_api.py`, `monitor_selenium.py`, and
  `monitor_api.py`.
- Prefer deterministic parser tests with small HTML fixtures over tests that
  require a live browser.
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
