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
- Jobs write market data. API is read-only except watchlist (later: Book CRUD).
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
| 1.7 | Sector + per-name risk | **Done** (branch `feat/sector-risk`) | SIC → sector from SEC submissions; vol / beta / max DD for the valuation universe; `InterestExpense` |
| 1.8 | Ticker + Compare pages | Not started | Northstar §3 rows added 2026-10-31 |
| 1.9 | Rotation panels | Not started | Cross-asset RRG, sector breadth + median valuation, intra-sector RRG, factor ETFs |
| 2 | Gems universe D | Not started | Flag only on B; membership + Yahoo gems later. No F-score gate |
| 3 | Book (portfolio CRUD + current risk) | Not started | Watchlist stays unsized. After 1.5 for user value |
| 3b | Constrained rebalance plan | Not started | After the Book is used; holdings-only min-vol first |
| 4 | Form 4 + insider sleeve | Not started | Until then, omit the insider column (do not show 0.5) |
| 5 | 10-K / 10-Q excerpts | Not started | Item 1A / Item 7 only; memo 10-Q stays `unavailable` |
| 6 | Recommendation writer | Not started | Pack desk metrics + citation gate; Python fills snapshot |
| 7 | Three-zone cards + Gems tab | Not started | Schema/`api.ts` before components. No F/Z drawer |

Last tracker update: 2026-10-31.

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

## Phase 1.6 — SEC TTM data quality (done, PR pending)

**Why:** a CRWV deep-dive (2026-10-31) found the stored TTM wrong for most of the universe.

- Cash-flow concepts in 10-Qs are year-to-date. `_flow_ttm` only accepted 60–120 day spans, so CFO / capex / D&A fell back to the last annual: latest FCF equalled the prior quarter's for 755 / 933 names.
- 10-Ks rarely tag a discrete Q4. `_last_quarters` skipped the gap and summed an older quarter (CRWV revenue TTM 7.23B vs ~7.59B). No December TTM rows were written.
- EBITDA mixed TTM EBIT with an annual D&A; components were never checked for the same period end.
- `DEBT_CONCEPTS` summed `LongTermDebt` **and** its current / noncurrent parts (double count), from unbounded-stale instants.
- `MIN_COMPARABLE_OBS = 252` let a 1.5-year-old listing score Cheap 0.90.

**Do:** derive discrete quarters from YTD differences (Q2 = 6M − 3M, Q3 = 9M − 6M, Q4 = FY − 9M), require four contiguous quarters, null any component whose period end differs from revenue's, debt = `LongTermDebt` else current + noncurrent, plus short-term borrowings, instants within 45 days. Store `cfo` and `capex` on `metric_ttm`. Comparable needs ≥ 750 sessions (Cheap falls back to neutral). Replace each name's TTM history on ingest so stale rows do not survive. Fixture tests; re-run `ingest_sec` → `compute_valuation` → `compute_quant` → `compute_scores`.

Found while re-running: filers switch synonym tags between 10-Q and 10-K (capex, D&A, debt), so quarters merge synonyms in priority order with a per-concept fallback; debt reads lease-inclusive / convertible / senior-note tags; a balance sheet with no debt line for 400 days is debt-free (0), a filer that moved debt to custom tags stays unknown (CRWV Q2 2026). The old code silently used years-stale instants and annuals for all of these. `ingest_sec` now raises the 700–1000 band inside the write transaction (it used to commit first). `compute_scores` prunes scores for names outside the run, so dropped names no longer surface with old ranks.

**Result (2026-10-31, same Aug-18 zip):** 973 members (was 933); 860 ranked. Repeated latest FCF 755 → 1. Median rank move 99 places; 11 of the old top 25 remain. Out: names without a current standard capex / EBIT tag (e.g. APP, ABNB, BIIB) and CRWV (debt on custom tags) — candidates for a concept-coverage follow-up, not a fallback to stale data.

