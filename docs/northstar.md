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
| Decision-layer tracker | [decision_layer_plan.md](decision_layer_plan.md) |
| Coding-agent map | [AGENTS.md](../AGENTS.md) |

Column lists, job flags, and formulas live in code (`store/models.py`, `jobs/`, `analytics/`). Do not copy them here.

---

## 1. Goal

Give a single operator a dense, honest view of US markets, then a **decision layer** on stored evidence:

- What macro and sectors are doing (**Live**, **Dynamics**)
- What is cheap vs history (**Valuation**): EV/EBITDA vs own 5y, FCF yield, net debt / EBITDA
- What is worth reading today (**Opportunities**): the same named desk metrics, ranked; trap flagged
- Names you track (**Watchlist**)
- A weekday morning **Outlook**: a pack-grounded structured brief (TL;DR → what happened → positioning → drivers → watch today → deep dives on macro / market / policy → invalidation → calendar; see §10.1) covering the US macro spine, what the tape and market-implied odds are pricing, and what is on the calendar in the next sessions
- Fiscal-year **facts** on the valuation universe (`metric_fy`: revenue, earnings, CFO, assets, debt, equity) for growth, accrual, and gems screens. Not computed by the writer
- Later (not this phase): a sized **Book**, a **Gems** universe, three-zone recommendation cards, and a constrained rebalance **plan**. Delayed data; **no orders**. Snapshot numbers are packed Python, not LLM. Postgres holds derived screens; Redis is not in the stack.

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
- Microcap “venture” names without usable XBRL. A **Gems** universe ($300M–$2B market cap, revenue floor in `config/universes.yaml`) is contracted; membership is not built yet
- Redis, Kafka, TimescaleDB, pgvector — not until a measured need. Derived Postgres tables (`quant_score`, later `portfolio_snapshot` / `portfolio_plan`) are the cache
- GraphQL; FMP / Polygon as extra market vendors (Yahoo + SEC cover prices and fundamentals)
- A full XBRL `financial_fact` warehouse or raw EDGAR HTML in hot tables
- LLM-owned weights, entries, targets, or stops. Python fills numeric snapshots; the writer narrates the pack
- Piotroski F-Score or Altman Z as a screen, badge, rank input, or pack field. `metric_fy` stays; F/Z are not product
- LLM “moat” scores or fit-percentage gauges
- P/E or P/B until those facts are stored (this universe is EV/EBITDA + FCF yield). Interest coverage is **in scope** once `InterestExpense` is stored (2026-10-31, see decision_layer_plan Phase 1.6)
- In-process job scheduler (APScheduler). Unattended runs are `cron` / `launchd` calling CLIs when you want them; until then, operators run `make` / `python -m jobs…`

Do not implement a non-goal because it appeared in an older plan. Change this section first.

---

## 3. Pages

| Tab | Job |
|-----|-----|
| **Live** | The read (stored Outlook `headline` / `live_md` / `expect`), regime & conditions band (growth/inflation/policy/volatility from `regime_snapshot`, Risk-On score, net liquidity), regime header (index, breadth, vol, duration, dollar, credit), global markets (`intl_section`), same-day Treasury yields (`yields_section`, bp moves), breakpoints (anomalies), outlier/co-move chips, Risk-On factors, today and the last two sessions’ catalysts, watchlist outliers, sector tape, Polymarket odds, existing FRED drill-down chart |
| **Outlook** | Structured brief (§10.1 sections; legacy macro / market / near-term as fallback), numeric snapshot from the pack, news tape, near calendar, **sources freshness table** |
| **Dynamics** | RRG, indexed relative performance, sector table, correlation, lead-lag |
| **Valuation** | EV/EBITDA vs own 5y, FCF yield, net debt / EBITDA, growth × re-rating |
| **Opportunities** | Named desk metrics + rank + trap; memos on top names (gems **inside** the $1B+ universe until universe D ships). Insider column omitted until Form 4 |
| **Watchlist** | User tickers, quote cards, TradingView widget |
| **Ticker** (`/t/[ticker]`) | One name in depth: FY + quarterly TTM history, valuation vs own history, dilution (share count YoY), technicals (SMAs, drawdown, RSI, vol), relative strength vs SPY and sector, risk (vol, beta, max drawdown), next earnings, news |
| **Compare** | 2–6 tickers side by side: desk metrics, solvency, risk, 1y rebased performance, pairwise correlation, rank. Side by side only — swapping a holding is Book Phase 3.5 |
| **Book** | Sized holdings + cash + risk snapshot + rebalance plan — **not shipped** |
| **Gems** | Small/mid screen ($300M–$2B cap) — **not shipped** |

