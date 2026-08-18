# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

## Day 11–13 (current)

Valuation universe is US NYSE/Nasdaq names with **TTM revenue ≥ $1B** from official SEC EDGAR (`company_tickers_exchange.json` + `companyfacts.zip`). Membership also requires usable XBRL for EV/EBITDA: four 10-Q/10-K quarters, positive TTM EBITDA, FCF, shares, and net debt (target **700–1000** names). `metric_ttm` is stored in Postgres. Daily bars reuse the existing Yahoo/`yfinance` job (`--universe valuation`). EV/EBITDA vs 5y is Day 14.

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

uvicorn api.main:app --reload --port 8000
# other terminal
npm --prefix web run dev
```

Or `make db migrate seed yahoo fred poly dynamics news calendar pack outlook sec yahoo-val api` and `make web`.

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

Day 14–15: Valuation page (`valuation_daily`, %ile vs 5y). No new vendors.
