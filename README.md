# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

## Day 5 (current)

Click a FRED lever on Live (default **DGS10**) for a 1Y chart, Δ 1D/1W/1M/1Y, yaml insight, and watch tickers. Risk-On v1 is a z-score blend of stored VIXCLS, HYG/LQD, RSP/SPY, T10Y2Y (not inverted), and cyclicals vs defensives. The browser still does not call FRED or Yahoo.

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
npm --prefix web install
npm --prefix web run dev
```

Or `make db migrate seed yahoo fred api` and `make web`.

`GET /live?lever=DGS10` includes `drilldown` and `risk_on`. Yield deltas are last minus a prior print, not an equity percent return.

## Config

| File | Purpose |
|------|---------|
| `config/universes.yaml` | Tape ETFs/indices, Live header, seed watchlist |
| `config/fred_series.yaml` | 13 FRED levers + insight templates |
| `config/polymarket_slugs.yaml` | Odds markets (slugs rotate — edit when a contract expires) |
| `config/news_queries.yaml` | Google News RSS buckets |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |

## Next

Day 6: Polymarket Gamma adapter and Fed / inflation / recession odds on Live (not mixed into Risk-On).