**Honest constraint:** $1B+ TTM revenue is mid/large cap. “Early gems” here means *mispriced or improving quality names with full SEC history*, not seed-stage. The on-screen language is **multiple, yield, growth, leverage, cash conversion** — not F-score, Z-score, or sleeve unit-ranks as the primary read. Recommendation cards (later) are three zones: header, desk snapshot, book impact if holdings exist. Explain is the ratios and their as-of dates. Not shipped.

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
| Daily OHLCV, sector ETFs, proxy levers (gold = GLD), same-day Treasury yield indices (^IRX/^FVX/^TNX/^TYX) and ICE dollar index (DXY = `DX-Y.NYB`) | Yahoo via `yfinance` behind `YahooClient` | 16:30 ET |
| Quote tape (delayed) | Same yfinance session | 60s in session when you re-run |
| Pre/post 5m gaps | Yahoo 5m | ~07:30 ET, **tape + watchlist only** |
| Yields, VIX, CPI/PCE (as indexes; pack computes YoY/MoM), OAS, DXY (spine), WTI/Brent/copper, real yield, breakevens, payrolls, claims, durable goods, debt/GDP, ECB/BOJ/PBOC policy, dollar crosses (EUR/JPY/GBP/MXN/BRL/CNY), lag-stamped foreign 10Ys | FRED (`config/fred_series.yaml`) | 06:00 ET |
| Fed / inflation / recession / geo odds | Polymarket Gamma API (`config/polymarket_slugs.yaml` slots + match rules; ingest resolves the current slug) | 15–60 min in session |
| Headlines | Google News RSS (`config/news_queries.yaml`; short newsroom-style queries, every request carries `when:{freshness_days}d`), title + link only | 30 min |
| Market wire + watchlist company news, with vendor summaries | Finnhub free REST (`/news?category=general`, `/company-news` per watchlist symbol, ≤5 per name, 2-day window); summary stored only when it is not a copy of the headline; no article fetching | 30–60 min in session, ~07:30 ET |
| FOMC statements, minutes, Chair speeches, testimony | Fed Board RSS (`press_monetary`, `speeches`, `testimony`) via `ingest/fed_rss`, plus the official `www.federalreserve.gov` article each recent item links to when the RSS text is only a title or venue line (capped body text, ≤2500 chars, 14-day lookback; no crawling, no other hosts) | 30–60 min in session |
| Earnings calendar + EPS/rev est. | Finnhub free | 07:00 ET |
| FOMC, CPI, PCE, NFP, GDP, JOLTS, Chair/Jackson Hole speeches, FOMC minutes, Beige Book, ISM, Treasury refunding, ECB/BoE/BoJ, elections | curated `config/catalysts.yaml` | hand, yearly |
| TTM metrics + valuation membership | SEC EDGAR companyfacts (bulk zip, then incremental) | nightly / monthly |
| Fiscal-year snapshots (growth, accrual, gems inputs) | Same companyfacts zip; curated columns only | with `ingest_sec` |
| Charts | TradingView widget | client-side, no ingest |

**Contracted, not ingested yet:** SEC `submissions` JSON, official Form 4 XML, official 10-K/10-Q HTML for Item 1A and Item 7 excerpts only. Same `SEC_USER_AGENT` and rate limit. Not a third-party scrape. Not a `financial_fact` warehouse.

**Polymarket:** store implied probability + liquidity **per catalog slot** (front FOMC, core CPI YoY, recession, …). Gamma slug rotates in place on `odds_snapshot`. UI label: market-implied; thin books are noisy. Do not scrape polymarket.com.

**Yahoo:** ≤2 req/s, `auto_adjust=False`, HTTP 429 fails fast. Timeouts/5xx retry ≤3.

