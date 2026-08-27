# Market Agent — Northstar

Personal US research terminal: delayed data, no trading. Fetch → store in Postgres → compute → serve a dashboard → write a daily brief and opportunity list from **stored evidence only**.

**v1 is shipped.** This file is the product contract, not a build plan. Changes must not contradict it. If product intent, sources, universes, pages, or schema *meaning* change, update this document first.

**Product name (UI):** Sector Panel
**Language:** English
**Charts:** TradingView embed
**Host:** Mac now; Raspberry Pi (or similar) later via the same Docker Compose stack — not a current task.

| Need | File |
|------|------|
| Job → table → API → UI | [system.md](system.md) |
| When and how to run jobs | [pipelines.md](pipelines.md) |
| Coding-agent map | [AGENTS.md](../AGENTS.md) |

Column lists, job flags, and formulas live in code (`store/models.py`, `jobs/`, `analytics/`). Do not copy them here.

---

## 1. Goal

Give a single operator a dense, honest view of US markets:

- What macro and sectors are doing (**Live**, **Dynamics**)
- What is cheap vs history (**Valuation**)
- What is worth reading today (**Opportunities**)
- Names you track (**Watchlist**)
- A weekday morning **Outlook** with three pack-grounded sections: US macro spine (rates, inflation, labor, fiscal, a short global context), what the tape and market-implied odds are pricing, and what is on the calendar in the next sessions

EA / UK / JP / globe appear as **FRED context series** (policy rate, FX, lag-stamped foreign 10Ys), not as non-US listings or a second terminal.

Every number on screen comes from Postgres. Vendors are never called from the UI or from the LLM.

---

## 2. Non-goals

- Trading, orders, paper fills
- Real-time / WebSocket quotes
- X / Twitter
- Non-US listings as first-class (no `.L`, `.T`, CEDEARs)
- Scraping Finviz, Investing.com, TradingView unofficial APIs, Google Finance RPC
- Letting the writer search the web or call Yahoo/SEC at generation time
- Microcap “venture” names (revenue < $1B) — later as a second universe
- Redis, Kafka, TimescaleDB, pgvector — not until a measured need
- In-process job scheduler (APScheduler). Unattended runs are `cron` / `launchd` calling CLIs when you want them; until then, operators run `make` / `python -m jobs…`

Do not implement a non-goal because it appeared in an older plan. Change this section first.

---

## 3. Pages

| Tab | Job |
|-----|-----|
| **Live** | Indices, sector tape, macro levers, Polymarket odds, Risk-On pill, drill-down chart |
| **Outlook** | Structured brief (macro / market / near-term), numeric snapshot from the pack, news tape, near calendar, **sources freshness table** |
| **Dynamics** | RRG, indexed relative performance, sector table, correlation, lead-lag |
| **Valuation** | EV/EBITDA vs own 5y range, industry, growth × re-rating |
| **Opportunities** | Quant scores + writer memos on top names (gems **inside** the $1B+ universe) |
| **Watchlist** | User tickers, quote cards, TradingView widget |

**Honest constraint:** $1B+ TTM revenue is mid/large cap. “Early gems” here means *mispriced or improving quality names with full SEC history*, not seed-stage companies.

---

## 4. Architecture

```text
ingest adapters  →  jobs (CLI)  →  PostgreSQL  →  FastAPI  →  Next.js
                         │
                         ├→ analytics tables (same DB)
                         └→ evidence_pack JSONB → agent (Outlook + top-N memos)
```

| Layer | Choice | Why |
|-------|--------|-----|
| DB | **PostgreSQL 16** in Docker Compose + named volume | Concurrent API + jobs, JSONB, proper types, Pi-portable |
| Migrations | Alembic | Schema is the contract |
| ORM | SQLAlchemy 2.0 **sync** + Pydantic schemas | Jobs and API share models |
| API | FastAPI, `def` routes (threadpool) | One connection style |
| Jobs | Python CLIs (`python -m jobs…` / `make`) | Timezone `America/New_York` in pipelines.md |
| HTTP | `httpx` + token bucket; Yahoo via `yfinance` | FRED/SEC use httpx; Yahoo ≤2 req/s (`curl_cffi` TLS) |
| UI | Next.js + Tailwind + shadcn | Dense dark terminal |
| Charts | TradingView embed; Recharts/SVG for sparklines, RRG, heatmap | Don’t rebuild a charting platform |
| LLM | Official Anthropic or Gemini SDK; template fallback | Writer only, pack-grounded |

**Postgres is the system of record.** No SQLite. Optional Parquet export can come later for notebooks; do not dual-write. `yfinance` may keep a small local timezone cache; that is not market data.

Adapters return frozen Pydantic in `store/canonical.py`. Repos upsert (`ON CONFLICT`). Jobs orchestrate. `api/` never imports `ingest`.

