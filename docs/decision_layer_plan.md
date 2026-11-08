# Decision layer — implementation tracker

Living build plan for evolving Sector Panel from a research terminal into a **decision layer** (named desk metrics on ranked names → sized book → pack-grounded cards → optional rebalance plan).

This file is **not** the product contract. If intent, sources, universes, pages, or schema meaning change, update [northstar.md](northstar.md) **first**, then this tracker.

| | Where |
|---|---|
| Contract | [northstar.md](northstar.md) |
| Job → table → API → UI | [system.md](system.md) |
| Operator runbook | [pipelines.md](pipelines.md) |
| Sketch (superseded) | [AI_Stock_Recommendation_Blueprint.md](archive/AI_Stock_Recommendation_Blueprint.md) |
| Coding-agent map | [AGENTS.md](../AGENTS.md) |

**Product rules that stay true**

- Delayed data. No orders, no broker, no WebSocket quotes.
- Jobs write market data. API is read-only except operator input: watchlist, Book holdings / cash, theses.
- Vendors never called from the UI or the writer LLM.
- Postgres is the cache. No Redis, GraphQL, FMP/Polygon, or pgvector unless Northstar says so.
- Python owns scores, weights, and snapshot numbers. The model only narrates a pack.
- On-screen language is **multiple, yield, growth, leverage, cash conversion**. If a number needs a footnote to decode (F-score, Z, sleeve 0.62, fit 92%), it does not ship.
- Accrual is **CFO > net income** as a yes/no/unavailable badge, not a rank input.
- Piotroski F-Score and Altman Z are **not product**. Do not show, pack, or rank on them. `metric_fy` stays as the annual fact table.

---

## Status snapshot