Do not add scraping, unofficial APIs, or non-US listings. Expanding the FRED catalog is not a new vendor. International **listings** stay out, but international **indices** (Nikkei, DAX, FTSE, HSI, CSI 300) and **EM ETFs** (EEM) via Yahoo are permitted for context.

---

## 7. Universes

| Tier | Contents | Stored history |
|------|----------|----------------|
| **A Tape** | US indices/ETFs + Treasury yield indices + international indices (Nikkei, DAX, FTSE, HSI, CSI 300) + EEM in `config/universes.yaml` | daily + quotes + 5m extended |
| **B Valuation / Opportunity** | US NYSE/Nasdaq, TTM revenue ≥ $1B, usable XBRL, Yahoo history | daily bars + SEC TTM + fiscal-year facts + valuation + ratio snapshot / gem flag |
| **C Watchlist** | user-defined | daily + 5m + TV chart |
| **D Gems** | US listings, market cap $300M–$2B, TTM revenue floor in yaml, usable XBRL | **not built**; flags may appear on B via `quant_score.is_gem_candidate` |

Build B from SEC tickers + `companyfacts` (prefer bulk zip once, then incremental). Rebuild membership monthly. Floor: `config/universes.yaml` `valuation.min_revenue_usd`. Gems thresholds live in the same file under `gems`; do not Yahoo-ingest D until a later phase screens SEC-first.

---

## 8. Schema

Table **purpose** lives here. Columns and constraints live in `store/models.py` and `alembic/versions/`. Adding a column that does not change product intent does not require a Northstar edit. Adding a table, vendor, universe, or page does.

Keep vendor payloads out of hot tables. Polymarket `raw` JSONB is the exception.

| Group | Tables | Purpose |
|-------|--------|---------|
| Identity | `instrument`, `universe`, `universe_member` | Tickers; `tape` / `valuation` / `watchlist` (later `gems`). `sector` = approximate GICS from the SEC SIC code (`config/sic_sectors.yaml`), `industry` = SEC `sicDescription` |
| Market | `bar_daily`, `quote_latest`, `bar_intraday` | Daily history, delayed last, 5m for tape ∪ watchlist only |
| Macro | `macro_series`, `macro_observation`, `odds_snapshot`, `regime_snapshot` | FRED prints; Polymarket implied yes keyed by catalog slot; daily growth / inflation / policy / volatility classification from stored FRED |
| Fundamentals | `metric_ttm`, `metric_fy` | Point-in-time TTM and fiscal-year facts from SEC companyfacts (no `financial_fact` warehouse). FY is for growth, accrual, gems — not an on-screen F/Z |
| Derived | `valuation_daily`, `rrg_point`, `return_stats`, `risk_stats`, `opportunity_score`, `quant_score` | Python → Postgres; the writer never computes these. `risk_stats` is per-name vol / downside vol / beta / drawdown from adjusted closes. `quant_score` holds a gem flag and ratio snapshot; legacy `f_score` / `z_score` columns stay NULL |
| News / calendar | `news_item`, `event_item`, `policy_item` | RSS headlines plus Finnhub `wire` / `company` rows (`summary` nullable, `query` = ticker for company); YAML catalysts (FOMC/CPI/PCE/NFP/GDP/JOLTS/speeches/minutes/Beige Book/ISM/Treasury/central banks) + Finnhub earnings; official Fed Board RSS (speech/statement/minutes/testimony excerpts) |
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

Sleeves in `analytics/scores.py` are a **sort key**, not the grid: Cheap 0.30 (1 − own 5y EV/EBITDA percentile), Quality 0.25 (FCF margin and FCF yield), Change 0.20 (1y EBITDA growth), Setup 0.15 (63-session return), minus Risk (trap + net-debt/EBITDA vs 8x). Value trap = cheap + falling EBITDA. **Insider is omitted from the UI** until Form 4; do not display the stub 0.5. Accrual (CFO > net income from `metric_fy`) is a yes/no/unavailable **badge**, not a sleeve.

**Desk metrics (the product language).** Every recommendation row is multiples, yields, growth, leverage, cash conversion:

- EV/EBITDA and own 5y percentile (`valuation_daily`)
- FCF yield (TTM FCF / EV) and FCF margin
- EBITDA YoY; revenue YoY from FY when present
- Net debt / EBITDA
- Trap badge

