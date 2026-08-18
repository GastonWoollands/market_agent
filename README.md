# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

## Day 18 (current)

Watchlist CRUD writes `universe_member` only. Quotes and 63-session sparklines are served from Postgres (`quote_latest` / `bar_daily`). Charts are the official TradingView advanced-chart widget (client-side, no ingest). Yahoo 5m extended hours (`prepost=True`) are stored in `bar_intraday` for **tape + watchlist only**, using the existing `YahooClient` — not a second vendor client.

```bash
python -m jobs.ingest_yahoo --universe watchlist
python -m jobs.ingest_intraday
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
python -m jobs.compute_scores
python -m jobs.generate_memos --template
python -m jobs.ingest_yahoo --universe watchlist
python -m jobs.ingest_intraday

uvicorn api.main:app --reload --port 8000
# other terminal
npm --prefix web run dev
```

Or `make db migrate seed yahoo fred poly dynamics news calendar pack outlook sec yahoo-val valuation scores memos yahoo-watch intraday api` and `make web`.

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

Day 19: Hardening (retries, stale badges, backfill, pg_dump). No new vendors.
