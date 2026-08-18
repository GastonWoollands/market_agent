# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

## Day 7 (current)

Dynamics shows **JdK RS-Ratio / RS-Momentum vs SPY** for tape sector/group ETFs, plus 1W/1M/3M/1Y returns and a 63-session indexed-to-100 sparkline. Computed from stored `bar_daily` by `jobs.compute_dynamics` into `rrg_point` / `return_stats`. The browser never calls Yahoo. Credit, vol, FX, and Polymarket are not on this plot.

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
python -m jobs.ingest_polymarket
python -m jobs.compute_dynamics

uvicorn api.main:app --reload --port 8000
# other terminal
npm --prefix web run dev
```

Or `make db migrate seed yahoo fred poly dynamics api` and `make web`.

## Config

| File | Purpose |
|------|---------|
| `config/universes.yaml` | Tape ETFs/indices, Live header, seed watchlist |
| `config/fred_series.yaml` | 13 FRED levers + insight templates |
| `config/polymarket_slugs.yaml` | Odds markets (slugs rotate — edit when a contract expires) |
| `config/news_queries.yaml` | Google News RSS buckets |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |

## Next

Day 8: Dynamics extras (relative overlay, sector table, 63d corr, lead-lag). No new vendors.