Do not show sleeve unit-ranks (0–1) as the primary columns once those fields are on the API. Do not add P/E or P/B until those facts exist. Interest coverage ships with stored `InterestExpense`.

**Not product:** Piotroski F-Score and Altman Z. Do not show them, pack them, or feed F into quality. Do not hard-cut F ≥ 7. Nothing computes them: the Piotroski / Altman modules were removed (2026-10-29) and the legacy `quant_score` columns are written NULL. Gem candidate flag uses yaml thresholds (cap band, revenue growth, FCF yield, D/E); fail negative book equity. Insider ownership is not required until Form 4.

**Correlation / lead-lag:** 63-session corr on sector ETFs; lags −5…+5. `analytics/corr.py`. Default finding is usually same-day — still show it so the brief cannot invent leadership.

**Macro pack:** Python turns stored FRED history into writer-facing rows (bp changes, CPI/PCE YoY/MoM, payrolls change, named facts such as 2s10s and funds-vs-2Y). `analytics/macro_pack.py`. The writer never computes these.

**Outliers / co-moves:** trailing z of 1-day changes across a small stored universe (2Y/10Y/30Y yields, VIX, dollar, yen, credit, SMH, IWM, XLK/XLU). Ranked chips plus jointly extreme sets with numbers and an optional writer-only `hint` (including `front_long` for 2s vs 30s). No causal verbs. `analytics/drivers.py`. The writer never computes these z-scores. Pack facts include `dgs2_d1_bp` and `dgs30_d1_bp`.

**Regime classification:** Structured macro environment detection stored in `regime_snapshot` table. Classifies growth (expansion/slowdown/recession/recovery), inflation (accelerating/stable/decelerating), policy (tightening/neutral/easing), and volatility (suppressed/normal/elevated) with confidence scores. `analytics/regime_detect.py`. Job: `jobs/compute_regime.py`. Run after `ingest_fred` and before `build_pack`. Surfaced on Live (latest snapshot) and packed for Outlook.

**Liquidity conditions:** Net liquidity = Fed Balance Sheet (WALCL) - (Reverse Repo + TGA). Rising net liquidity historically correlates with risk asset strength. WoW change flags material shifts. `analytics/macro_pack.compute_net_liquidity`. Packed in `evidence_pack.liquidity` and computed read-time for `GET /live`.

**Anomaly detection:** Identifies unusual cross-asset behavior — correlation breakdowns (SPY/10Y moving same direction vs historical negative correlation), z-score extremes (>2σ moves), breadth divergences (SPY up while RSP/IWM down). `analytics/anomaly_detect.py`. Packed in `evidence_pack.anomalies` with severity scores (top 3 by severity for writer context) and surfaced read-time on Live as "Breakpoints".

---

## 10. AI layer

Unattended local = `cron` / `launchd` → Python job → Anthropic or Gemini (official SDKs). Template fallback when the API is down. No in-process scheduler. Ollama can wait.

**Evidence pack** (Python, stored JSONB) includes index/sector returns, a precomputed macro snapshot (levels, bp/YoY deltas, `lag_days`, named facts), a `judgment` object (takeaways, tensions, watch, invalidation, outliers, co_moves, `policy_comms`), Risk-On, RRG, labeled Polymarket odds, stored headlines selected by one read-time rule set (`config/news_sources.yaml`, `analytics/news_rank.py`, shared with `GET /outlook`): drop blocked publishers and junk title patterns, drop duplicate stories, rank by publisher tier then recency, then cap per bucket (3 over 48h, 6 for the Finnhub wire; bucket = category, or category + ticker for company news); rows keep the vendor `summary` when present. Nothing is filtered at ingest, so rule changes apply to stored rows. last-72h official Fed `policy_items[]`, near vs later events, watchlist outliers, top opportunity rows, `regime`, `liquidity`, `anomalies`, same-day `yields_live` (Yahoo levels + bp), `extended_hours` (pre/post-market gaps from stored 5m bars vs the last daily close, outside the cash session only), `session.phase` (pre_open / intraday / after_close / closed, ET clock at build time), and a `sources[]` freshness table. `agent/pack.py`; the writer receives the compact `writer_pack` slice of it (headlines spread one per bucket first, up to 32, Finnhub wire three per round). Writer may quote packed policy excerpts only.

