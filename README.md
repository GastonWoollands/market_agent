# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

## Day 3 (current)

`GET /live` reads `quote_latest` and `bar_daily` from Postgres. The Next.js Live page never calls Yahoo.

Postgres is published on **host port 5433**.

```bash
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d db
alembic upgrade head
python -m jobs.seed_tape
python -m jobs.ingest_yahoo

uvicorn api.main:app --reload --port 8000
# other terminal
npm --prefix web run dev
```

Or `make db migrate seed yahoo api` and `make web`.

`GET /health` should show `daily_bars` > 0 and an `ingest_yahoo` job with status `ok`. SPY and XLK must have rows or the job fails. `GET /live` then returns the header (`^GSPC`, QQQ, `^RUT`, `^DJI`, USO, GLD) and sector movers.

Yahoo is unofficial. ATS may return 429 for non-browser TLS or a flagged IP. The job uses `yfinance` (`curl_cffi`) and is idempotent. If `finance.yahoo.com` itself is 429, wait hours (or change network), then:

```bash
python -m jobs.ingest_yahoo --tickers SPY,XLK
python -m jobs.ingest_yahoo
```

## Config

| File | Purpose |
|------|---------|
| `config/universes.yaml` | Tape ETFs/indices, Live header, seed watchlist |
| `config/fred_series.yaml` | 13 FRED levers |
| `config/polymarket_slugs.yaml` | Odds markets (slugs rotate — edit when a contract expires) |
| `config/news_queries.yaml` | Google News RSS buckets |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |

## Next

Day 4: FRED adapter and Live sidebar (last value + 1D change).
