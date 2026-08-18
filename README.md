# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

## Day 14–15 (current)

`valuation_daily` is EV/EBITDA vs each name’s own 5y daily multiple, plus 1y EBITDA growth × multiple re-rating. All of it is computed in Python from stored bars + SEC TTM — no new vendor. The Valuation page headline **N of M with a comparable multiple** is a SQL count (`comparable` needs ≥252 trading days of a positive multiple).

```bash
python -m jobs.ingest_sec
python -m jobs.ingest_yahoo --universe valuation
python -m jobs.compute_valuation
```

Postgres is published on **host port 5433**.

```bash
cp .env.example .env   # set FRED_API_KEY, FINNHUB_API_KEY, SEC_USER_AGENT (real email)
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
python -m jobs.generate_outlook --template
python -m jobs.ingest_sec
python -m jobs.ingest_yahoo --universe valuation
python -m jobs.compute_valuation

uvicorn api.main:app --reload --port 8000
# other terminal
npm --prefix web run dev
```

Or `make db migrate seed yahoo fred poly dynamics news calendar pack outlook sec yahoo-val valuation api` and `make web`.

Set `SEC_USER_AGENT` to `MarketAgent you@real-email`. The first `ingest_sec` downloads `companyfacts.zip` into `data/sec/` (gitignored).

## Config

| File | Purpose |
|------|---------|
| `config/universes.yaml` | Tape ETFs/indices, Live header, seed watchlist, valuation floor |
| `config/fred_series.yaml` | 13 FRED levers + insight templates |
| `config/polymarket_slugs.yaml` | Odds markets (slugs rotate — edit when a contract expires) |
| `config/news_queries.yaml` | Google News RSS buckets |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |

## Next

Day 16–17: Opportunities (quant scores + memos). No new vendors.
