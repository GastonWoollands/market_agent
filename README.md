# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

## Day 9 (current)

Outlook shows a **sources table** (vendor, job as_of, row counts from Postgres), Google News RSS tape, and a calendar (yaml FOMC/CPI plus Finnhub watchlist earnings). Evidence pack is built in Python and stored for Day 10. The browser never calls Google or Finnhub. Claude is not in this day.

Postgres is published on **host port 5433**.

```bash
cp .env.example .env   # set FRED_API_KEY and FINNHUB_API_KEY
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d db
alembic upgrade head
python -m jobs.seed_tape
python -m jobs.ingest_yahoo
python -m jobs.ingest_fred
python -m jobs.ingest_polymarket
python -m jobs.compute_dynamics
python -m jobs.ingest_news
python -m jobs.ingest_calendar
python -m jobs.build_pack

uvicorn api.main:app --reload --port 8000
# other terminal
npm --prefix web run dev
```

Or `make db migrate seed yahoo fred poly dynamics news calendar pack api` and `make web`.

## Config

| File | Purpose |
|------|---------|
| `config/universes.yaml` | Tape ETFs/indices, Live header, seed watchlist |
| `config/fred_series.yaml` | 13 FRED levers + insight templates |
| `config/polymarket_slugs.yaml` | Odds markets (slugs rotate — edit when a contract expires) |
| `config/news_queries.yaml` | Google News RSS buckets |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |

## Next

Day 10: Claude Outlook (pack → structured brief, citation check). No new vendors.