---

## 5. Postgres

One service, one volume, one database. See `docker-compose.yml`. Setup and backup: pipelines.md.

- App reads `DATABASE_URL` (default `postgresql://market:market@localhost:5433/market_agent`; container still listens on 5432)
- Jobs are the only writers of market data. API is read-only except watchlist CRUD and refresh triggers
- `ON CONFLICT` upserts everywhere (idempotent jobs)
- `timestamptz` always; store UTC, display ET in the UI
- Money, yields, multiples: `NUMERIC` — never `float` for values you compare or rank
- JSONB for evidence packs, news extras, Polymarket raw
- SQLAlchemy pool_size 5, max_overflow 5 — enough for one user

Vanilla Postgres is enough for ~900 names × 10y daily bars. Do not add 1-minute bars for the full universe.

---

## 6. Source stack

Frozen for v1. A new vendor is a contract change: update this section first. Catalogs in `config/`. Cadence (intended, not scheduled) is in pipelines.md.

| Input | Vendor | Typical cadence |
|-------|--------|-----------------|
| Daily OHLCV, sector ETFs, proxy levers | Yahoo via `yfinance` behind `YahooClient` | 16:30 ET |
| Quote tape (delayed) | Same yfinance session | 60s in session when you re-run |
| Pre/post 5m gaps | Yahoo 5m | ~07:30 ET, **tape + watchlist only** |
| Yields, VIX, CPI/PCE (as indexes; pack computes YoY/MoM), OAS, DXY, WTI, real yield, breakevens, payrolls, claims, debt/GDP, ECB policy, dollar crosses, lag-stamped foreign 10Ys | FRED (`config/fred_series.yaml`) | 06:00 ET |
| Fed / inflation / recession / geo odds | Polymarket Gamma API (`config/polymarket_slugs.yaml`) | 15–60 min in session |
| Headlines | Google News RSS (`config/news_queries.yaml`) | 30 min |
| Earnings calendar + EPS/rev est. | Finnhub free | 07:00 ET |
| FOMC, CPI, PCE, NFP, GDP, JOLTS, ECB/BoE/BoJ, elections | curated `config/catalysts.yaml` | hand, yearly |
| TTM metrics + valuation membership | SEC EDGAR companyfacts (bulk zip, then incremental) | nightly / monthly |
| Charts | TradingView widget | client-side, no ingest |

**Polymarket:** store implied probability + liquidity. UI label: market-implied; thin books are noisy.

**Yahoo:** ≤2 req/s, `auto_adjust=False`, HTTP 429 fails fast. Timeouts/5xx retry ≤3.

Do not add scraping, unofficial APIs, or non-US listings. Expanding the FRED catalog is not a new vendor. International **listings** stay out.

---

## 7. Universes

| Tier | Contents | Stored history |
|------|----------|----------------|
| **A Tape** | Indices/ETFs in `config/universes.yaml` | daily + quotes + 5m extended |
| **B Valuation / Opportunity** | US NYSE/Nasdaq, TTM revenue ≥ $1B, usable XBRL, Yahoo history | daily bars + SEC TTM + valuation |
| **C Watchlist** | user-defined | daily + 5m + TV chart |

Build B from SEC tickers + `companyfacts` (prefer bulk zip once, then incremental). Rebuild membership monthly. Floor: `config/universes.yaml` `valuation.min_revenue_usd`.

---

## 8. Schema

Table **purpose** lives here. Columns and constraints live in `store/models.py` and `alembic/versions/`. Adding a column that does not change product intent does not require a Northstar edit. Adding a table, vendor, universe, or page does.

Keep vendor payloads out of hot tables. Polymarket `raw` JSONB is the exception.

| Group | Tables | Purpose |
|-------|--------|---------|
| Identity | `instrument`, `universe`, `universe_member` | Tickers; `tape` / `valuation` / `watchlist` |
| Market | `bar_daily`, `quote_latest`, `bar_intraday` | Daily history, delayed last, 5m for tape ∪ watchlist only |
| Macro | `macro_series`, `macro_observation`, `odds_snapshot` | FRED prints; Polymarket implied yes |
| Fundamentals | `metric_ttm` | Point-in-time TTM from SEC companyfacts (no `filing` / `financial_fact` tables) |
| Derived | `valuation_daily`, `rrg_point`, `return_stats`, `opportunity_score` | Python → Postgres; the writer never computes these |
| News / calendar | `news_item`, `event_item` | RSS headlines; YAML catalysts (FOMC/CPI/PCE/NFP/GDP/JOLTS/central banks) + Finnhub earnings |
| Agent | `evidence_pack`, `outlook_report`, `opportunity_memo`, `job_run` | Pack JSONB, briefs, memos, run log |

---

## 9. Analytics

All of this is Python → Postgres. The writer never computes a multiple. Weights and windows live in the named modules.

**Risk-On (−1…+1):** z-score blend of inverse VIX, HYG/LQD, RSP/SPY, 2s10s (not inverted), cyclicals vs defensives. `analytics/risk_on.py`. Polymarket odds are **displayed**, not mixed into the score.

**RRG:** JdK RS-Ratio / RS-Momentum vs SPY. `analytics/rrg.py`. Quadrants Leading / Weakening / Lagging / Improving.

**Valuation:** point-in-time TTM EBITDA; EV = market cap + net debt; percentile vs that name’s own 5y distribution; 1y decomposition ≈ EBITDA growth × multiple change. `analytics/valuation.py`.

**Opportunities — quant first, LLM second**

```text
valuation universe → data-quality filters → sleeve scores → rank → writer on top 15–25
```

Sleeves in `analytics/scores.py`: Cheap 0.30, Quality 0.25, Change 0.20, Setup 0.15, Insider 0.10, minus Risk. Value trap = cheap + falling revenue/margins or distressed leverage. Insider is a **neutral 0.5** until Form 4 exists (it does not).

**Correlation / lead-lag:** 63-session corr on sector ETFs; lags −5…+5. `analytics/corr.py`. Default finding is usually same-day — still show it so the brief cannot invent leadership.

**Macro pack:** Python turns stored FRED history into writer-facing rows (bp changes, CPI/PCE YoY/MoM, payrolls change, named facts such as 2s10s and funds-vs-2Y). `analytics/macro_pack.py`. The writer never computes these.

---

## 10. AI layer

Unattended local = `cron` / `launchd` → Python job → Anthropic or Gemini (official SDKs). Template fallback when the API is down. No in-process scheduler. Ollama can wait.

**Evidence pack** (Python, stored JSONB) includes index/sector returns, a precomputed macro snapshot (levels, bp/YoY deltas, `lag_days`, named facts), a `judgment` object (takeaways, tensions, watch, invalidation), Risk-On, RRG, labeled Polymarket odds, stored headlines (capped per bucket), near vs later events, watchlist outliers, top opportunity rows, and a `sources[]` freshness table. `agent/pack.py`.

**Generation rules**

- Temperature low; structured JSON out: `{headline, abstract, conclusions, expect, macro_md, market_md, near_term_md}`
- System prompt: *only narrate pack fields; prefer judgment; if a field is missing, say unavailable; not a trading signal; use pack YoY/bp, never raw CPI/PCE indexes as percents*
- Post-check: every ticker and every `%` / yield in the output must appear in the pack; CPI YoY and weekly claims must be covered when present — otherwise fail the job and keep yesterday’s report (`agent/citations.py`)
- Prompt version stored on the row
- Opportunities: one memo schema `{why_scored, what_10q_changed, invalidation, caveats}` per top name

**Do not** give the model tools to fetch live prices. Do not wrap LangChain. Call `anthropic` / `google-genai`, not raw HTTP.

---

## 11. API

Screen-shaped. Every payload includes `as_of` and stale flags. Shapes in `api/schemas.py`.

```text
GET /live
GET /outlook?date=
GET /dynamics
GET /valuation?q=&industry=&sort=&min_rev=
GET /opportunities?sort=&as_of=
GET /watchlist
POST /watchlist  DELETE /watchlist/{ticker}
GET /search?q=
GET /health
```

---

## 12. As-built gaps

These were in the original v1 sketch and are **not** implemented. Do not add them unless this file is updated first.

- No Form 4 ingest; opportunity `insider` sleeve is stubbed at 0.5
- No Alpaca quote adapter
- No `filing` / `financial_fact` / `raw_payload` tables
- No in-process scheduler
- Pi host is allowed later (same compose); not a current task

---

## 13. Engineering standards

- One adapter per vendor; canonical Pydantic in, SQL out
- Idempotent upserts; jobs safe to re-run
- No vendor I/O in request handlers except watchlist “add ticker”
- Log `job_run` always
- Types: `NUMERIC` for ranks; `float` only inside numpy then cast back
- Tests: adapter fixtures, upsert uniqueness, Risk-On bounds, pack citation checker
- UI: dark, green/red only for signed changes, density over decoration
- Comments only when the finance formula is non-obvious

---

## 14. What “good” looks like

A weekday morning you open Outlook and see three sections whose sources table matches Postgres. CPI/PCE are YoY/MoM with print dates, not index levels. 10Y, 2s10s, breakevens, real yields, and funds-vs-2Y are pack facts. Live 10Y and sector tape agree with Yahoo delayed. Dynamics does not claim a leader that lead-lag says is same-day. Valuation percentiles match a spot-check of EV/EBITDA vs history. Opportunities #1 is cheap-or-improving **and** not a collapsing-margin trap. Watchlist charts are TradingView. Nothing required a web search by the model.