**Generation rules**

- Temperature low; structured JSON out = the §10.1 sections **plus** the backward-compat fields `{headline, abstract, conclusions, expect, live_md}` (Live reads `headline` / `live_md` / `expect`). `macro_md` / `market_md` / `near_term_md` are legacy and filled from the deep sections. Field list: `agent/brief.py`
- `live_md` is the short Live slice (2–4 sentences). Outlook keeps the long sections. No second writer job and no Live-time LLM.
- System prompt: *only narrate pack fields; prefer judgment (including co_moves / outliers / watch / policy_comms) and policy_items; if a field is missing, say unavailable; not a trading signal; use pack YoY/bp, never raw CPI/PCE indexes as percents; do not invent a hike date or a mechanism those fields do not support*
- Post-check: every ticker and every `%` / yield in the output must appear in the pack; CPI YoY and weekly claims must be covered when present; §10.1 fields must pass `validate_brief_fields` (length, sequence, levels, scenario outcomes) — otherwise fail the job and keep yesterday’s report (`agent/citations.py`)
- Prompt version stored on the row
- Opportunities: one memo schema `{why_scored, what_10q_changed, invalidation, caveats}` per top name, packed from desk metrics. The UI shows the stored memo; a browser-built desk summary is only the fallback when no memo exists. `what_10q_changed` is `unavailable` until filing excerpts exist; do not ask the model to invent a 10-Q change
- Later recommendation cards: three zones (header, desk snapshot, book impact if holdings exist). Python owns the snapshot numbers. No entry/target/stop on the card. No F-score or Z in the pack. Citation check still gates prose.

**Do not** give the model tools to fetch live prices. Do not wrap LangChain. Call `anthropic` / `google-genai`, not raw HTTP.

### 10.1 Outlook narrative structure

The Outlook brief must provide structured, actionable analysis — not merely event narration. The following sections are required in the JSON output and markdown rendering:

**Core sections (required):**

- `tldr`: 1-2 sentence synthesis of regime + primary catalyst + market direction. Not a summary, a takeaway.
- `what_happened`: 3-5 sentences explaining yesterday's cross-asset move as a mechanism. Which asset led? What followed? Use packed `co_moves` and `outliers` to identify rotation/deleveraging/carry stories. Numbers are evidence for causality.
- `current_positioning`: 3-4 sentences on where key spreads (2s10s, HY-IG, DXY, breakevens, fed_vs_2y_bp, gold, EM FX if present) sit relative to recent ranges. Use `judgment.tensions` to frame fragility. Include specific levels and cross-asset signals (e.g., gold rallying with equities = fiscal hedge, not flight-to-quality).
- `drivers`: 3-5 sentences distinguishing scheduled events (`watch.role=printed`) from ongoing forces (odds shifts, geopolitical premium, liquidity conditions, curve dynamics). If the move preceded the catalyst, say so.

**Scenario planning (required):**

- `watch_today`: Array of structured scenarios for each `watch.role=next` catalyst. Each includes `{catalyst, outcome_bullish, outcome_bearish, threshold}`. Branching logic: if CPI > consensus, what happens to 2Y vs 10Y? To equities? Use `judgment.invalidation` to bound scenarios.
- `invalidation`: Explicit triggers that would break the current read. Include thresholds (e.g., "10Y breaking 4.80% sustained" or "payrolls < 150k with rising claims"). Use packed `judgment.invalidation` + extend with market-structure triggers.

**Deep sections (required, 4-6 sentences each):**

