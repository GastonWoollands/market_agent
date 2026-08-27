---
name: add-adapter
description: Adds a vendor ingest adapter (client, parse, errors, canonical models, job, fixture tests). Use when adding a data vendor, ingest source, HTTP client, or Yahoo/FRED/SEC-style adapter.
---

# Add ingest adapter

If this is a new v1 source, update `docs/NORTHSTAR.md` §6 first. Do not add scraping, unofficial APIs, or non-US listings.

## Layout

```text
ingest/<vendor>/
  __init__.py     # export client + parse helpers
  client.py       # fetch only; return canonical models
  parse.py        # vendor payload → store.canonical
  errors.py       # typed errors (HttpError with status_code)
```

Templates: HTTP → `ingest/fred/`. Yahoo/yfinance → `ingest/yahoo/` (do not copy Yahoo’s session hacks into HTTP clients).

## Steps

1. Add frozen Pydantic in `store/canonical.py` only if no existing type fits.
2. Add `upsert_*` in `store/repos.py` (`ON CONFLICT`). Schema change → Alembic + `store/models.py`.
3. Curated lists go in `config/*.yaml` + `store/catalog.py`, not hardcoded tickers.
4. Wire a job (`python -m jobs.ingest_<vendor>`). Follow skill `add-job`.
5. Tests: parse fixtures with no network (`tests/test_<vendor>_parse.py`). Assert Decimal/date types.
6. Rate limits: reuse `ingest.retry.retry_call` for timeouts/5xx. **429 fails fast.** Yahoo stays ≤2 req/s via `TokenBucket`.

Do not import the adapter from `api/` or `web/`.