| Phase | Name | Status | Notes |
|---|---|---|---|
| 0 | Contract | **Done** | Desk metrics are the product language; F/Z out of product (2026-09-14) |
| 1 | `metric_fy` + ratio snapshot / gem flag | **Warehouse done** | Branch `feat/desk-metrics-and-review`. F/Z computation removed 2026-10-29. No UI |
| 1.5 | Desk metrics on Valuation + Opportunities | **Done** | Named fields on `GET /valuation` and `GET /opportunities`; grids match. No LLM |
| 1.6 | SEC TTM data quality | **Done** (PR #13) | YTD-differenced quarters, contiguous TTM, aligned periods, debt de-dup, `cfo`/`capex` stored, comparable ≥ 750 sessions |
| 1.7 | Sector + per-name risk | **Done** (PR #14) | SIC → sector from SEC submissions; vol / beta / max DD for the valuation universe; `InterestExpense` |
| 1.8 | Ticker + Compare pages | **Done** (PR #15) | `GET /ticker/{t}`, `GET /compare`; links from every grid; header search |
| 1.9 | Rotation panels | Not started | Cross-asset RRG, sector breadth + median valuation, intra-sector RRG, factor ETFs |
| 1.10 | Peer comps + credit curve | **Done** (PR #17) | Ticker-page peer table and EV/EBITDA vs growth scatter (no new data); FRED rating-bucket OAS / yields, DGS1, Baa–Aaa, NFCI, STLFSI4 |
| 1.11 | Equity-implied credit bucket | **Done** (PR #18) | Merton DD → implied rating bucket on the FRED curve; `config/credit_calibration.yaml` reviewed before ship |
| 1.12 | Options read | **Done** (PR #19) | Yahoo chains (scoped names), ^VIX9D / ^VIX3M / ^VVIX / ^SKEW, Cboe market put/call |
| 1.13 | Kalshi + CFTC | **Done** (PR #20) | S&P / Nasdaq range distribution, Fed + recession beside Polymarket; TFF positioning |
| 1.14 | Short interest + estimate revisions | **Done** (PR #21) | FINRA short interest + days to cover (all stored names); Yahoo EPS revisions (watchlist ∪ top 25). No targets |
| 1.15 | Foreign filers (US-listed ADRs) + bank read | **Done** (branch `feat/foreign-filers`) | Curated 20-F / 6-K filers in USD join B; Yahoo quarters as labeled vendor TTM; TTM net income + equity; P/E, P/B, ROE for banks |
| 1.17 | Ticker pre-trade read + risk flags + consolidation | Contracted 2026-11-08 | Seven rows, warnings-only color, four collapsible sections. No new data |
| 1.18 | SBC, debt maturities, earnings for every stored name | Contracted 2026-11-08 | SEC tags + Finnhub per-day calendar; FCF − SBC shown, rank unchanged until measured |
| 1.19 | Reverse DCF (implied growth) | Contracted 2026-11-08 | After 1.18 (needs SBC). Growth rate only, r grid 8/9/10% |
| R1 | Score validation (research) | Contracted 2026-11-08 | Quintile forward returns + IC of the Ideas rank; decides whether the rank shows in the pre-trade read |
| 2 | Gems universe D | Not started | Flag only on B; membership + Yahoo gems later. No F-score gate |
| 3 | Book + pre-trade risk + what-if | Contracted 2026-11-08 | Holdings, risk contribution, VaR / ES, stress, sizing limit, "add X for $N". Needs `launchd` |
| 3.6 | Thesis + invalidation triggers | Contracted 2026-11-08 | After 3. Fixed trigger menu, entry snapshot, nightly check |
| 3b | Constrained rebalance plan | Not started | After the Book is used; holdings-only min-vol first |
| 4 | Form 4 + insider sleeve | Not started | Until then, omit the insider column (do not show 0.5) |
| 5 | 10-K / 10-Q excerpts | Not started | Item 1A / Item 7 only; memo 10-Q stays `unavailable` |
| 6 | Recommendation writer | Not started | Pack desk metrics + citation gate; Python fills snapshot |
| 7 | Three-zone cards + Gems tab | Not started | Schema/`api.ts` before components. No F/Z drawer |

Last tracker update: 2026-11-08 (pre-trade contract).

---

## How to work a phase

Do not start the LLM writer or three-zone cards until packs exist. Desk-metric columns on **existing** pages are Phase 1.5 and should ship without a writer.

Order inside every phase:

1. Pull the item out of Northstar §12 into the current phase (if it is listed there).
2. Alembic + `store/models.py` + repos upserts (`ON CONFLICT`) when schema changes.
3. Adapter or analytics with **fixture tests** (no network).
4. Job with `job_run` + Makefile + pipelines.md row (if a job is needed).
5. API schema (if anything is served) then `web/lib/api.ts`. UI last.
6. Mark the phase **Done** here with the branch/commit and a one-line operator check.

Skills: `.cursor/skills/add-adapter`, `add-job`, `change-outlook-writer`.

---

## Phase 0 — Contract (done)

Rewrote the product sentence without becoming a broker: research terminal + decision layer, delayed data, no orders. Redis/GraphQL/FMP rejected. 2026-09-14: F-score / Altman Z removed from the product surface; named desk metrics are the read.

**Touched:** `docs/northstar.md`, `docs/system.md`, `docs/pipelines.md`, `AGENTS.md`, `config/universes.yaml` (`gems:` thresholds).

---

## Phase 1 — FY facts + ratio snapshot (warehouse done)

Fiscal-year snapshots from the existing SEC companyfacts zip. Gem **flag** only (no universe D). The branch first computed Piotroski F-Score and Altman Z; that code was removed on 2026-10-29 and the legacy `quant_score` columns are written NULL. Do not bring them back.

### Shipped

| Piece | Location |
|---|---|
| Tables | `metric_fy`, `quant_score` — Alembic `0016_metric_fy_quant` |
| FY extract | `ingest/sec/parse.py` `fy_history_from_facts` |
| Ratios / gem flag | `analytics/quant.py` (FCF yield, revenue growth, D/E, cap band) |
| Ingest | `jobs/ingest_sec.py` writes FY on full run; `--fy-only` backfills members |
| Compute | `jobs/compute_quant.py` / `make quant` |
| Health | `GET /health` → `metric_fy`, `quant_score` |
| Tests | `tests/test_quant.py`, FY cases in `test_sec_parse.py` |

**Keep from FY:** revenue, NI, CFO, assets, debt, equity — used for revenue YoY, accrual badge (CFO > NI), gems D/E (fail when equity ≤ 0).

**Operator check (this machine, 2026-09-14):**

```text
python -m jobs.ingest_sec --fy-only     # 939 members, 5502 FY rows, 4 failures
python -m jobs.compute_quant            # 935 rows, 1 gem flag (TASK)
GET /health                             # metric_fy=5502, quant_score=935
```

One gem flag on universe B is expected ($1B TTM revenue vs $300M–$2B cap). Do not build a Gems tab on it.

**Not in Phase 1:** desk-metric columns, Book, Gems membership, Form 4, F as a quality sleeve.

### Recurring

Nightly (after valuation Yahoo): `ingest_sec` (monthly zip is enough) → `compute_valuation` → `compute_quant` (gem flag / ratios) → `compute_scores` → memos. See pipelines.md.

---

## Phase 1.5 — Desk metrics on existing pages (done)

**Goal:** The operator can validate a name from standard desk numbers without SQL and without an LLM. Same language on Valuation and Opportunities.

**Do**

1. Northstar §3 / §9 / §11 / §12: already pulled — this is the current phase.
2. FastAPI: add named fields to `GET /valuation` and `GET /opportunities` (no new routes). Join `valuation_daily` + `metric_ttm` + `opportunity_score` + latest `metric_fy`. `quant_score` is **not** required for the grid.
3. `web/lib/api.ts`, then `ValuationView` and `OpportunitiesView`.
4. Opportunities primary columns:

   `# | Ticker | EV/EBITDA | 5y %ile | FCF yield | ND/EBITDA | EBITDA 1y | Trap`

   Rank remains the default sort. Accrual is a badge (yes / no / —), not a column that needs a legend. Hide Cheap/Quality/Change/Setup unit-ranks as the primary read. Hide insider until Form 4. Drop the 10-Q memo block until Phase 5 (or render `unavailable` only).
5. Valuation: keep EV/EBITDA and 5y %ile; add FCF yield and ND/EBITDA.
6. Bind ranker copy to those metrics (Quality = FCF margin and FCF yield). Do not wire F-score.
7. Browser verification: both pages, empty/stale, trap on, missing FCF/ND shown as —.

**Do not:** new tab, F/Z columns, sleeve 0–1 as the row the user reads, insider 0.50, `what_10q_changed` as invented prose, P/E or P/B.

**Shipped:** `api/desk.py` ratios; `GET /valuation` and `GET /opportunities` add `fcf_yield`, `nd_ebitda`, `accrual`; Valuation and Opportunities grids show those numbers (not sleeve 0–1). Quality sleeve blends FCF margin and FCF yield when both exist. Insider and 10-Q memo blocks omitted from the grid.

**Operator check:** open `/valuation` and `/opportunities`; missing FCF/ND render as —. Accrual is yes/no/— from latest `metric_fy`.

---

## Phase 1.6 — SEC TTM data quality (done)

**Why:** a CRWV deep-dive (2026-10-31) found the stored TTM wrong for most of the universe.

- Cash-flow concepts in 10-Qs are year-to-date. `_flow_ttm` only accepted 60–120 day spans, so CFO / capex / D&A fell back to the last annual: latest FCF equalled the prior quarter's for 755 / 933 names.
- 10-Ks rarely tag a discrete Q4. `_last_quarters` skipped the gap and summed an older quarter (CRWV revenue TTM 7.23B vs ~7.59B). No December TTM rows were written.
- EBITDA mixed TTM EBIT with an annual D&A; components were never checked for the same period end.
- `DEBT_CONCEPTS` summed `LongTermDebt` **and** its current / noncurrent parts (double count), from unbounded-stale instants.
- `MIN_COMPARABLE_OBS = 252` let a 1.5-year-old listing score Cheap 0.90.

**Do:** derive discrete quarters from YTD differences (Q2 = 6M − 3M, Q3 = 9M − 6M, Q4 = FY − 9M), require four contiguous quarters, null any component whose period end differs from revenue's, debt = `LongTermDebt` else current + noncurrent, plus short-term borrowings, instants within 45 days. Store `cfo` and `capex` on `metric_ttm`. Comparable needs ≥ 750 sessions (Cheap falls back to neutral). Replace each name's TTM history on ingest so stale rows do not survive. Fixture tests; re-run `ingest_sec` → `compute_valuation` → `compute_quant` → `compute_scores`.

Found while re-running: filers switch synonym tags between 10-Q and 10-K (capex, D&A, debt), so quarters merge synonyms in priority order with a per-concept fallback; debt reads lease-inclusive / convertible / senior-note tags; a balance sheet with no debt line for 400 days is debt-free (0), a filer that moved debt to custom tags stays unknown (CRWV Q2 2026). The old code silently used years-stale instants and annuals for all of these. `ingest_sec` now raises the 700–1000 band inside the write transaction (it used to commit first). `compute_scores` prunes scores for names outside the run, so dropped names no longer surface with old ranks.

**Result (2026-10-31, same Aug-18 zip):** 973 members (was 933); 860 ranked. Repeated latest FCF 755 → 1. Median rank move 99 places; 11 of the old top 25 remain. Out: names without a current standard capex / EBIT tag (e.g. APP, ABNB, BIIB) and CRWV (debt on custom tags) — candidates for a concept-coverage follow-up, not a fallback to stale data.

**Follow-up (2026-11-06):** SEC companyfacts omits some 10-Qs that exist on EDGAR with XBRL (SO, DUK, V, HUM Q2 2026; checked with a cache-buster, not ours), which broke the quarter chain for a year. TTM now falls back to FY + YTD − prior-year YTD (or a fiscal year ending at the newest period), quarterly filers only; the freshest of quarters / YTD wins, so a years-old chain no longer beats current data (IDA read 2018). Revenue breaks a same-date tie between tags by size: `RevenueFromContractWithCustomer…` is often a part of `Revenues` (HIG 1.8B vs 29.9B, URI, GM, ANDE). The larger tag must be no smaller in any summed period and larger in most, so a quarter inflated by a restatement (FY from the pre-spin 10-K minus a restated 9M: APTV, HON) does not win; the gross-of-excise tag never wins by size (BF-A, SAM). Added `RegulatedAndUnregulatedOperatingRevenue` (SR). Old vs new parser over 1150 names (2026-11-07): 70 change, 14 to a current date (stale or missing before), 56 same-date corrections (20 under 2%); TTM history is smoother (HIG max quarter-to-quarter step 5.1x → 1.05x). Review hardening: a YTD uses one tag for FY, YTD and prior YTD (never FY of one synonym minus YTDs of another); a larger same-date YTD beats a quarter chain only for a tag with no chain of its own there; an annual newer than every quarter / YTD candidate yields no quarterly TTM instead of an older chain. Known limit: a missing 10-Q right after a spin-off can still inflate the YTD TTM (FY from the pre-spin 10-K plus restated YTDs), the same hazard as FY − 9M for Q4; catching it needs the as-filed values, not only the latest restatement.

**Operator check:** CRWV TTM revenue at 2026-06-30 = 7.590B, a 2025-12-31 row exists, FCF differs quarter to quarter; `opportunity_score` has one row per ranked name.

## Phase 1.7 — Sector + per-name risk (done)

- `jobs.ingest_sec_profile`: SEC submissions `sic` → `config/sic_sectors.yaml` (ranges, first match wins, ticker overrides for SIC 7389 / travel / internet media) → `instrument.sector`; `industry` = `sicDescription`. Approximate GICS, not GICS. `upsert_instrument` now coalesces sector/industry so catalog upserts keep it.
- `risk_stats` + `jobs.compute_risk`: vol 3m / 1y, downside vol, beta vs SPY and QQQ, corr vs SPY, max drawdown 1y, drawdown from 1y high, from `adj_c` (valuation ∪ watchlist ∪ tape).
- `metric_ttm.ebit` / `interest_expense` (migration 0020). `analytics/desk.py`: `interest_coverage`, `share_change` (dilution), `financing_gap` ((capex − CFO) / market cap). Served from Phase 1.8.
- Fix: `ingest_sec --tickers/--limit` replaced the whole valuation membership with the subset; partial runs are now additive.

**Result (2026-10-31):** sector on 973 / 973 (0 unmapped); interest expense on 666 / 973; `risk_stats` 998 names. Names outside the universe (e.g. CRWV) get risk only once they are on the watchlist or tape.

**Operator check:** `select sector, count(*)` over the valuation universe has 11 sectors and no NULLs; MSFT coverage ≈ 50x, KODK < 1x.

## Phase 1.8 — Ticker + Compare pages (done)

- `GET /ticker/{ticker}`: identity (sector ETF from the tape catalog), last close, desk (EV/EBITDA, 5y %ile, FCF yield, ND/EBITDA, EBITDA and revenue 1y, interest coverage, share change 1y, financing gap, accrual, rank), TTM + FY history, technicals (`analytics/technicals.py`: SMAs, RSI 14, 52w range, returns, relative vs SPY and sector ETF), risk (`risk_stats`, else read-time from stored bars), next events, news. 404 when the ticker is not stored.
- `GET /compare?tickers=`: the same per-name blocks, 1y rebased overlay (with SPY) and pairwise correlation of 1y adjusted returns; unknown tickers come back in `missing`.
- `valuation_daily` is used only for current valuation members (a former member's row is stale); otherwise EV is read-time (close × TTM shares + net debt) and says so.
- `ingest_sec` now refreshes TTM / FY for every stored name it lists, not only members, so a name that drops out never keeps rows from an older parse (CRWV showed net cash from the pre-fix run).
- Web: `/t/[ticker]`, `/compare` (tab), ticker links from Valuation / Opportunities / Watchlist, header input jumps to `/t/X` or `/compare?tickers=A,B`.

**Operator check:** `/t/MSFT` full; `/t/CRWV` shows "outside every universe", EV "—" (Q2 debt unknown), interest cover < 0; `/compare?tickers=MSFT,META,NVDA,GOOG` renders table, overlay and heatmap; `/t/ZZZZ` says not stored.

**Known limits:** share counts come from SEC `dei` / weighted averages and can switch between one class and all classes, so "Shares 1y" can jump for multi-class issuers. Earnings dates and company news exist only for Watchlist names.

## Phase 1.9 — Rotation panels

Cross-asset RRG on existing tape (TLT, GLD, UUP, HYG, EEM vs SPY). Sector breadth (% above 200d) and median EV/EBITDA percentile once sectors exist. Intra-sector RRG. Factor ETFs (IWF/IWD, MTUM, QUAL, USMV) via `config/universes.yaml`. "Sell X, buy Y" stays Phase 3.5 — no separate simulator.

## Phase 2 — Gems universe D

**Goal:** A second universe of US names with market cap $300M–$2B, TTM revenue ≥ yaml floor ($50M), usable XBRL. Honest copy: liquid small/mid with full SEC history, not seed-stage.

**Do**

1. Northstar §7 / §12: pull “Gems membership” into the current phase.
2. Screen in SEC space first (`metric_fy` + `metric_ttm` + public float / later price×shares). Do **not** Yahoo-ingest thousands of names.
3. `universe` name `gems`; `replace_membership` like valuation.
4. Rules: yaml cap band, revenue growth, FCF yield, D/E. Fail negative book equity. Same desk metrics as B.
5. `ingest_yahoo --universe gems --resume` only for survivors (cap membership, e.g. ≤300).
6. Recompute cap; keep $300M–$2B. Re-run ratio / gem-flag job on D (or B∪D).
7. `GET /gems` + Gems tab **wait for Phase 7**. Prefer API+light grid only if you need to inspect members without SQL.

**Do not:** F ≥ 7 at write time or as a UI default. Do not require insider ownership >10% (needs Form 4 / DEF 14A). Do not add 13F. Do not ship a tab on the one B-universe flag.

**Depends on:** Phase 1. After 1.5 for user value; can parallel Book for Yahoo-budget reasons.

---

## Phase 3 — Book + pre-trade risk (contracted 2026-11-08)

**Goal:** One operator-sized book (shares, average cost, cash) and the answer to "how much can I lose, and what does this add do to my risk?". Watchlist remains the unsized tracker. This is the step that turns the terminal into a decision layer. Operator chose the full scope for v1 (2026-11-08): risk + stress + what-if + sizing limit in one PR.

**Do**

1. Northstar §3 / §8 / §9 / §11 / §12: done in the pre-trade contract PR.
2. Alembic: `portfolio` (singleton cash, loss budget % of NAV) + `portfolio_holding` (`instrument_id`, shares, average_cost, opened_on). No `user_id` UUID. `book` universe kept equal to holdings by the repo, so bars / risk / options / estimates / earnings scopes include holdings (CRWV gets covered by holding it, without the watchlist).
3. `analytics/portfolio_risk.py` (classes, fixture tests, no network): `ReturnPanel` (1y adjusted log returns, sector-ETF proxy for short histories, labeled), `ShrunkCovariance` (Ledoit-Wolf toward constant correlation), `PortfolioRisk` (vol, VaR 95% 1m parametric + historical, ES 97.5%, Euler contributions, top correlated pairs, sector weights), `StressTest` (historical windows + factor shocks from `config/stress_scenarios.yaml`), `SizingLimit`.
4. `jobs.compute_portfolio` after `compute_risk`: delayed MV, weight, unrealized P&L, the risk read above → `portfolio_snapshot` JSONB with as-of. `job_run`, Makefile, pipelines.md.
5. API: `GET/PUT /portfolio`, holdings CRUD (add hydrates like `POST /watchlist`: job helper, no vendor in the route), `GET /portfolio/what-if?ticker=&amount=` (read-time, before / after, cash check, sizing limit).
6. Book tab: holdings, weights, P&L, sector stack, risk contribution bar, VaR / ES, stress table, correlated pairs. What-if box also on the Ticker page next to the pre-trade read. `StaleBadge`. No blotter, no Sharpe on the primary view.
7. **Prerequisite:** `launchd` recipes (2026-11-03 review item 3). A risk read on stale bars is worse than none; the snapshot carries the bars' as-of and goes stale with the freshness strip.

**Operator check:** with 3+ holdings, risk contributions sum to portfolio vol; the parametric VaR matches a hand calc on a 2-name fixture; a CRWV holding shows the proxy label until it has 252 sessions; what-if with amount > cash says so.

**Depends on:** Phase 1.5, `launchd`. Can run in parallel with Phase 2.

### Phase 3.5 — Book-aware Ideas (no optimizer)

**Goal:** the what-if, per row. For each Ideas row when the book is non-empty: ρ vs current holdings, sector overlap, marginal vol at a stated add (e.g. 2% of NAV). Reuses `PortfolioRisk`. Hide when cash is the only holding (Path B). Rank continuously; no magic ΔSharpe cut.

**Depends on:** Phase 3.

### Phase 3.6 — Thesis + invalidation triggers (contracted 2026-11-08)

**Goal:** no position without a written reason and a machine-checked way to know it broke. The documented value of a decision journal is against hindsight bias and thesis drift; it only works when the triggers are checked, so free text alone carries no trigger state.

**Do**

1. Alembic: `thesis` (one open per instrument: text ≤ 3 lines, horizon date, pre-mortem, entry snapshot JSONB of the desk metrics, close note + exit snapshot) and `thesis_trigger` (kind from the fixed menu in Northstar §9, threshold `NUMERIC` or bucket, state, last_checked, fired_at).
2. `analytics/thesis.py` `TriggerCheck` per kind (fixture tests). `jobs.check_theses` nightly after risk / credit / estimates.
3. API: `GET/PUT /thesis/{ticker}`, `POST /thesis/{ticker}/close`. Works for Book holdings and for watchlist names before entry.
4. UI: thesis block under the pre-trade read on Ticker; trigger chips on Book and Watchlist; a "theses tripped" chip on Live. On close, entry vs exit snapshot side by side.

**Operator check:** a fixture thesis with "close below 200d SMA" fires on the first stored close below it and records `fired_at`; closing keeps both snapshots.

**Depends on:** Phase 3 (entry snapshot uses the same desk read), 1.17.

---

## Phase 3b — Rebalance plan (optimization)

**Goal:** Target weights for **this** book. Not a 900-name mean-variance stock picker. Do this **after the Book is actually used**.

**Do**

1. Northstar: `portfolio_plan` table purpose; still no orders.
2. `analytics/portfolio_opt.py` + `jobs.compute_portfolio_opt`.
3. v1 method: **long-only min-vol** (or risk-budget) on holdings ∪ cash, name cap, sector cap, turnover cap, no-trade band.
4. Do **not** use raw 126d mean as μ. Optional max-Sharpe later with shrunk μ + small quant tilt.
5. Candidate set if you allow adds: holdings + top-N Opportunities + gem flags + watchlist. Never the full valuation universe.
6. `GET /portfolio/plan`. Book **Plan** panel: current vs target, turnover, vol/Sharpe delta. Label is not “optimal.”
7. Later rec types: `REBALANCE` trims from Δw; funding legs packed for the writer.

**Depends on:** Phase 3, ≥2 risky names with overlapping history. Empty book → skip (Path B = today’s Opportunities list).

---

## Phase 4 — Form 4

**Goal:** Replace the unused insider stub with stored net buying, then show a column.

**Do**

1. Same `ingest/sec` vendor: submissions JSON → Form 4 XML. Rate limit / 429 fail-fast.
2. `insider_transaction` table; aggregate 14d / 90d net buy.
3. Wire `analytics/scores.py` insider sleeve. Tests: P vs S vs option exercise (`M` is not an open-market buy).
4. Then display the column. Until this phase, omit it.
5. Do not store raw XML in the hot table.

**Depends on:** Phase 0. Can parallelize with Phase 2/3. Shared submissions client with Phase 5.

---

## Phase 5 — Filing excerpts (no RAG)

**Goal:** Item 1A and Item 7 (10-Q Item 2) text in Postgres for the writer. Fail closed.

**Do**

1. `filing_index` + `filing_excerpt` (capped text, hash, `parse_ok`). Not a `financial_fact` warehouse.
2. Official EDGAR HTML only. Parser golden files: one 10-K, one 10-Q, one amendment.
3. Job over **writer candidates only** (top Opportunities, gem names, book names) — not the full 900.
4. Missing extract → pack field `unavailable`. No fetch at generation time. Only then may memos fill a 10-Q change.

**Depends on:** submissions client (Phase 4 can land first).

---

## Phase 6 — Recommendation writer

**Goal:** Dated recommendation rows. Thesis from the pack. Snapshot numbers from Python.

**Do**

1. Tables: `recommendation` (type `ALPHA` / `GEM` / `REBALANCE` / `HEDGE`, optional fit fields, thesis JSONB, snapshot JSONB, pack JSONB).
2. Python snapshot: delayed last, EV/EBITDA, 5y %ile, FCF yield, ND/EBITDA, EBITDA 1y, trap, accrual, cash-affordable size / sector cap if Book exists. **No LLM-owned entry/target/stop. No F/Z.**
3. Path A (book nonempty): fit from ρ, sector overlap, cash used — rank continuously, no magic 0.05 Sharpe cut without units.
4. Path B (empty book): today’s Opportunities + gem flag + regime. No second ranker. Hide fit.
5. Writer schema: `thesis_bullets`, `risk_factors`; `insider_activity_summary` only if Form 4 packed. Citation check must pass or keep previous / template.
6. Label in pack and later UI: research snapshot, delayed, not advice, not an order.

**Depends on:** Phases 1.5 + 3 at minimum; 4/5 make cards honest. 3b is optional.

---

## Phase 7 — UI

**Goal:** Dense terminal cards and a Gems grid. Explain shows packed ratios + as-of dates + excerpt hashes — not nine binary tests.

**Do**

1. FastAPI schemas first, then `web/lib/api.ts`, then components.
2. Opportunities card: **three zones** — header (ticker, delayed last, trap, sector), desk snapshot (the named metrics), book impact if holdings exist. Hide fit on Path B. Thesis optional and last.
3. Gems tab: cards with the same desk metrics (not an LLM “moat”). 90d insider badge when Form 4 exists.
4. Book Plan panel if 3b shipped.
5. Browser verification: Book CRUD → snapshot → Opportunities overlap; empty book still shows ALPHA as the Opportunities list.

**Depends on:** Phase 6 (and 2 if Gems tab). Keep green/red for signed P&L and returns only.

---

## Phase 1.10 — Peer comps + credit curve (done)

- Ticker page: peers = same sector, valuation universe, nearest by market cap (cap 10). Columns are the Compare desk metrics. Scatter EV/EBITDA vs EBITDA 1y with the name highlighted and the sector median lines.
- FRED catalog: `BAMLC0A1CAAA`, `BAMLC0A2CAA`, `BAMLC0A3CA`, `BAMLC0A4CBBB`, `BAMLH0A1HYBB`, `BAMLH0A2HYB`, `BAMLH0A3HYC` (OAS) and the matching effective-yield series, `DGS1`, `BAA10Y`, `NFCI`, `STLFSI4`. ICE series on FRED carry ~3y of history only.
- Ticker: the rating curve (OAS by bucket today vs 1y ago, Δ 1m / 1y, effective yield, Baa−10Y, NFCI, STLFSI). Live panel deferred until the implied bucket exists.
- Shipped: `GET /ticker/{t}` → `peers` (self row from the page's own desk, 1y return from adjusted closes; `return_stats` only covers sector ETFs); `GET /credit/curve`; `FredSeriesItem.in_pack` keeps reference series out of the writer pack; `ingest_sec_profile --tickers` now accepts names outside every universe (CRWV had no sector).

**Operator check:** `/t/MSFT` peers AAPL / NVDA / AVGO…, sector median EV/EBITDA ~20x; `/t/CRWV` peers in Information Technology by cap; credit curve CCC ~1,325bp (+500 over 1y).

**Known limits:** peers are sector + size, not business model (CRWV's comps are FLEX / TTWO / UI, not AI-infra names). SIC sectors are approximate (OTIS lands in IT). A curated peer override (`config/peers.yaml`) is the follow-up if this bites.

## Phase 1.11 — Equity-implied credit bucket (done)

Method in Northstar §9. Spike (2026-10-31, scratch only, 65 rated names + CRWV held out, FRED 2026-10-29):

| Bucket | AAA | AA | A | BBB | BB | B | CCC |
|---|---|---|---|---|---|---|---|
| ICE BofA OAS (bp) | 46 | 65 | 74 | 110 | 194 | 332 | 1,325 |
| Median DD anchor | 11.05 | 8.91 | 8.04 | 4.55 | 2.61 | 2.46 | 1.19 |

- Spearman(rating, −DD) = 0.80; leave-one-out implied bucket exact 24/65, within one bucket 56/65.
- CRWV (held out, rated B, CDS ~1,000–1,140bp in Oct 2026 press): DD 0.98, below the CCC anchor → reads **below CCC**. MSFT: DD 10.2 → AA.
- Raw Merton N(−DD) spreads were ~0bp for every IG name: the bucket mapping is required, not optional.
- Default point uses liabilities (every filer tags them; gross debt is missing for CRWV / GM / F from custom tags). Removing current deferred revenue moved MSFT AAA-side and kept the HY order; software names still read one bucket low (CRM BBB, ORCL BB).
- Thin tail: 5 B names (WYNN at DD 4.3 drags the median) and 2 CCC. Fix by adding rated HY names to the calibration yaml, not by changing the model.
- Ratings in the spike came from operator memory. **Before ship:** `config/credit_calibration.yaml` with source + as-of per row, reviewed by the operator.
- **Re-run on the verified set (2026-10-31, `config/credit_calibration.yaml`, 106 rows, 91 fitted):** anchors AAA 11.05 · AA 9.08 · A 7.59 · BBB 4.59 · BB 2.69 · B 1.76 · CCC 1.33 (B now has 19 names, CCC 4). Spearman 0.84; leave-one-out exact 35/91, within one bucket 84/91 (92%). Misses > 1 bucket are low-vol levered payers (KO, MO, MCD, KMI, TDG read too safe), CABO (vol 112%) too risky, BLCO too safe. CRWV (S&P B+, held out) still reads below CCC; MSFT AAA; ORCL (BBB-) reads BB; META (AA-) reads A.
- Output: `credit_implied` (instrument, as_of, E, F, σ_E, σ_A, DD, bucket, bucket_oas_bp, calibration_version). Excluded sectors per Northstar §9. Not a rank input.
- Shipped: `analytics/credit.py` (default point, Merton solve, anchors, placement, inputs), `metric_ttm.current_liabilities / total_liabilities / deferred_revenue_current` (migration 0021; L&SE − equity fallback), `credit_implied` + `credit_anchor`, job `compute_credit` (897 names on 2026-10-30; anchors AAA 11.02 · AA 9.15 · A 7.61 · BBB 4.65 · BB 2.69 · B 1.81 · CCC 1.30), `credit` block on `GET /ticker` (stored, else read-time on the stored ladder; agency rating from the yaml when present), `CreditImpliedPanel` + implied bucket ringed on the curve.

**Operator check:** `/t/CRWV` "Below CCC" vs S&P B+; `/t/MSFT` AAA; `/t/ORCL` BB vs BBB-; `/t/V` "Not scored".

**Known limits:** whole Financials / Real Estate sectors are excluded, which also drops payment networks (V, MA, PYPL) that Merton could score; narrow the exclusion to banks / insurers / REITs by industry if that matters. Operator decision 2026-11-01: keep it sector-wide for now; do not narrow without asking. Low-vol buyback-levered issuers read too safe. Re-review `config/credit_calibration.yaml` when agencies move (rows carry as-of dates).

## Phase 1.12 — Options read (done)

- Chains for watchlist + Opportunities top 25 + SPY / QQQ / IWM / sector ETFs, ~4 monthly expiries, within the Yahoo 2 req/s budget (one request per expiry).
- `option_stats` daily per name: ATM IV 30d, IV / RV, P/C volume and OI, 25d skew proxy, term slope, expected move to earnings. IV rank after 252 stored sessions only.
- Tape: ^VIX9D, ^VIX3M, ^VVIX, ^SKEW. Cboe daily JSON → `options_market_stats` with a date backfill (≥ 2025-03 verified).
- Visuals: IV term structure, skew curve, VIX curve slope, equity P/C history.
- Shipped: `ingest/cboe/` (daily JSON, six products validated, 403 = no file), `YahooClient.fetch_option_expiries / fetch_option_chain` on the same token bucket, `analytics/options.py` (Black-Scholes IV on OTM mids, monthly picker, total-variance term interpolation, skew, expected move, IV rank), migration 0022 (`option_chain_snapshot`, `option_stats`, `options_market_stats`), jobs `ingest_options` and `ingest_cboe`, `options` block on `GET /ticker`, `GET /options/market`, `OptionsPanel` (Ticker) and `MarketOptionsPanel` (Dynamics).
- First run (Sat 2026-11-01, close 2026-10-30): 45 names in ~2 min, ~11k chain rows; 42 with a 30d IV, 30 with a skew. Cboe backfill 2025-03-03 → 2026-10-30, 420 sessions, none missing. SPY 30d IV 16.7% (VIX 19.4), skew +13 pts; VIX ÷ VIX3M 0.93; equity P/C 0.66 (81st percentile of the year).
- Quote cleaning found on that run: Yahoo IV on deep ITM rows reached 235%; thin sector ETFs quote $3–5 wide after the close; XLE carried a Dec call bid at 22% of spot a year after its last trade. Hence OTM only, spread ≤ ½ mid (10c floor) else a same-session print, price monotone away from spot, and a strike-neighbour IV outlier cut.

**Operator check:** `/t/SPY` 30d IV a few points under VIX, positive skew; `/t/MSFT` expected move blank until earnings are within 45 days; `/dynamics` "What is the options market pricing?" ratio below 1 on a calm day.

**Known limits:** run before the close; weekend runs leave some ETF IVs empty. Put/call per name counts the stored monthlies ±30%, not the whole chain. The expected move covers spot to the first expiry after earnings, so a monthly far from the date overstates the event. IV rank is blank until 252 sessions are stored (~Nov 2027). Cboe ratios are Cboe-listed volume only.

## Phase 1.13 — Kalshi + CFTC (done)

- Kalshi `KXINX` / `KXNASDAQ100` range series → implied distribution of the next close (median, 10/90 band) on Live. `KXFEDDECISION` and `KXRECSSNBER` sit on the Polymarket `front_fomc` / `recession` rows in `odds_snapshot` (now keyed `source + slot`).
- CFTC TFF (Socrata `gpe5-46if`, futures only): asset manager / leveraged funds net as a share of open interest and its 3y percentile for S&P 500, Nasdaq-100, Russell 2000, UST 2Y / 10Y, VIX → `cot_position`, table on Dynamics.

**Shipped:** `ingest/http.py` (`JsonApiClient` base for new JSON vendors), `ingest/kalshi/`, `ingest/cftc/`, `analytics/prediction_markets.py` (`RangeDistribution`), `analytics/positioning.py` (`PositioningRead`), `jobs/ingest_kalshi.py`, `jobs/ingest_cftc.py`, `api/odds.py` (`KalshiLiveView`), `api/positioning.py`, `GET /positioning`, Live Market-implied panel rows, `PositioningPanel.tsx`.

**Run:** `make cftc-backfill kalshi`; then `ingest_kalshi` in session and `ingest_cftc` on Fridays.

**Limits:** CPI has no Kalshi pair (Kalshi lists core CPI month-over-month, Polymarket year-over-year), so that row stays Polymarket only. Kalshi is shown only for the outcome Polymarket ranks first and only at the same FOMC meeting. Kalshi's recession contract is NBER "starts this year", Polymarket's is "by end of 2026": the definition is in the row tooltip, and the pair shows only when both name the same year. `ingest_kalshi` skips events past their strike (Kalshi keeps them open until settlement). Outlook pack still reads Polymarket only.

## Phase 1.14 — Short interest + estimate revisions (done)

Scope changed on 2026-11-03 (operator decision): price targets and buy / hold / sell counts are out. They lag the price, skew optimistic and read as a target; estimate revisions are the documented signal.

- FINRA consolidated short interest (public API, no credential) for every stored instrument: short as a share of shares outstanding (SEC, not float), days to cover, change vs the prior cycle → `short_interest`, one year backfilled.
- Yahoo `earningsTrend` for the watchlist ∪ Opportunities top 25: consensus EPS for the current and next fiscal year, its 30d / 90d change, analysts revising up / down in 30 days → `eps_revision`. Labeled street consensus, vendor data.

**Shipped:** `ingest/finra/` (`FinraClient` on `JsonApiClient`, now with read-only `post_json`), `YahooClient.fetch_eps_revisions`, `analytics/street.py` (`ShortInterestRead`, `RevisionRead`), `jobs/ingest_finra.py`, `jobs/ingest_estimates.py`, `api/street.py` (`StreetView`), `street` block on `GET /ticker/{ticker}`, `StreetPanel.tsx`.

**Run:** `make finra-backfill estimates`; then `ingest_estimates` daily and `ingest_finra` after each FINRA publication.

**Limits:** short share is of shares outstanding, not float (understates for closely held names). Revisions only for the watchlist ∪ top 25; other Ticker pages say so. Not in the writer pack yet.

## Phase 1.15 — Foreign filers + bank read (done)

**Why.** The operator analyzes LatAm ADRs (NU, DLO, VIST, MELI, IREN) next to US names. Today they have bars and risk only: NU and IREN have no CIK, so `ingest_sec` skips them as `no_cik`, and 20-F filers never reach the valuation screen.

**What the SEC data looks like (probe 2026-11-07, companyfacts JSON):**

| Name | Forms in XBRL | Basis / currency | Latest SEC period | Current parser |
|---|---|---|---|---|
| IREN | 10-K, 10-Q (domestic filer since 2025) | US GAAP / USD | 2026-09-30 | Full TTM; only the CIK is missing |
| MELI | 10-K, 10-Q | US GAAP / USD | 2026-09-30 | Works; refresh only |
| DLO | 20-F + tagged 6-K | IFRS / USD | FY 2025 (6-K tags stop at 2025-09-30) | Revenue / CFO / capex only; EBIT, D&A, net debt missing (IFRS concept names) |
| NU, VIST | 20-F only | IFRS / USD | FY 2024 | Annual only, about 22 months old |
| YPF | 20-F | IFRS / USD + ARS | FY 2025 | Yahoo statements are labeled ARS with about 10× the share count: out |
| PAM | 20-F | IFRS / ARS (Yahoo USD) | — | ADR = 25 shares: out until the ratio path is tested |

SEC alone gives these names annual data that is 10 to 22 months old. Yahoo quarterly statements are current (Q2 or Q3 2026) and in USD for NU, DLO, VIST, PAM.

**Operator decisions (2026-11-07):**

1. Quarters come from Yahoo quarterly statements, labeled vendor data (`metric_ttm.source = yahoo`), like the EPS revisions. SEC 20-F / 6-K stays the official source and wins on the same period.
2. ARS reporters (YPF, PAM) stay out. USD reporters first.
3. Banks (NU) get a bank read (P/E, P/B, ROE) and stay out of EV/EBITDA, the rank and Merton.
4. Foreign filers join universe B and the watchlist, so they appear on Valuation / Opportunities like any member. The 5y percentile is `comparable = false` until the history is long enough.
5. Membership is a curated list in `config/universes.yaml` `valuation.foreign_filers`: ticker, ADR ratio, bank flag. Never auto-detected.
6. `metric_ttm` gets `net_income` and `equity` for every name (migration). This phase shows P/E / P/B only for banks.

**Build order:**

1. **Identity.** Fill `instrument.cik` from SEC `company_tickers` for stored instruments with a NULL CIK (watchlist, foreign filers). Keep `upsert_instrument` coalescing the CIK.
2. **Catalog.** `valuation.foreign_filers` in `config/universes.yaml` with a typed model in `store/catalog.py`. Seed: NU (bank), DLO, VIST.
3. **SEC parser.** Add IFRS concepts: EBIT (`ProfitLossFromOperatingActivities`), D&A (`DepreciationAndAmortisationExpense`, or depreciation + amortisation lines), debt (`Borrowings`, `LongtermBorrowings`, `ShorttermBorrowings`, lease liabilities on the same rule as US GAAP), cash (`CashAndCashEquivalents`), shares (`dei:EntityCommonStockSharesOutstanding`), net income (`ProfitLoss`), equity (`Equity`). Accept tagged 6-K rows as quarters. Fixture tests from DLO / NU / VIST companyfacts.
4. **Migration.** `metric_ttm.net_income`, `metric_ttm.equity`. SEC parser fills both for every name.
5. **Yahoo statements.** `YahooClient.fetch_quarterly_statements` → frozen `QuarterlyStatement` in `store/canonical.py` → TTM from the last four quarters. The adapter rejects non-USD `financialCurrency` and fewer than four quarters. Shares come from Yahoo × ADR ratio, checked against SEC `dei` shares when present.
6. **Job.** `ingest_sec` runs the Yahoo pass for the curated foreign filers after the SEC pass. It writes only TTM points newer than the latest SEC point. Run meta lists skipped names and why (`non_usd`, `few_quarters`, `shares_mismatch`).
7. **Membership.** Curated foreign filers are members of `valuation`; `compute_valuation` / `compute_scores` / `compute_risk` pick them up unchanged. Banks are skipped by `compute_valuation` and `compute_credit`.
8. **Bank read.** `analytics/bank.py` `BankRead` (P/E, P/B, ROE with as-of and source) → `bank` block on `GET /ticker/{ticker}` → one Ticker panel. No new page.
9. **UI labels.** A `source: yahoo` TTM shows "vendor quarters" next to its as-of date on Ticker and Valuation.

**Shipped (branch `feat/foreign-filers`):**
- Migration 0025: `metric_ttm.net_income` / `equity`.
- IFRS concepts and 6-K periods in `ingest/sec/parse.py`.
- `upsert_metric_ttm(..., source=)`; prune by source.
- `YahooClient.fetch_quarterly_statements` → `QuarterlyStatement`, and `ingest/yahoo/statements.py` `StatementTtm`.
- `jobs/foreign_filers.py` `ForeignFilerSync`: identity, CIK fill, membership, Yahoo TTM, run meta.
- Banks skipped in `compute_valuation` / `compute_credit`.
- `analytics/bank.py` `BankRead` → `bank` on `GET /ticker`.
- `ttm_source` on the desk, TTM rows and `GET /valuation`.
- Bank valuation panel and `*` vendor-quarter labels in the web.

**First run (2026-11-07):**

| Name | TTM | Reads |
|---|---|---|
| DLO | SEC 6-K to 2025-12, Yahoo to 2026-06 | EV/EBITDA 12.3x, FCF yield 11.7% |
| VIST | Yahoo to 2026-09 | EV/EBITDA 3.8x |
| NU (bank) | Yahoo to 2026-06 | P/E 16.1x, P/B 4.4x, ROE 27% on ending equity |

IREN and MELI got their CIK / Q3 2026 SEC TTM. YPF is skipped as `non_usd`.

**Limits.**
- Opportunities ranks only `comparable` rows (≥ 750 sessions of own multiple history). DLO / VIST show on Valuation, but are unranked until that history exists. The Valuation grid shows "—" for a non-comparable EV/EBITDA; the Ticker page shows the number.
- "Revenue 1y" / "Shares 1y" need a TTM row 300–430 days back. For DLO the SEC history jumps from 2024-12 to 2025-09, so those read "—" for now.
- SEC SIC codes can mislabel. IREN is SIC 6199 (Finance Services) from its bitcoin-mining origin. By operator decision (2026-11-07) a `tickers` override in `config/sic_sectors.yaml` maps it to Information Technology, which keeps its Merton bucket; the Financials exclusion stays sector-wide. DLO maps to Industrials (SIC 7389, business services).
- Yahoo statements are vendor data, not filings: no restatement history, about 5 quarters deep, so the 5y percentile stays non-comparable for these names for years.
- The ADR ratio is curated by hand.
- Bank metrics have no loan-growth or NIM line in this phase.
- `ingest_finnhub_news` / `ingest_calendar` reach these names once PR #26 (watchlist from DB) merges.

**Operator check.**
- `make sec` with the foreign filers in the yaml.
- Then `ingest_yahoo --universe valuation`, `ingest_sec_profile --tickers NU,DLO,VIST`, and the compute jobs.
- `GET /ticker/DLO` shows TTM as of Q2 2026, `source: yahoo`, with EV/EBITDA.
- `GET /ticker/NU` shows the bank block and no EV/EBITDA.
- DLO / VIST appear on Valuation.

## Phase 1.16 — Ideas: score rules, sector-neutral 12-1 ranking, Ideas page (PRs 1–2 of 3)

**Why.** The UI audit (2026-11-03) found the Opportunities top 25 led by data artifacts (KODK FCF yield 79% from a one-off, AMN EBITDA +864% off a near-zero base) and 12 of 25 names in software that fell against its own history. Operator decisions (2026-11-07, prototype canvas): merge Valuation + Opportunities into one Ideas page, keep artifacts out of the rank but visible with the reason, rank within sectors, use 12-1 momentum.

**Shipped in PR 1 (`compute_scores`, no UI yet).**
- `analytics.scores.ScoreGate`, four rules: `fcf_one_off` (FCF TTM rose from a TTM at or below zero, within the last four, by more than 15% of revenue, or FCF yield above 30%), `base_effect` (|EBITDA 1y| > 300%), `extreme_multiple` (EV/EBITDA > 60x), `stale_ttm` (TTM older than `TTM_STALE_DAYS` = 150, the number the freshness strip uses). Failing names go to `score_exclusion` (rule + the numbers behind it), never to `opportunity_score`.
- Quality, change and setup rank within the sector (`SECTOR_MIN_NAMES` = 10; smaller sectors ranked together). Cheap stays the name's own 5y percentile.
- Setup = 12-1 momentum from adjusted closes (`opportunity_score.ret_12_1`); `ret_3m` stays for display.
- `SSRM` → Materials (SIC 6795 "mineral royalty traders").
- `compute_scores --dry-run` prints the top 25 and the exclusion counts without writing.

**First run (2026-11-08, scores as of 2026-11-06).** 774 ranked, 81 excluded (`fcf_one_off` 25, `stale_ttm` 22, `base_effect` 19, `extreme_multiple` 18). 8 of the old top 25 stay; KODK, AMN, WLKP and SONO are excluded; software leaves the top 25 (12 → 0), mostly on 12-1 momentum (DOCU #1 → out). The top 25 drives the `ingest_estimates` and `ingest_options` scope and memo generation, so those move too.

**Shipped in PR 2 (`GET /ideas` + Ideas page).**
- `GET /ideas` (`api/ideas.py` `IdeasBoard`) returns every valuation member once with a status: `ranked`, `excluded` (rules + values from `score_exclusion`) or `no_score` (no comparable multiple). It also carries the rule texts and sleeve weights from `analytics.scores`, so thresholds live in Python only, and top-25 stats (median EV/EBITDA and own-5y %ile, net cash, traps, sector concentration).
- `/ideas`: Shortlist (top 25) / All / Excluded, sector filter, search, column sort, detail panel (sleeve bars, stored memo or desk summary, exclusion rules). 12-1 replaces 3m on screen. Decisions (2026-11-08): English like the rest of the app; All = the whole valuation universe; old pages redirect and their code is removed.
- `GET /valuation` and `GET /opportunities` are removed; `/valuation` and `/opportunities` redirect to `/ideas`.
- Ticker "rank X of N" counted every stored score row (1556); it now counts names in the current run (776).
- First read (scores as of 2026-11-06): 973 in the universe, 857 with comparable data, 776 ranked, 81 excluded, 116 no score.

**Next.** PR 3: "What changed" (top-25 entries and exits, EBITDA-margin turns, EPS revisions once the universe-wide Yahoo test passes).

**Known.** Health insurers (UNH, ELV, HUM, MOH; SIC 6324) and DLB sit in Financials by SIC; moving them changes the Merton credit scope, so it waits for an operator decision.

## Pre-trade plan (contracted 2026-11-08)

**Why.** The goal is not to take risk without knowing it. A review against industry practice (Morningstar / Koyfin / TIKR snapshots, buy-side pre-trade checklists, Bloomberg PORT / Barra-style risk, Mauboussin's expectations investing, decision journals) found the stored data mostly sufficient but spread over twelve Ticker panels, with four real gaps: no sizing or portfolio risk, no thesis discipline, FCF overstated where SBC is heavy, and earnings dates only for watchlist names.

**Operator decisions (2026-11-08).**
- Pre-trade read colors **warnings only** (amber / red); nothing is colored good.
- SBC: show FCF and FCF − SBC, measure the top-25 impact, decide the ranking afterwards (same method as 1.6).
- Book v1 is the full scope (risk, stress, what-if, sizing limit).
- Score validation (R1) runs in parallel and decides whether the Ideas rank appears in the pre-trade read.

**Order.** After the sector PR (insurers → Health Care, DLB → IT) and Ideas PR 3:

```text
1.17 pre-trade read ─ 1.18 SBC / maturities / earnings ─ 3 Book (+ launchd) ─ 3.6 thesis ─ 1.19 reverse DCF
R1 score validation in parallel (no UI)
```

Outlook pack integration of 1.10–1.14 (2026-11-03 review item 1) is still unscheduled; ask before slotting it.

### Phase 1.17 — Ticker pre-trade read + consolidation

1. `analytics/risk_flags.py` `RiskFlags` with thresholds in `config/risk_flags.yaml` (fixture tests per rule).
2. `api/ticker.py`: `TickerSummary` builds the seven rows from blocks the route already reads (valuation, desk, credit, technicals, revisions, short interest, options, next event) plus sector medians; `summary` on `GET /ticker/{ticker}`. Then `web/lib/api.ts`.
3. `TickerView`: pre-trade read + flags above the fold; the existing panels move into four collapsible sections (business numbers, valuation & peers, credit, market), news and events last. No panel is deleted in this PR.
4. Rank row: hidden until R1 says otherwise.

**Operator check:** `/t/MSFT` reads in one screen; `/t/CRWV` shows the stale / outside-universe flags; a bank shows P/E, P/B, ROE in the valuation row; no green anywhere in the read.

### Phase 1.18 — SBC, debt maturities, earnings for every stored name

1. `ingest/sec/parse.py`: `ShareBasedCompensation` (synonym `AllocatedShareBasedCompensationExpense`), YTD-differenced like CFO → `metric_ttm.sbc`; `LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths` / `…InYearTwo` from the latest 10-K. Migration for the columns.
2. Desk read + Ticker: FCF − SBC, its yield, debt due vs cash + FCF. `compute_scores --dry-run` variant prints the top 25 with FCF − SBC in Quality; the result goes into this file for the ranking decision.
3. `FinnhubClient.fetch_earnings_by_day` (unfiltered calendar, one day per request, filter to stored tickers, per-symbol fallback when a day hits the cap). `ingest_calendar` covers every stored instrument; the options expected move then works for the whole options scope.

**Operator check:** software names show FCF − SBC well below FCF; an Ideas name outside the watchlist has a next-earnings date; `ingest_calendar` logs request count (~90 for 90 days).

### Phase 1.19 — Reverse DCF (implied growth)

`analytics/expectations.py` `ImpliedGrowth` (bisection on g, fixture tests against a hand-built DCF). Row on the valuation section of Ticker: implied g at 8 / 9 / 10% beside revenue CAGR 5y, FCF CAGR and revisions. Read-time, no table; store only if Ideas needs it later. Unavailable cases per Northstar §9.

**Operator check:** a name priced at exactly its constructed DCF returns the constructed g; CRWV reads unavailable (FCF − SBC ≤ 0).

### R1 — Score validation (research, no UI)

Rebuild monthly Ideas scores from stored history with a **reporting lag** (TTM usable 60 days after period end for 10-Q, 90 for 10-K, unless the filing date is stored) to avoid look-ahead. Spearman IC of the rank vs next 3m / 6m returns, within-sector; quintile spreads; IC stability by year. Survivorship bias: the universe is today's membership, so results are an upper bound. Output recorded here; decision rule: mean IC below ~0.02 or unstable sign → the rank stays out of the pre-trade read. `analytics/score_validation.py` + `jobs.validate_scores` (prints, writes no table).

## Explicitly deferred

| Item | Why |
|---|---|
| Piotroski F-Score / Altman Z as UI, rank, or pack | Opaque composites; desk metrics replace them |
| LLM “moat” / fit-percentage gauges | Second opaque rank |
| Entry / target / stop on the card | Read as advice even when Python-filled. Street price targets were allowed as vendor data, then dropped from 1.14 (2026-11-03) |
| Sleeve unit-ranks as the primary Opportunities columns | After 1.5 the row is the named metrics |
| Hard-cut F ≥ 7 | Throws away the middle of the universe |
| P/E, P/B | Facts not stored; EV/EBITDA + FCF yield match this universe (interest coverage moved to Phase 1.7) |
| 13F institutional accumulation | 45-day lag, sparse on small-caps |
| Insider ownership > 10% | Needs DEF 14A; Form 4 net-buy is the substitute |
| Redis / GraphQL / FMP / Polygon | Not needed for one operator |
| LLM price targets or portfolio weights | Citation and honesty failure |
| Alpaca, scheduler, Pi host | Northstar §12 “still out” |
| Unconstrained Markowitz on trailing returns | Chases last quarter’s winners |

---

## Suggested staffing order

```text
Phase 1 warehouse ✓  (FY facts; F/Z removed)
    └─ Phase 1.5 ✓  Desk metrics on Valuation + Opportunities
          ├─ Phase 3  Book   (after the integration + operations PRs below)
          │     └─ Phase 3.5  book-aware Opportunities (ρ, sector, cash)
          │           └─ Phase 3b  min-vol only after the Book is used
          ├─ Phase 4  Form 4  ──┐
          └─ Phase 2  Gems membership (Yahoo-budget; tab waits)
                    └─ Phase 5  excerpts ─┴─ shared submissions client
                              └─ Phase 6  writer
                                    └─ Phase 7  three-zone cards
```

## Pending before the next phase (2026-10-29 review)

Operator / hygiene items found in the full review. Do these before or alongside Phase 3.

1. **Writer keys — decided 2026-10-29: leave as is.** Gemini keys invalid and `ANTHROPIC_API_KEY` empty on purpose; the operator generates the Outlook manually (`/generate-outlook-manual`) each morning and afternoon to iterate on it. Automated `generate_outlook` / `generate_memos` write template fallbacks meanwhile.
2. **Backups — deferred until prod.** Not needed while the DB is local (decided 2026-10-29). Add nightly `make dump` when it moves to a hosted / Pi environment.
3. **Unattended runs.** `launchd` plists calling the existing CLIs for the morning / close / nightly recipes in pipelines.md §4 (no in-process scheduler).
4. ~~**2027 catalysts.**~~ Done 2026-10-30: FOMC, CPI, NFP, GDP, PCE, ECB, BoE, BoJ 2027 from the official calendars. Still unpublished then: JOLTS, FOMC minutes, Beige Book, Jackson Hole, Treasury refunding; ISM's calendar needs a login. `ingest_calendar` logs `short_horizon` (series ending within 60 days) so the gaps surface on each run.
5. ~~**Writer model.**~~ Done 2026-10-29: Anthropic default `claude-sonnet-5-5` (no `temperature`, `max_tokens` 16000, refusal / truncation → template).
6. ~~**Finnhub earnings = 0.**~~ Done 2026-10-29: the unfiltered calendar is capped at 1500 rows; watchlist earnings are now fetched per symbol.
7. **Small cleanups.** `CORS_ORIGINS` parsed but unused (API hard-codes `*`); `ALPACA_*` in `.env.example` without a settings field; Polymarket month-guess slugs for non-monthly prefixes waste ~10 requests per slot.
8. **Design question.** FCF yield is in the Quality sleeve while Cheap already weighs the multiple (partial double count).
9. ~~**Ship the branch.**~~ Done 2026-10-29: PR #5 merged.

## Review after Phase 1.14 (2026-11-03)

Market-signal phases 1.10–1.14 are on `main` (PRs #17–#21; migrations through `0024_short_interest_revisions`). A full review of what is left found these gaps between the stored data and the product. The operator has not yet picked the order; the proposal is below.

**Gaps found**

1. **Outlook pack does not read 1.10–1.14.** No credit curve / implied bucket, options (`option_stats`, VIX term, Cboe put/call), Kalshi rows (`latest_odds` defaults to Polymarket), CFTC positioning, short interest or EPS revisions in `agent/pack.py`.
2. **Four pack defects from the 2026-11-02 manual Outlook run, still open:**
   - `percentile_2y` loads a 180-day window (`analytics/regime_detect.py`, `lookback = as_of - timedelta(days=180)`).
   - `_policy_read` (`analytics/outlook_judgment.py`) returns `hold_base` only by string match, so a top outcome of "increase 25 bps" gets no hike read.
   - `co_moves` / `outliers` 1d mix today's partial bars with the prior session's FRED, and bond-ETF bars look like ex-distribution drops.
   - The 72h policy window drops the FOMC statement by Monday.

   Also, `compute_dynamics` is not in the `generate-outlook-manual` refresh chain (RRG went stale 10-29).
3. **Everything runs by hand.** About 25 jobs, several time-bound:
   - `ingest_options` before 15:45 ET.
   - `ingest_kalshi` in session.
   - `ingest_cboe` after 18:00 ET.
   - `ingest_cftc` Friday after 15:30 ET.
   - `ingest_finra` twice a month.
   - `ingest_estimates` daily.

   Item 3 below (`launchd`) is still open.
4. **Coverage:**
   - APP, ABNB, BIIB and CRWV are out of the valuation universe (custom XBRL tags for capex / EBIT / debt).
   - Peers are sector + size, not business model; `config/peers.yaml` is the follow-up.
   - CRWV is not on the watchlist, so it has no options or EPS revisions. The operator holds CRWV; adding it is the operator's call.
5. **Ticker page density.** 1.10–1.14 added five panels (peers, credit curve, implied credit, options, short interest + revisions). The operator wants a simple, clear UI: one consolidation pass (order, what sits above the fold, what collapses) before adding more.
6. **Older adapters on the shared base.** New JSON vendors use `ingest/http.py` `JsonApiClient` (Kalshi, CFTC, FINRA). Polymarket and Cboe still carry their own HTTP code; migrate them in a separate PR (the operator asked for OOP on new code first).

**Superseded 2026-11-08** by "Pre-trade plan" above for items 3–4 (Book, Ticker consolidation). Item 1 (Outlook integration) is unscheduled; item 2 (`launchd`) is now a Phase 3 prerequisite.

**Proposed order (2026-11-03, kept for history)**

1. **Outlook integration:** fix the four pack defects and pack 1.10–1.14 with citations (`change-outlook-writer` skill).
2. **Operations:** `launchd` plists for morning / in-session / close / evening / Friday / FINRA recipes (CLIs only, no in-process scheduler).
3. **Phase 3 Book + 3.5 book-aware Opportunities.**
4. **Ticker page consolidation.**
5. Then 1.9 rotation panels, Phase 4 Form 4, Phase 2 Gems, Phase 5 excerpts, Phase 6 writer, Phase 7 cards.

The original order was 1.9 → Book. It moved because 1.9 adds more charts, while 1–3 make the stored data reach the Outlook and the operator's own positions.

Do not start Phase 7 until packs exist. Do not start a PR to “fix F-score for the UI.”

## Working agreements (operator, 2026-11)

- Ask before assuming. Decisions are taken one question at a time; merges only when the operator says so.
- Long-term, object-oriented code that follows industry standards: adapters subclass `JsonApiClient`, readers are classes (`KalshiLiveView`, `PositioningView`, `StreetView`), analytics expose frozen dataclasses with classmethod constructors (`RangeDistribution`, `PositioningRead`, `ShortInterestRead`, `RevisionRead`).
- UI simple and clear above everything: fewer, labeled numbers; one panel per question; footnote limits in one line.
- One PR per phase unless the operator says otherwise. Format only touched files (`ruff format <files>`); the repo has older files ruff would rewrite.
- PR bodies carry no "Generated with Claude Code" footer.

---

## Changelog

| Date | What |
|---|---|
| 2026-09-14 | Phase 0+1 warehouse on `cursor/metric-fy-quant-scores`. Tracker created. |
| 2026-09-14 | Product simplification: F-score / Altman Z out of product. Desk metrics are the read. Phase 1.5 is next; Book before Gems/optimizer/fiches. Blueprint stamped superseded. |
| 2026-09-14 | Phase 1.5: `fcf_yield`, `nd_ebitda`, `accrual` on GET /valuation and GET /opportunities; both grids. |
| 2026-10-29 | Review + hardening: Polymarket slot identity committed; no look-ahead on `?as_of=`; stored memos shown on Opportunities; Outlook contract (§10) matches v12; DB rebuilt from scratch; gold moved from FRED LBMA to GLD tape. |
| 2026-10-29 | Piotroski / Altman modules and tests removed; `compute_quant` writes legacy F/Z columns NULL. Branch renamed `feat/desk-metrics-and-review`. |
| 2026-10-31 | Phases 1.6–1.9 added after a single-name deep-dive exposed TTM / debt defects. Northstar: Ticker + Compare pages; interest coverage in scope. |
| 2026-10-31 | Phase 1.6 merged (PR #13). Phase 1.7: SIC sectors, `risk_stats`, EBIT / interest TTM, additive partial `ingest_sec`. |
| 2026-10-31 | Phase 1.7 merged (PR #14). Phase 1.8: Ticker + Compare pages and APIs; facts refreshed for non-members. |
| 2026-11-08 | Pre-trade contract: Northstar §1/§2/§3/§6/§8/§9/§11/§12/§13 + AGENTS.md. Phases 1.17 (pre-trade read), 1.18 (SBC, maturities, earnings for all), 1.19 (reverse DCF), R1 (score validation), 3 expanded (risk, stress, what-if, sizing), 3.6 (thesis triggers). |
| 2026-11-08 | Phase 1.16 PR 2: `GET /ideas` + Ideas page (Shortlist / All / Excluded) replace Valuation and Opportunities; Ticker rank-of-N counts the current run. |
| 2026-11-08 | Phase 1.16 PR 1: `ScoreGate` (four data-quality rules → `score_exclusion`), sector-neutral sleeves, 12-1 momentum as setup, SSRM → Materials. |
| 2026-11-07 | Phase 1.15 shipped on `feat/foreign-filers`. NU / DLO / VIST live; IREN and MELI CIK / TTM refreshed. Limits recorded (unranked until comparable; operator accepted). IREN sector override → Information Technology. |
| 2026-11-07 | Phase 1.15 contracted: curated foreign filers (US-listed 20-F / 6-K ADRs in USD) join B; Yahoo quarterly statements as labeled vendor TTM; `metric_ttm.net_income` / `equity`; bank read (P/E, P/B, ROE). YPF / PAM out (ARS, ADR ratio). |
| 2026-11-03 | PRs #20 and #21 merged. Review after 1.14: Outlook pack integration, four pack defects, unattended runs, coverage gaps and Ticker density recorded; proposed order integration → operations → Book → Ticker consolidation → 1.9 (pending operator decision). |
| 2026-11-03 | Phase 1.14: FINRA short interest (all stored names, 1y) + Yahoo EPS revisions on the Ticker page; targets and recommendation counts dropped by operator decision. |
| 2026-11-03 | Phase 1.12 merged (PR #19). Phase 1.13: Kalshi index ranges + Fed / recession pairs on Live, CFTC TFF positioning on Dynamics; `odds_snapshot` keyed by source + slot. |
| 2026-11-01 | Phase 1.11 merged (PR #18). Phase 1.12: options read (Yahoo chains + `option_stats`, vol indices on the tape, Cboe put/call with backfill; Ticker + Dynamics panels). |
| 2026-10-31 | Phase 1.11: equity-implied credit bucket (verified 106-name calibration set, `compute_credit`, Ticker panel). |
| 2026-10-31 | Phase 1.10: peer comps + scatter on Ticker, FRED rating curve (`GET /credit/curve`), `in_pack` flag. |
| 2026-10-31 | Phase 1.8 merged (PR #15). Market-signals contract: Phases 1.10–1.14 (peer comps, credit curve, implied credit bucket, options, Kalshi, CFTC, Cboe, consensus, short interest). Merton spike results recorded; single-name CDS and per-bond TRACE out (licensed). |
