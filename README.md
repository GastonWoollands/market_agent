# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

## Day 4 (current)

`GET /live` reads Yahoo tape tables **and** FRED `macro_observation`. The browser never calls FRED or Yahoo.

Postgres is published on **host port 5433**.

```bash
cp .env.example .env   # set FRED_API_KEY
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d db
alembic upgrade head
python -m jobs.seed_tape
python -m jobs.ingest_yahoo
python -m jobs.ingest_fred

uvicorn api.main:app --reload --port 8000
# other terminal
npm --prefix web run dev
```

Or `make db migrate seed yahoo fred api` and `make web`.

`GET /live` includes `macro` in catalog order. **DGS10** (10Y yield) must have rows or `ingest_fred` fails. Levels are native FRED units; 1D change is last minus previous print, not an equity-style percent return.

Yahoo is unofficial. If `finance.yahoo.com` returns 429, wait and retry `python -m jobs.ingest_yahoo --tickers SPY,XLK`.

FRED is the official `series/observations` JSON API (`httpx`). Request a key at https://fred.stlouisfed.org/docs/api/api_key.html.

## Config

| File | Purpose |
|------|---------|
| `config/universes.yaml` | Tape ETFs/indices, Live header, seed watchlist |
| `config/fred_series.yaml` | 13 FRED levers |
| `config/polymarket_slugs.yaml` | Odds markets (slugs rotate — edit when a contract expires) |
| `config/news_queries.yaml` | Google News RSS buckets |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |

## Next

Day 5: Live lever drill-down (chart, Δ 1D/1W/1M/1Y, insight templates) and Risk-On v1.
