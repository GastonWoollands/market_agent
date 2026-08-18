# Market Agent

Personal US market research terminal. Delayed data, no trading.

**Northstar:** [docs/NORTHSTAR.md](docs/NORTHSTAR.md) — product, schema, sources, and day-by-day plan. Read that before adding features.

## Day 10 (current)

Outlook brief is written from the stored evidence pack. The job uses the official **Anthropic** or **Gemini** SDK (`AGENT_PROVIDER`), then a Python citation check. If the API is down or no key is set, a template fills from pack numbers. The browser never calls a model.

Postgres is published on **host port 5433**.

```bash
cp .env.example .env   # set FRED_API_KEY, FINNHUB_API_KEY, and ANTHROPIC_API_KEY or GEMINI_API_KEY
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
python -m jobs.generate_outlook          # or --template

uvicorn api.main:app --reload --port 8000
# other terminal
npm --prefix web run dev
```

Or `make db migrate seed yahoo fred poly dynamics news calendar pack outlook api` and `make web`.

## Config

| File | Purpose |
|------|---------|
| `config/universes.yaml` | Tape ETFs/indices, Live header, seed watchlist |
| `config/fred_series.yaml` | 13 FRED levers + insight templates |
| `config/polymarket_slugs.yaml` | Odds markets (slugs rotate — edit when a contract expires) |
| `config/news_queries.yaml` | Google News RSS buckets |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |

## Next

Day 11–13: Valuation universe (SEC). No new LLM vendors.
