# Market Agent — coding agents

Personal US research terminal. Delayed data, no trading. UI name: Sector Panel.

v1 is shipped. Do not implement Northstar gaps (Form 4, Alpaca, scheduler, Pi host, `filing` tables) unless `docs/northstar.md` is updated first.

Read `docs/northstar.md` before changing product intent, schema meaning, or source stack.
Read `docs/system.md` for orientation (job → table → API → UI).
Read `docs/pipelines.md` before running or adding jobs.
Do not paste those files into chat. Open them when the task needs them.

`agent/` is the Outlook/memo **writer** (Anthropic/Gemini SDK, pack-grounded).
This file steers **coding** agents (Cursor, Claude Code). Do not mix the two.

Layer conventions: `.cursor/rules/*.mdc`. Workflows: `.cursor/skills/`.
Claude Code: `CLAUDE.md` imports this file. Skills are the same tree via `.claude/skills`.

## Invariants

- Postgres is the system of record. Vendors are never called from the UI or from the writer LLM.
- Jobs are the only writers of market data. API is read-only except watchlist CRUD and refresh triggers.
- `api/` must not import `ingest`.
- Adapters return frozen Pydantic in `store/canonical.py`. Repos upsert (`ON CONFLICT`). Jobs orchestrate.
- `NUMERIC` / `Decimal` for money, yields, multiples. `float` only inside numpy, then cast back.
- `timestamptz` in UTC; display ET in the UI.
- Host Postgres is port **5433** (`DATABASE_URL` default). Container still uses 5432.
- Yahoo ≤2 req/s, `auto_adjust=False`, HTTP 429 fails fast. Timeouts/5xx retry ≤3.
- Writer: official `anthropic` / `google-genai` SDKs only. No LangChain. No tools. No live fetch.
- Citation check must pass or keep yesterday’s report (`agent/citations.py`).
- Do not add Redis, Kafka, Timescale, pgvector, scraping, or non-US listings without updating Northstar first.

## Layout

```text
ingest/     vendor adapters
store/      SQLAlchemy models + repos
jobs/       CLI writers
analytics/  Python → Postgres
agent/      pack + Outlook/memos
api/        FastAPI, `def` routes
web/        Next.js (dark terminal)
config/     yaml catalogs
```

Canonical examples: `ingest/yahoo/client.py`, `ingest/fred/client.py`,
`jobs/ingest_yahoo.py`, `store/repos.py`, `api/live.py`,
`web/lib/api.ts`, `agent/outlook.py`.

## Commands

Python 3.12, venv `.venv`, `pip install -e ".[dev]"`.
`make db migrate test api web`
Jobs: `python -m jobs.<module>` or matching `make` targets. See pipelines.md.
Lint: `ruff` (line-length 100). Tests: `pytest`.

## When changing X

- Schema contract (new table, vendor, universe, page) → Alembic + `store/models.py` + Northstar §8
- New vendor → Northstar §6 first, then new `ingest/<vendor>/`, yaml catalog if needed, job, tests with fixtures
- Outlook prose → `agent/prompts.py` + citation tests; never give the model fetch tools
- UI data → FastAPI schema first, then `web/lib/api.ts`; no vendor calls from the browser