**Operator check:** CRWV TTM revenue at 2026-06-30 = 7.590B, a 2025-12-31 row exists, FCF differs quarter to quarter; `opportunity_score` has one row per ranked name.

## Phase 1.7 — Sector + per-name risk (done)

- `jobs.ingest_sec_profile`: SEC submissions `sic` → `config/sic_sectors.yaml` (ranges, first match wins, ticker overrides for SIC 7389 / travel / internet media) → `instrument.sector`; `industry` = `sicDescription`. Approximate GICS, not GICS. `upsert_instrument` now coalesces sector/industry so catalog upserts keep it.
- `risk_stats` + `jobs.compute_risk`: vol 3m / 1y, downside vol, beta vs SPY and QQQ, corr vs SPY, max drawdown 1y, drawdown from 1y high, from `adj_c` (valuation ∪ watchlist ∪ tape).
- `metric_ttm.ebit` / `interest_expense` (migration 0020). `analytics/desk.py`: `interest_coverage`, `share_change` (dilution), `financing_gap` ((capex − CFO) / market cap). Served from Phase 1.8.
- Fix: `ingest_sec --tickers/--limit` replaced the whole valuation membership with the subset; partial runs are now additive.

**Result (2026-10-31):** sector on 973 / 973 (0 unmapped); interest expense on 666 / 973; `risk_stats` 998 names. Names outside the universe (e.g. CRWV) get risk only once they are on the watchlist or tape.

**Operator check:** `select sector, count(*)` over the valuation universe has 11 sectors and no NULLs; MSFT coverage ≈ 50x, KODK < 1x.

## Phase 1.8 — Ticker + Compare pages

Northstar §3. API schema first, then `web/lib/api.ts`, then pages. Desk language only — no F/Z.

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

## Phase 3 — Book

**Goal:** One operator-sized book (shares, average cost, cash). Watchlist remains the unsized tracker. This is the step that turns the terminal into a decision layer.

**Do**

1. Northstar §3 / §8 / §11 / §12: Book tables and CRUD.
2. `portfolio` (singleton cash) + `portfolio_holding` (`instrument_id`, shares, average_cost). No `user_id` UUID.
3. API: `GET/PUT /portfolio`, holdings CRUD. Adding a name hydrates like `POST /watchlist` (job helper, no vendor in the route).
4. `jobs.compute_portfolio`: delayed MV, weight, unrealized P&L, sector stack, current vol, Sharpe (FRED T-bill RF or **null** — do not fake RF). Persist `portfolio_snapshot` JSONB.
5. Book tab: holdings, weights, sectors, cash, ND/EBITDA of the book if computable, snapshot Sharpe/vol. Dense terminal, `StaleBadge`. No blotter.

**Depends on:** Phase 0. Ship **after 1.5**. Can run in parallel with Phase 2.

### Phase 3.5 — Book-aware Opportunities (no optimizer)

**Goal:** “What happens if I add this name?” without a solver.

For each Opportunities row when the book is non-empty: ρ vs current holdings, sector overlap, cash used at a stated add (e.g. 2% of NAV). Hide these fields when cash is the only holding (Path B). Rank continuously; no magic ΔSharpe cut.

**Depends on:** Phase 3 + 1.5.

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

## Explicitly deferred

| Item | Why |
|---|---|
| Piotroski F-Score / Altman Z as UI, rank, or pack | Opaque composites; desk metrics replace them |
| LLM “moat” / fit-percentage gauges | Second opaque rank |
| Entry / target / stop on the card | Read as advice even when Python-filled |
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
          ├─ Phase 3  Book   ← next
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

Next concrete PR: **Phase 1.8 Ticker + Compare pages**, then 1.9, then **Phase 3 Book** (with 3.5 as the rotation read). Gems membership can parallel Book. Do not start Phase 7 until packs exist. Do not start a PR to “fix F-score for the UI.”

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
