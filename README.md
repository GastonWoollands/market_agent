# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

**Runbook:** [docs/PIPELINES.md](docs/PIPELINES.md) — setup, job order, when to re-run, flags, backup.

## Day 19 (current)

Hardening reuses the existing adapters. Yahoo 429 still fails fast. Timeouts and 5xx retry up to 3 times. Kill a Yahoo ingest mid-run and continue with `--resume`; upserts do not duplicate bars. Postgres is on **host port 5433**.

```bash
python -m jobs.ingest_yahoo --resume
python -m jobs.backfill yahoo --universe tape --resume
bash scripts/pg_dump.sh
```

## Config

| File | Purpose |
|------|---------|
| `config/universes.yaml` | Tape ETFs/indices, Live header, seed watchlist, valuation floor |
| `config/fred_series.yaml` | 13 FRED levers + insight templates |
| `config/polymarket_slugs.yaml` | Odds markets (slugs rotate — edit when a contract expires) |
| `config/news_queries.yaml` | Google News RSS buckets |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |

## Next

Day 20 (optional): same Compose on a Pi; restore dump; Outlook job without the Mac.