- `macro_deep`: Curve (2s10s, real_10y, fed_vs_2y_bp), inflation gap (breakeven_10y vs CPI/PCE YoY), employment (PAYEMS print_change, UNRATE, ICSA weekly), FX & commodities (DXY direction, gold vs real yields, oil for inflation/geopolitics, copper for industrial demand), fiscal (GFDEGDQ188S), global context (ECB/BOJ/PBOC rates, major international indices if diverging). Narrate regime, not just levels.
- `market_deep`: Risk-On score + factors, HY vs IG (OAS), odds top_outcome with implied_yes, cross-asset positioning (DXY transmission to EM/commodities/carry), RRG quadrant shifts, international divergence (EEM, Nikkei, DAX, HSI vs SPY). Contrast front-end (DGS2/Fed odds) with long-end (DGS10/DGS30/breakevens). Explain what the market is pricing.
- `policy_deep`: Synthesize `policy_comms` (stance, speaker, tensions) and `policy_items` excerpts. What is the Fed/ECB/BOJ watching? Where is the next inflection? Use packed odds to quantify market expectations.
- `geopolitical_deep`: (optional, only if relevant) Energy infrastructure (oil supply/demand, refining capacity, natural gas/LNG), trade policy (active tariff disputes, supply chain shifts), geopolitical risk premium (conflicts affecting shipping/commodities/safe havens). Systematic approach: use news items, Fed/Treasury commentary, cross-asset correlations. Distinguished structural vs transient risk. Omit if not market-relevant.

**Meta (required for backward compat):**

- `conclusions`: Three bullets (Printed / Tape / Next) for audit trail. Keep existing logic.
- `calendar`: Structured array with `{date, time, event, consensus, prior, source}` for next sessions' tests.

**Rendering principles:**

1. Synthesis over narration: explain mechanisms, not just report numbers
2. Cross-asset connections: how does policy affect markets affect economy?
3. Forward scenarios: give the reader branching outcomes with explicit thresholds
4. Hierarchical structure: TL;DR → What Happened → Drivers → Watch Today → Deep Dive → Invalidation
5. Actionability: every section answers "so what?" for a market professional

**Citation rules remain:** every ticker, `%`, and yield must appear in the pack. New fields (`tldr`, `what_happened`, `current_positioning`, `drivers`, `watch_today`) must pass the same citation checks as existing fields.

---

## 11. API

Screen-shaped. Every payload includes `as_of` and stale flags. Shapes in `api/schemas.py`.

```text
GET /live
GET /outlook?date=
GET /dynamics
GET /valuation?q=&industry=&sort=&min_rev=
GET /opportunities?sort=&as_of=
GET /ticker/{ticker}
GET /compare?tickers=A,B,...
GET /watchlist
POST /watchlist  DELETE /watchlist/{ticker}
GET /search?q=
GET /health
```

`GET /valuation` and `GET /opportunities` include named desk-metric fields (`fcf_yield`, `nd_ebitda`, `accrual`). Book CRUD, `GET /recommendations`, `GET /gems`, and `GET /portfolio/plan` are contracted; do not add them until that phase. No GraphQL.

---

## 12. As-built gaps

These are contracted or sketched and are **not** implemented. Do not add them unless this file is updated first (pull the item out of this list into the current phase).

**Decision layer (next phases)**

- No Form 4 ingest; omit the insider column (code may still stub 0.5 — do not display it)
- No `filing_index` / `filing_excerpt` (Item 1A / Item 7). Still no `financial_fact` / `raw_payload` warehouse. Memo 10-Q field stays `unavailable`
- No Book (`portfolio` / holdings), no portfolio risk snapshot, no constrained optimizer / rebalance plan
- No Gems universe membership or Yahoo gems ingest (`is_gem_candidate` on `quant_score` is a flag only)
- No recommendation rows or three-zone cards
- No 13F institutional accumulation
- Piotroski / Altman are **out of product** — do not pull them back in as UI, rank, or pack fields

**Still out**

- No Alpaca quote adapter
- No in-process scheduler
- Pi host is allowed later (same compose); not a current task
- Redis / GraphQL / extra fundamental vendors

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

A weekday morning you open Outlook and see the structured brief (TL;DR first) whose sources table matches Postgres. CPI/PCE are YoY/MoM with print dates, not index levels. 10Y, 2s10s, breakevens, real yields, and funds-vs-2Y are pack facts. Live 10Y and sector tape agree with Yahoo delayed. Dynamics does not claim a leader that lead-lag says is same-day. Valuation percentiles match a spot-check of EV/EBITDA vs history; FCF yield and ND/EBITDA on that row match TTM ÷ EV. Opportunities #1 is cheap-or-improving **and** not a collapsing-EBITDA trap, readable from EV/EBITDA, 5y %ile, FCF yield, ND/EBITDA, and EBITDA 1y — no F-score or Z on the row. Watchlist charts are TradingView. Nothing required a web search by the model.
