# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

## Day 6 (current)

Live shows **market-implied** Polymarket odds (Fed / inflation / recession) from `odds_snapshot`. Odds are **not** an input to Risk-On. The browser never calls Gamma.

Slugs in `config/polymarket_slugs.yaml` expire; if ingest 404s it logs Gamma search candidates — paste a replacement slug, do not scrape the site.

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

uvicorn api.main:app --reload --port 8000
# other terminal
npm --prefix web run dev
```

Or `make db migrate seed yahoo fred poly api` and `make web`.

## Config

| File | Purpose |
|------|---------|
| `config/universes.yaml` | Tape ETFs/indices, Live header, seed watchlist |
| `config/fred_series.yaml` | 13 FRED levers + insight templates |
| `config/polymarket_slugs.yaml` | Odds markets (slugs rotate — edit when a contract expires) |
| `config/news_queries.yaml` | Google News RSS buckets |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |

## Next

Day 7: Dynamics core (returns, RRG, indexed-to-100). No new vendors.
