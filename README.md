# Market Agent

Personal US market research terminal. Delayed data, no trading. UI name: **Sector Panel**.

v1 is shipped: Live, Outlook, Dynamics, Valuation, Opportunities, Watchlist — all from Postgres. Vendors and the writer LLM are never called from the UI.

| Doc | Use |
|-----|-----|
| [docs/northstar.md](docs/northstar.md) | Product contract (intent, sources, schema meaning, non-goals) |
| [docs/system.md](docs/system.md) | As-built map: job → table → API → UI |
| [docs/pipelines.md](docs/pipelines.md) | Setup, job order, flags, backup |
| [docs/decision_layer_plan.md](docs/decision_layer_plan.md) | Decision-layer phase tracker (status, next PR) |
| [AGENTS.md](AGENTS.md) | Cursor / Claude Code map |

## Run

```bash
cp .env.example .env          # fill keys — see pipelines.md
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d db       # Postgres on host port 5433
alembic upgrade head
```

First load and recurring recipes: [pipelines.md](docs/pipelines.md). Serve with `make api` and `make web` (UI `http://localhost:3000`, health `http://localhost:8000/health`).

## Config

| File | Purpose |
|------|---------|
| `config/universes.yaml` | Tape ETFs/indices, Live header, seed watchlist, valuation floor |
| `config/fred_series.yaml` | FRED levers + insight templates |
| `config/polymarket_slugs.yaml` | Odds slots + match rules (ingest rotates Gamma slugs) |
| `config/news_queries.yaml` | Google News RSS buckets |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |
