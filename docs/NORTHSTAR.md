# Market Agent — Northstar

Personal US research terminal: delayed data, no trading. Fetch → store in Postgres → compute → serve a dashboard → write a daily brief and opportunity list from **stored evidence only**.

**Product name (UI):** Sector Panel
**Language:** English
**Charts:** TradingView embed
**Host:** Mac now; Raspberry Pi (or similar) later via the same Docker Compose stack

This file is the implementation contract. Day-by-day work must not contradict it. If product intent changes, update this document first.

---

## 1. Goal

Give a single operator a dense, honest view of US markets:

- What macro and sectors are doing (**Live**, **Dynamics**)
- What is cheap vs history (**Valuation**)
- What is worth reading today (**Opportunities**)
- Names you track (**Watchlist**)
- A weekday morning brief that cites only data already in Postgres (**Outlook**)

Every number on screen comes from Postgres. Vendors are never called from the UI or from the LLM.

---

## 2. Non-goals (v1)

- Trading, orders, paper fills
- Real-time / WebSocket quotes
- X / Twitter
- Non-US listings as first-class (no `.L`, `.T`, CEDEARs)
- Scraping Finviz, Investing.com, TradingView unofficial APIs, Google Finance RPC
- Letting Claude search the web or call Yahoo/SEC at generation time
- Microcap “venture” names (revenue < $1B) — later as a second universe
- Redis, Kafka, TimescaleDB, pgvector — not until a measured need

---

## 3. Pages

| Tab | Job |
|-----|-----|
| **Live** | Indices, sector tape, macro levers, Polymarket odds, Risk-On pill, drill-down chart |
| **Outlook** | Daily AI brief, news tape, catalysts, **sources freshness table** |
| **Dynamics** | RRG, indexed relative performance, sector table, correlation, lead-lag |
| **Valuation** | EV/EBITDA vs own 5y range, industry, growth × re-rating |
| **Opportunities** | Quant scores + Claude memos on top names (gems **inside** the $1B+ universe) |
| **Watchlist** | User tickers, quote cards, TradingView widget |

**Honest constraint:** $1B+ TTM revenue is mid/large cap. “Early gems” here means *mispriced or improving quality names with full SEC history*, not seed-stage companies.

---

## 4. Architecture

```text
ingest adapters  →  jobs (cron)  →  PostgreSQL  →  FastAPI  →  Next.js
                         │
                         ├→ analytics tables (same DB)
                         └→ evidence_pack JSONB → agent (Outlook + top-N memos)
```

| Layer | Choice | Why |
|-------|--------|-----|
| DB | **PostgreSQL 16** in Docker Compose + named volume | Concurrent API + jobs, JSONB, proper types, Pi-portable |
| Migrations | Alembic | Schema is the contract |
| ORM | SQLAlchemy 2.0 **sync** + Pydantic schemas | Jobs and API share models; skip async SQLAlchemy in v1 |
| API | FastAPI, `def` routes (threadpool) | Simple; one connection style |
| Jobs | Python + APScheduler or `launchd`/`cron` calling CLI | Timezone `America/New_York` |
| HTTP | `httpx` + token bucket; Yahoo via `yfinance` | FRED/SEC use httpx; Yahoo ≤2 req/s (`curl_cffi` TLS) |
| UI | Next.js + Tailwind + shadcn | Dense dark terminal |
| Charts | TradingView embed; Recharts/SVG for sparklines, RRG, heatmap | Don’t rebuild a charting platform |
| LLM | Official Anthropic or Gemini SDK; template fallback | Writer only, pack-grounded |

**Postgres is the system of record.** No SQLite. Optional Parquet export can come later for notebooks; do not dual-write in v1. `yfinance` may keep a small local timezone cache; that is not market data.

---

## 5. Postgres + Docker

One service, one volume, one database. No PgAdmin, no Redis, no extra containers until something hurts.

See `docker-compose.yml` in the repo root.

**Local rules**

- App reads `DATABASE_URL` (default `postgresql://market:market@localhost:5433/market_agent`; container still listens on 5432 internally)
- Jobs and API share the URL; **jobs are the only writers** of market data
- API is read-only except watchlist CRUD and “refresh now” triggers
- `ON CONFLICT` upserts everywhere (idempotent jobs)
- `timestamptz` always; store timestamps in UTC, display ET in the UI
- Money, yields, multiples: `NUMERIC` — never `float` for values you compare or rank
- JSONB for evidence packs, news extras, Polymarket raw, option chains
- `bigserial` PKs
- SQLAlchemy pool_size 5, max_overflow 5 — enough for one user

**Why not Timescale yet:** ~900 names × 10y × 252 days ≈ 2.3M daily bars. Vanilla Postgres is fine. Do not add 1-minute bars for the full universe.

**Pi later:** same compose. Lower `shared_buffers` if RAM is tight. Backup is `pg_dump`. Prefer Pi 5 / 8 GB + SSD.

**Dev workflow**

```text
docker compose up -d db
alembic upgrade head
python -m jobs.seed_tape
uvicorn api.main:app --reload
# web: npm run dev
```

---

## 6. Source stack (frozen for v1)

| Input | Vendor | Cadence |
|-------|--------|---------|
| Daily OHLCV, sector ETFs, proxy levers | Yahoo via `yfinance` behind `YahooClient` (canonical models → Postgres) | 16:30 ET |
| Quote tape (delayed) | Same yfinance session (chart metadata); Alpaca IEX as fallback | 60s in session |
| Pre/post 5m gaps | Yahoo 5m | ~07:30 ET, **tape + watchlist only** |
| Yields, VIX, CPI/PCE, OAS, DXY, WTI, real yield, breakevens | FRED (~13 series) | 06:00 ET |
| Fed / inflation / recession / geo odds | Polymarket Gamma API | 15–60 min in session |
| Headlines | Google News RSS (query catalog) | 30 min |
| Earnings calendar + EPS/rev est. | Finnhub free | 07:00 ET |
| FOMC, CPI dates, elections | curated `config/catalysts.yaml` | hand, yearly |
| Statements, TTM, Form 4 | SEC EDGAR (bulk facts + submissions) | nightly |
| Charts | TradingView widget | client-side, no ingest |

**FRED v1:** see `config/fred_series.yaml`.

**ETF proxies:** see `config/universes.yaml` tape list.

**Polymarket:** curated slugs in `config/polymarket_slugs.yaml`. Store implied probability + liquidity. UI label: market-implied; thin books are noisy.

**Alpaca:** optional quote spare tire, not a second history.

**gauss314/skills:** documentation and script patterns for adapters. Not the runtime ingestion layer.

---

## 7. Universes

| Tier | Contents | Stored history |
|------|----------|----------------|
| **A Tape** | ~25 indices/ETFs | daily + quotes + 5m extended |
| **B Valuation / Opportunity** | US NYSE/Nasdaq, TTM revenue ≥ $1B, usable XBRL, Yahoo history | daily bars + SEC TTM + valuation |
| **C Watchlist** | user-defined | daily + 5m + TV chart |

Build B from `company_tickers_exchange.json` + SEC `companyfacts` (prefer bulk zip once, then incremental). Rebuild membership monthly.

---

## 8. Canonical schema (Postgres)

Keep vendor payloads out of hot tables. Optional `raw_payload` with cleanup can come after Day 1 if debugging needs it.

**Identity**

- `instrument(id, ticker UNIQUE, name, exchange, asset_class, sector, industry, cik, figi, is_active)`
- `universe(id, name UNIQUE)` — `tape`, `valuation`, `watchlist`
- `universe_member(universe_id, instrument_id, PRIMARY KEY)`

**Market**

- `bar_daily(instrument_id, date, o, h, l, c, adj_c, volume, source, UNIQUE(instrument_id, date))`
- `quote_latest(instrument_id PK, price, change_pct, volume, market_state, as_of, source)`
- `bar_intraday(instrument_id, ts, interval, o, h, l, c, volume, UNIQUE(...))` — tape/watchlist only

**Macro**

- `macro_series(id text PK, name, unit, source, fred_id nullable)`
- `macro_observation(series_id, date, value NUMERIC, UNIQUE(series_id, date))`
- `odds_snapshot(slug, as_of, question, implied_yes NUMERIC, liquidity, raw jsonb)`

**Fundamentals**

- `filing(cik, form, filed_at, period_end, accession UNIQUE)`
- `financial_fact(cik, concept, taxonomy, period_end, form, value NUMERIC, unit, accession)`
- `metric_ttm(instrument_id, as_of, revenue, ebitda, fcf, net_debt, shares, UNIQUE(instrument_id, as_of))`
- `insider_form4(...)` — after core valuation works

**Derived**

- `valuation_daily(...)`
- `rrg_point(...)`
- `return_stats(...)`
- `opportunity_score(...)`

**News / calendar**

- `news_item(...)`
- `event_item(...)`

**Agent**

- `evidence_pack(id, as_of, pack jsonb, hash, created_at)`
- `outlook_report(date UNIQUE, model, prompt_version, body_md, body_json jsonb, pack_id, status)`
- `opportunity_memo(...)`
- `job_run(id, job_name, started_at, finished_at, status, rows_written, error, meta jsonb)`

---

## 9. Analytics (finance)

**Risk-On (−1…+1):** z-score blend of inverse VIX, HYG/LQD, RSP/SPY, 2s10s (not inverted), cyclicals vs defensives. Document weights in `analytics/risk_on.py`. Polymarket odds are **displayed**, not mixed into v1 score.

**RRG:** JdK RS-Ratio / RS-Momentum vs SPY, ~12-week window, 3–8 week trails, quadrants Leading / Weakening / Lagging / Improving.

**Valuation:** point-in-time TTM EBITDA from last four 10-Qs; EV = market cap + net debt; percentile vs that name’s own 5y distribution; 1y decomposition ≈ EBITDA growth × multiple change.

**Opportunities — quant first, LLM second**

```text
~900 → data-quality filters → sleeve scores → rank → Claude on top 15–25
```

Sleeves: Cheap 0.30, Quality 0.25, Change 0.20, Setup 0.15, Insider 0.10, minus Risk.
Value trap = cheap + falling revenue/margins or distressed Altman-like score.

**Correlation / lead-lag:** 63-day corr on sector ETFs; cross-corr lags −5…+5. Default finding is usually same-day — still show it so the brief cannot invent leadership.

**All of this is Python → Postgres.** The agent never computes a multiple.

---

## 10. AI layer (Outlook + Opportunities)

**Cursor cron is not the production path.** Unattended local = `cron`/`launchd` → Python job → Anthropic or Gemini (official SDKs). Template fallback when the API is down. Ollama can wait.

**Evidence pack** (built in Python, stored JSONB) includes index/sector returns, macro snapshot, Risk-On, RRG, Polymarket odds, stored headlines, upcoming events, watchlist outliers, top opportunity rows, and a `sources[]` freshness table.

**Generation rules**

- Temperature low; structured JSON out
- System prompt: *only narrate pack fields; if a field is missing, say unavailable; not a trading signal*
- Post-check: every ticker and every `%` / yield in the output must appear in the pack — otherwise fail the job and keep yesterday’s report
- Prompt version stored on the row
- Opportunities: one memo schema `{why_scored, what_10q_changed, invalidation, caveats}` per top name

**Do not** give the model tools to fetch live prices in v1. Do not wrap LangChain. Call `anthropic` / `google-genai`, not raw HTTP.

---

## 11. API (screen-shaped)

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

Every payload includes `as_of` and stale flags.

---

## 12. Repo layout

```text
market_agent/
  docker-compose.yml
  alembic/
  config/          # yaml catalogs, .env.example
  ingest/          # yahoo, fred, sec, polymarket, news_rss, finnhub
  store/           # engine, models, repos
  analytics/       # risk_on, rrg, valuation, corr, scores
  jobs/            # one module per schedule entry, CLI
  agent/           # pack.py, outlook.py, memos.py, prompts/
  api/             # FastAPI
  web/             # Next.js
  docs/NORTHSTAR.md
```

Adapters return Pydantic canonical models. Repos upsert. Jobs orchestrate. API never imports `ingest`.

---

## 13. Keys

| Key | Required for |
|-----|----------------|
| `FRED_API_KEY` | macro |
| `FINNHUB_API_KEY` | earnings calendar |
| `ANTHROPIC_API_KEY` | Outlook + memos (Anthropic provider) |
| `GEMINI_API_KEY` | Outlook + memos (Gemini provider; `GOOGLE_API_KEY` alias) |
| `AGENT_PROVIDER` | `anthropic` or `gemini` (empty = auto) |
| `SEC_USER_AGENT` | `MarketAgent you@email.com` |
| `ALPACA_*` | optional quotes |
| `DATABASE_URL` | local compose default |

Never commit secrets. Copy `.env.example` → `.env`.

---

## 14. Day-by-day implementation

Each day has a **definition of done**. Do not start the next day until it passes. Prefer one vertical slice over scaffolding everything empty.

### Day 0 — Config and compose

Docker Compose Postgres + volume, `.env.example`, `config/` yaml catalogs, `.gitignore` for `.env`.

**Done:** `docker compose up -d db` and `psql` connects.

### Day 1 — Skeleton

Alembic, `instrument` / `universe` / `job_run`, SQLAlchemy models, FastAPI `/health`, Next.js chrome (six tabs). Seed tape tickers.

**Done:** UI loads; health shows Postgres ok.

### Day 2 — Yahoo adapter

`yfinance` 1.6 with `curl_cffi` Chrome impersonation, token bucket ≤2 req/s, `bar_daily` + `quote_latest` upserts for tape. UI and LLM never import `yfinance`. `auto_adjust=False`. Sequential requests; fail fast on HTTP 429.

**Done:** SPY and XLK have rows in Postgres.

### Day 3 — Live tape

`GET /live` from DB. Next.js Live header + tape. No vendor calls from the browser.

**Done:** Live looks like a delayed tape after a job run.

### Day 4 — FRED

Adapter + 13 series + `macro_observation`. Live sidebar with last value and 1D change.

**Done:** 10Y yield is a real FRED number with `as_of`.

### Day 5 — Live drill-down

Select a lever → large chart, Δ 1D/1W/1M/1Y, static insight templates. Risk-On v1.

**Done:** clicking 10Y matches the Live screenshot structure.

### Day 6 — Polymarket

Gamma adapter, curated slugs, `odds_snapshot`. Show Fed / inflation / recession on Live.

**Done:** odds update on job without affecting Risk-On.

### Day 7 — Dynamics core

Returns, RRG points, indexed-to-100 series. Dynamics page: scatter + grouped list.

**Done:** quadrants move when you re-run on history.

### Day 8 — Dynamics extras

Relative-performance overlay, US sectors table, 63d correlation heatmap, lead-lag pair control.

**Done:** no new vendors.

### Day 9 — Outlook without LLM

Google News RSS, Finnhub earnings, catalysts yaml, evidence pack, sources table.

**Done:** sources table is true (vendor, as_of, counts).

### Day 10 — Agent Outlook

Weekday job 07:45 ET: pack → structured Anthropic or Gemini → `outlook_report`. Citation check. Fallback: template if API fails.

**Done:** one generated brief uses only pack numbers.

### Day 11–13 — Valuation universe

SEC tickers + companyfacts. Revenue ≥ $1B. `metric_ttm`. Daily bars for those names.

**Done:** membership count is in the 700–1000 band.

### Day 14–15 — Valuation page

`valuation_daily`, %ile vs 5y, filters, growth × re-rating.

**Done:** “N of M with a comparable multiple” is a real query.

### Day 16–17 — Opportunities

Score job, table UI, Claude memos for rank ≤ 20.

**Done:** you can explain the #1 name from SQL without the memo.

### Day 18 — Watchlist

Add/remove, quote cards, sparklines, TradingView embed. Extended-hours 5m for watchlist + indices only.

**Done:** a watchlist name shows TV chart + DB quote.

### Day 19 — Hardening

Retries, `/health` job status, stale badges, backfill CLI, `pg_dump` script, README runbook.

**Done:** killing Yahoo mid-job and re-running does not duplicate bars.

### Day 20 — Pi pass (optional)

Same compose on device; restore dump; run jobs + API; browse UI from the Mac.

**Done:** Outlook job runs without the Mac.

If a day slips, **do not skip ahead to the agent job or SEC bulk**.

---

## 15. Engineering standards

- One adapter per vendor; canonical Pydantic in, SQL out
- Idempotent upserts; jobs safe to re-run
- No vendor I/O in request handlers except watchlist “add ticker”
- Log `job_run` always
- Types: `NUMERIC` for ranks; `float` only inside numpy then cast back
- Tests: adapter fixtures, upsert uniqueness, Risk-On bounds, pack citation checker
- UI: dark, green/red only for signed changes, density over decoration
- Comments only when the finance formula is non-obvious

---

## 16. What “good” looks like

A weekday morning you open Outlook and see a brief whose sources table matches Postgres. Live 10Y and sector tape agree with Yahoo delayed. Dynamics does not claim a leader that lead-lag says is same-day. Valuation percentiles match a spot-check of EV/EBITDA vs history. Opportunities #1 is cheap-or-improving **and** not a collapsing-margin trap. Watchlist charts are TradingView. Nothing required a web search by the model.
