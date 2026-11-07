# Pipelines

How data gets into Postgres, when to run each job, and how to serve the UI.

Product contract: [northstar.md](northstar.md). As-built map: [system.md](system.md). This file is the operator guide.

Jobs are the only writers of market data. The API and UI never call Yahoo, FRED, SEC, or the LLM. There is no scheduler yet — you run CLIs (or `make` targets). Times below are **America/New_York**, the intended cadence if you later wire `cron` / `launchd`.

```text
config yaml  +  vendor APIs
        ↓
   ingest jobs  →  PostgreSQL  →  compute jobs  →  PostgreSQL
                                      ↓
                              evidence pack / brief
                                      ↓
                         FastAPI (read)  →  Next.js
```

---

## 1. One-time setup

```bash
cp .env.example .env          # fill keys (table below)
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d db       # Postgres on host port 5433
alembic upgrade head
```

| Key | Needed for |
|-----|------------|
| `FRED_API_KEY` | Live macro |
| `FINNHUB_API_KEY` | Watchlist earnings on Outlook |
| `SEC_USER_AGENT` | Valuation universe (`MarketAgent you@real-email`) |
| `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` | Outlook + memos (optional; `--template` works without) |
| `AGENT_PROVIDER` | `anthropic` or `gemini` (empty = Anthropic if its key is set, else Gemini) |
| `AGENT_MODEL` | Override the provider default model (optional) |

Activate `.venv` in every terminal before `python -m jobs…`.

---

## 2. When to run what

| Situation | What to run |
|-----------|-------------|
| Empty database | [First load](#3-first-load-run-in-this-order) — all steps, in order |
| Weekday morning | Tape Yahoo + FRED + regime, then Outlook chain (news → Fed RSS → calendar → pack → outlook) |
| During the session | Polymarket and Kalshi anytime; tape Yahoo for delayed quotes; options chains before 15:45 ET |
| After the close (~16:30) | Tape Yahoo daily bars, then Dynamics; Cboe after 18:00 ET |
| Nightly | SEC refresh (weekly is enough; daily in earnings season), valuation Yahoo, valuation, quant, scores, risk, credit, estimates, memos |
| Friday after 15:30 ET | CFTC positioning |
| ~8 business days after the 15th and month-end | FINRA short interest |
| After Ctrl-C on Yahoo | `--resume` on the same job |
| Before a Pi move / wipe | `pg_dump` |

Fast path once the DB is already loaded:

```bash
# morning Live + Outlook
python -m jobs.ingest_yahoo
python -m jobs.ingest_yahoo --universe watchlist   # the default run refreshes the tape only
python -m jobs.ingest_fred
python -m jobs.compute_regime
python -m jobs.ingest_intraday      # pre/post 5m bars -> pack extended_hours
python -m jobs.ingest_polymarket
python -m jobs.ingest_news
python -m jobs.ingest_finnhub_news
python -m jobs.ingest_fed_rss
python -m jobs.ingest_calendar
python -m jobs.build_pack
python -m jobs.generate_outlook     # or the generate-outlook-manual skill
```

---

## 3. First load (run in this order)

Each step needs the ones above it. Skip a block only if you do not care about that tab yet.

### A — Live

| # | Command | Why |
|---|---------|-----|
| 1 | `python -m jobs.seed_tape` | Instruments + `tape` / `watchlist` from `config/universes.yaml` (includes US indices/ETFs + international indices: Nikkei/DAX/FTSE/HSI/CSI 300 + EEM) |
| 2 | `python -m jobs.ingest_yahoo` | 5y daily bars + delayed quotes for the tape (~40 names: US + intl indices + Treasury yield indices) |
| 3 | `python -m jobs.ingest_fred` | FRED catalog (US spine: rates/inflation/growth/employment + FX: DXY/EUR/JPY/MXN/BRL/CNY + commodities: copper/oil/gas + global: ECB/BOJ/PBOC + credit curve: ICE BofA OAS / yield AAA…CCC, Baa−10Y, NFCI, STLFSI4; needs `FRED_API_KEY`) |
| 3b | `python -m jobs.compute_regime` | `regime_snapshot` from stored FRED (Live band + `pack.regime`) |
| 4 | `python -m jobs.ingest_polymarket` | Fed / inflation / recession odds |

Live tab works after this. Required tape names: **SPY**, **XLK**, **EEM**. Required FRED series: **DGS10**, **DTWEXBGS**. Gold is the **GLD** tape quote (FRED dropped the LBMA fixing).

### B — Dynamics

| # | Command | Why |
|---|---------|-----|
| 5 | `python -m jobs.compute_dynamics` | RRG, returns, correlation from stored tape bars |

No vendor call. Re-run after a fresh Yahoo daily ingest.

### C — Outlook

| # | Command | Why |
|---|---------|-----|
| 6 | `python -m jobs.ingest_news` | Google News RSS (`config/news_queries.yaml`: rates/inflation/growth/fx/commodities/trade/treasury/corporate/energy/central banks/geopolitics) |
| 6b | `python -m jobs.ingest_finnhub_news` | Finnhub market wire (Reuters/CNBC/Bloomberg) + watchlist company news (≤5 per name), with vendor summaries; needs `FINNHUB_API_KEY` |
| 7 | `python -m jobs.ingest_fed_rss` | Fed Board RSS (statements, speeches, testimony); thin items get the official article body (capped) |
| 8 | `python -m jobs.ingest_calendar` | YAML catalysts (FOMC/CPI/PCE/NFP/GDP/JOLTS/speeches/minutes/Beige Book/ISM/Treasury/CBs) + Finnhub watchlist earnings |
| 9 | `python -m jobs.build_pack` | JSON evidence pack from **Postgres only** |
| 10 | `python -m jobs.generate_outlook` | Brief from that pack |

Use `--template` on step 10 to skip the LLM. Without a key, the job falls back to the template on its own.

Calendar still writes FOMC/CPI dates if Finnhub is unset; earnings just stay empty.

### D — Valuation (slow)

| # | Command | Why |
|---|---------|-----|
| 11 | `python -m jobs.ingest_sec --rebuild` | SEC tickers + TTM + fiscal-year snapshots; screens every listing into the ~700–1000 name universe (zip) |
| 12 | `python -m jobs.ingest_yahoo --universe valuation` | Daily bars for those names (≤2 req/s — long) |
| 13 | `python -m jobs.compute_valuation` | EV/EBITDA, 5y percentile, growth × re-rating |
| 14 | `python -m jobs.compute_quant` | Gem-candidate flag + ratio snapshot (`quant_score`). F-score / Z are not computed |
| 14a | `python -m jobs.ingest_sec_profile --resume` | Sector (SIC → `config/sic_sectors.yaml`) + SEC industry on `instrument`; ~1 SEC request per name, `--resume` skips names that have a sector |
| 14b | `python -m jobs.compute_risk` | Vol 3m/1y, downside vol, beta vs SPY/QQQ, drawdown → `risk_stats` (valuation ∪ watchlist ∪ tape) |
| 14c | `python -m jobs.compute_credit` | Merton DD from market cap, 1y vol and TTM liabilities; rating anchors from `config/credit_calibration.yaml` + FRED ICE BofA OAS → `credit_implied`, `credit_anchor` (valuation ∪ watchlist ∪ calibration names; Financials / Real Estate / captive finance excluded). Needs `ingest_sec`, `ingest_fred` (DGS1) first |

After a schema upgrade that adds `metric_fy`, backfill without rebuilding membership:

```bash
python -m jobs.ingest_sec --fy-only
python -m jobs.compute_quant
```

`--fy-only` reads the zip (add `--per-cik` to skip the 1.4 GB download when the local copy is older than 7 days) and does not move the Filings date.

`ingest_sec --rebuild` downloads `companyfacts.zip` (~1.4 GB) into `data/sec/` (gitignored) and re-downloads it when the copy is older than 7 days. Set `SEC_USER_AGENT` to a real email.

After the first load, plain `ingest_sec` refreshes stored names only (valuation ∪ watchlist) by their stored CIK from per-CIK JSON (~20 min for ~1000 names), committing every 50 names. It never changes membership: names that fall below the floor stay members, and new names never enter. Names without a CIK (ETFs, foreign filers) are listed under `meta.no_cik`, not `failures`. `--tickers` narrows the refresh to stored names; `--rebuild --tickers A,B` adds new ones. `--zip` / `--refresh-zip` / `--per-cik` need `--rebuild` or `--fy-only`. Run `--rebuild` monthly so the universe does not drift.

**Foreign filers (Phase 1.15).** Every refresh or rebuild first syncs `config/universes.yaml` `valuation.foreign_filers` (NU, DLO, VIST): each curated name is upserted with its SEC CIK and kept as a `valuation` member, and a full `--rebuild` keeps them too. The same step fills a NULL CIK for any stored valuation / watchlist name found in the SEC ticker list (`meta.cik_filled`). After the SEC pass, Yahoo quarterly statements give those names TTM points newer than their latest SEC point (`metric_ttm.source = yahoo`; four Yahoo requests per name). `meta.yahoo_skipped` lists `non_usd` / `few_quarters` names, and `meta.yahoo_warnings` lists `shares_mismatch` (Yahoo shares ÷ ADR ratio more than 10% off the SEC count). To add a foreign filer: add one line to the yaml (USD reporters only, with the right `adr_ratio`; `bank: true` for banks), then run `ingest_sec --tickers T`, `ingest_yahoo --universe valuation --tickers T`, `ingest_sec_profile --tickers T`, and the compute jobs. After the first monthly `--rebuild` with this phase, check that NU, DLO and VIST are still `valuation` members (the keep-ids union in `_write_members` has no unit test).

A full run (no `--tickers` / `--limit`, at most 5% failed fetches) records `meta.facts_as_of` — the fetch date, or the zip file's mtime (a copied old zip reads as new) — which the freshness strip shows as Filings. If the zip is older than 7 days and the download fails, the old copy is used and Filings shows its date as late.

If Yahoo dies mid-universe:

```bash
python -m jobs.ingest_yahoo --universe valuation --resume
```

Smoke-test one name: `--tickers MSFT` (adds / refreshes that name; it does not shrink the universe).

### E — Opportunities

| # | Command | Why |
|---|---------|-----|
| 15 | `python -m jobs.compute_scores` | Rank from stored TTM + multiples + returns |
| 16 | `python -m jobs.generate_memos --template` | Pack-grounded memos for rank ≤ 20 |

Drop `--template` when an LLM key is set.

### F — Watchlist extras

| # | Command | Why |
|---|---------|-----|
| 17 | `python -m jobs.ingest_yahoo --universe watchlist` | Daily bars for seeded watchlist names |
| 18 | `python -m jobs.ingest_intraday` | 5m extended-hours for **tape ∪ watchlist** only |

Adding a ticker in the UI hydrates that name on demand. This job is the batch path.

### G — Options (Phase 1.12)

| # | Command | Why |
|---|---------|-----|
| 19 | `python -m jobs.ingest_cboe --backfill` | Cboe daily put/call JSON for every stored SPY session since 2025-03-03 → `options_market_stats` (~420 files, ~7 min). Without `--backfill`: the last 10 sessions not stored |
| 20 | `python -m jobs.ingest_options` | Yahoo chains for watchlist ∪ Opportunities top 25 ∪ SPY / QQQ / IWM ∪ sector and group ETFs (~45 names, 4 monthlies each, strikes ±30% of spot) → `option_chain_snapshot` + `option_stats`. Needs `ingest_yahoo` (1y realized vol), `ingest_fred` (DGS3MO), `compute_scores` (top 25) |

The vol indices ^VIX9D / ^VIX3M / ^VVIX / ^SKEW are tape names: `seed_tape` + `ingest_yahoo` load them.

Run `ingest_options` before the close (~15:45 ET). After hours and on weekends Yahoo shows
the widened closing quotes: thin ETF chains then fall back to same-session trades and some
30d IVs come back empty. `ingest_cboe` after 18:00 ET, when Cboe publishes the day's file.

### H — Kalshi + CFTC (Phase 1.13)

| # | Command | Why |
|---|---------|-----|
| 21 | `python -m jobs.ingest_cftc --backfill` | CFTC Traders in Financial Futures (futures only) for the six contracts in `config/cftc_contracts.yaml`, three years plus a quarter → `cot_position` (~1,000 rows, seconds). Without `--backfill`: the last 8 weeks (CFTC revises) |
| 22 | `python -m jobs.ingest_kalshi` | Soonest open event per series in `config/kalshi_series.yaml` → `odds_snapshot` rows with `source = kalshi`: S&P 500 / Nasdaq-100 close ranges (median, 10–90%), Fed decision and NBER recession beside Polymarket |

Kalshi books are thin outside US hours: run `ingest_kalshi` in session, beside `ingest_polymarket`.
A contract nobody bids carries no probability; a book whose quoted mids sum below 0.8 is flagged
thin. CFTC publishes Friday 15:30 ET for Tuesday's positions.

### I — Short interest + estimate revisions (Phase 1.14)

| # | Command | Why |
|---|---------|-----|
| 23 | `python -m jobs.ingest_finra --backfill` | FINRA consolidated short interest, one year of twice-monthly settlement dates, every stored instrument → `short_interest` (~22k rows, ~2 min). Without `--backfill`: dates of the last 60 days not stored, plus the latest (FINRA revises) |
| 24 | `python -m jobs.ingest_estimates` | Yahoo `earningsTrend` (consensus EPS now / 7 / 30 / 60 / 90 days ago, analysts revising up / down) for the watchlist ∪ Opportunities top 25 → `eps_revision` (~30 s). Needs `compute_scores` (top 25) |

FINRA publishes about eight business days after each settlement (mid-month and month-end).
No price targets or buy/hold/sell counts are stored: they lag the price and read as a target.

Make equivalent of A–F:

```bash
make db migrate seed yahoo fred regime poly dynamics news fed-rss calendar pack outlook \
  sec-rebuild sec-profile yahoo-val valuation quant scores risk memos yahoo-watch intraday \
  cboe-backfill options cftc-backfill kalshi finra-backfill estimates

make yahoo yahoo-watch fred regime poly dynamics news fed-rss calendar pack outlook
```

---

## 4. Recurring recipes

Intended times if you automate later. Until then, run the same commands by hand.

### Weekday morning (~07:30–07:45)

1. `python -m jobs.ingest_yahoo` — delayed tape quotes
2. `python -m jobs.ingest_yahoo --universe watchlist` — watchlist quotes (the default run is tape only; the pack reads both)
3. `python -m jobs.ingest_fred` — 06:00 cadence
4. `python -m jobs.compute_regime` — classify macro regime from FRED
5. `python -m jobs.ingest_intraday` — pre/post 5m gaps
6. `python -m jobs.ingest_polymarket` — Fed / CPI / recession odds
7. `python -m jobs.ingest_news` and `python -m jobs.ingest_finnhub_news` (wire + watchlist company news with summaries)
8. `python -m jobs.ingest_fed_rss`
9. `python -m jobs.ingest_calendar` — Finnhub ~07:00
10. `python -m jobs.build_pack` — before 09:30 ET the pack carries `extended_hours` (pre-market gaps)
11. `python -m jobs.generate_outlook` — ~07:45 (SDK writer; provider per `AGENT_PROVIDER`), or the manual skill

Open Outlook: the sources table must match `/health` job rows. Hover the header status dot for latest `job_run`.

**Manual override (optional):** If the automated output needs better reasoning, use the coding-agent skill (Cursor or Claude Code). This is the one sanctioned exception to the writer/coder split in AGENTS.md; the citation check still gates the result:

```
# In Cursor or Claude Code
/generate-outlook-manual
```

Use manual generation when:
- High-severity anomalies detected (>0.7 severity)
- Regime classification changed
- Complex cross-asset narratives
- Testing prompt changes

### Weekday afternoon (manual Outlook, ~15:30–16:15)

Current operating mode: the operator regenerates the Outlook with the coding-agent skill.
`build_pack` stamps `session.phase` (intraday before 16:00 ET, after_close after), so run it
when you want that framing. Yahoo yield indices can lag the rest of the tape by ~1h.

```bash
python -m jobs.ingest_yahoo
python -m jobs.ingest_yahoo --universe watchlist
python -m jobs.ingest_fred
python -m jobs.compute_regime
python -m jobs.ingest_intraday      # after 16:00 ET: post-market gaps (earnings)
python -m jobs.ingest_polymarket
python -m jobs.ingest_news
python -m jobs.ingest_finnhub_news
python -m jobs.ingest_fed_rss
python -m jobs.ingest_calendar
python -m jobs.build_pack
# then /generate-outlook-manual
```

### During the session

```bash
python -m jobs.ingest_polymarket     # every 15–60 min
python -m jobs.ingest_news           # every ~30 min
python -m jobs.ingest_finnhub_news   # wire + watchlist company news (summaries)
python -m jobs.ingest_fed_rss        # every ~30 min with news
python -m jobs.ingest_yahoo          # quotes when you want a fresher tape
python -m jobs.ingest_yahoo --universe watchlist   # same for watchlist names
```

### Before the close (~15:45)

```bash
python -m jobs.ingest_options
```

### After the close (~16:30)

```bash
python -m jobs.ingest_yahoo
python -m jobs.ingest_yahoo --universe watchlist
python -m jobs.compute_dynamics
python -m jobs.ingest_cboe          # after 18:00 ET; today's file 403s before that
```

Friday after 15:30 ET (weekly positioning):

```bash
python -m jobs.ingest_cftc
```

Daily (estimates) and around the 1st / 15th + 8 business days (FINRA cycle):

```bash
python -m jobs.ingest_estimates
python -m jobs.ingest_finra
```

After a Chair speech (same stored Outlook slice; no Live-time LLM):

```bash
python -m jobs.ingest_fed_rss
python -m jobs.ingest_news
python -m jobs.ingest_finnhub_news
python -m jobs.ingest_yahoo
python -m jobs.ingest_yahoo --universe watchlist
python -m jobs.ingest_fred
python -m jobs.compute_regime
python -m jobs.ingest_polymarket
python -m jobs.build_pack
python -m jobs.generate_outlook
```

### Nightly / monthly (Valuation + Opportunities)

```bash
python -m jobs.ingest_sec            # per-CIK refresh of stored names; weekly, daily in earnings season
python -m jobs.ingest_sec --rebuild  # monthly: re-screen every listing (zip, auto-refreshed after 7 days)
python -m jobs.ingest_yahoo --universe valuation --resume
python -m jobs.compute_valuation
python -m jobs.compute_quant
python -m jobs.compute_scores
python -m jobs.ingest_sec_profile --resume   # new names only; drop --resume after editing sic_sectors.yaml
python -m jobs.compute_risk
python -m jobs.compute_credit
python -m jobs.generate_memos
```

### Kill mid-Yahoo, then continue

Already-written tickers stay in `bar_daily`. Upserts never duplicate.

```bash
python -m jobs.ingest_yahoo --resume
python -m jobs.ingest_yahoo --universe valuation --resume
python -m jobs.ingest_intraday --resume
```

Same thing via the backfill wrapper:

```bash
python -m jobs.backfill yahoo --universe tape --resume
python -m jobs.backfill yahoo --universe valuation --tickers MSFT
python -m jobs.backfill intraday --resume
python -m jobs.backfill fred --series DGS10
```

`--resume` skips names that already have rows. Omit it to re-fetch everything (still idempotent).

Timeouts and HTTP 5xx retry up to 3 times inside the adapters. **Yahoo 429 still fails fast** — stop and resume later.

### Outlook generation strategy

Two approaches: **automated (default)** and **manual override (Cursor skill)**.

#### Automated (SDK writer)

```bash
python -m jobs.generate_outlook
```

- **Model:** `AGENT_PROVIDER` / `AGENT_MODEL` from `.env`; defaults `claude-sonnet-5-5` (Anthropic) or `gemini-2.5-flash` (Gemini). Sonnet 5.5 runs without `temperature` (the API rejects non-default values) and with `max_tokens` 16000 because adaptive thinking shares the budget
- **Speed:** 5-10 seconds
- **Cost:** low per run; check the provider console
- **Use when:** Normal market day, routine updates, running unattended

Template fallback if API unavailable: `python -m jobs.generate_outlook --template`

#### Manual (coding-agent skill — current operating mode)

Cursor or Claude Code: `/generate-outlook-manual`. As of 2026-10-29 the operator runs this each morning and afternoon to iterate on the brief; the SDK writer keys are intentionally left unset/invalid.

- **Model:** whatever coding agent runs the skill; stamped as `manual/<agent-model>`
- **Speed:** 15-30 seconds (with streaming)
- **Cost:** included in the coding-agent subscription
- **Use when:**
  - High-severity anomalies (>0.7 severity)
  - Regime classification changed
  - Complex cross-asset narratives require nuance
  - Testing prompt changes before deployment
  - Gemini output was too generic

Both write to `outlook_report` table. UI displays latest for the date.

---

## 5. Job reference

| Job | Writes | Flags |
|-----|--------|-------|
| `jobs.seed_tape` | `instrument`, `universe`, `universe_member` | — |
| `jobs.ingest_yahoo` | `bar_daily`, `quote_latest` | `--universe tape\|valuation\|watchlist`, `--tickers A,B`, `--resume` |
| `jobs.ingest_fred` | `macro_series`, `macro_observation` | `--series DGS10,VIXCLS` |
| `jobs.compute_regime` | `regime_snapshot` | `--as-of YYYY-MM-DD` |
| `jobs.ingest_polymarket` | `odds_snapshot` | `--slots front_fomc,core_cpi_yoy`, `--slugs slug-a,slug-b` |
| `jobs.compute_dynamics` | `rrg_point`, `return_stats` | — |
| `jobs.ingest_news` | `news_item` | `--categories macro,fed` |
| `jobs.ingest_finnhub_news` | `news_item` (`wire`, `company`) | `--skip-company` |
| `jobs.ingest_fed_rss` | `policy_item` (RSS + capped federalreserve.gov body for recent thin items) | `--kinds speech,statement` |
| `jobs.ingest_calendar` | `event_item` | `--skip-finnhub` |
| `jobs.build_pack` | `evidence_pack` | `--as-of YYYY-MM-DD` |
| `jobs.generate_outlook` | `outlook_report` | `--template`, `--as-of`, `--provider`, `--model` |
| `jobs.ingest_sec` | `metric_ttm` (`source` sec, or yahoo for curated foreign filers), `metric_fy`; valuation membership only with `--rebuild`, plus the curated foreign filers on every run | `--rebuild`, `--refresh-zip`, `--zip PATH`, `--per-cik`, `--tickers`, `--limit`, `--fy-only` |
| `jobs.compute_valuation` | `valuation_daily` | — |
| `jobs.compute_quant` | `quant_score` (gem flag / ratios) | — |
| `jobs.compute_scores` | `opportunity_score` (prunes names outside the run) | — |
| `jobs.ingest_sec_profile` | `instrument.sector` / `instrument.industry` | `--tickers` (any stored name, also outside every universe), `--resume` |
| `jobs.compute_risk` | `risk_stats` | — |
| `jobs.compute_credit` | `credit_implied`, `credit_anchor` | — |
| `jobs.ingest_options` | `option_chain_snapshot`, `option_stats` | `--tickers` (subset of the options scope) |
| `jobs.ingest_cboe` | `options_market_stats` | `--backfill` |
| `jobs.ingest_kalshi` | `odds_snapshot` (`source = kalshi`) | — |
| `jobs.ingest_cftc` | `cot_position` | `--backfill` |
| `jobs.ingest_finra` | `short_interest` | `--backfill` |
| `jobs.ingest_estimates` | `eps_revision` | — |
| `jobs.generate_memos` | `opportunity_memo` | `--template`, `--provider`, `--model` |
| `jobs.ingest_intraday` | `bar_intraday` (5m) | `--tickers`, `--resume` |
| `jobs.backfill` | same as yahoo / intraday / fred | `yahoo\|intraday\|fred` plus the flags above |

Every job writes `job_run` (`running` → `ok` / `error` on Yahoo/intraday/backfill; others record on finish).

Catalogs you may edit without code:

| File | Used by |
|------|---------|
| `config/universes.yaml` | seed, Yahoo universes, valuation floor, gems thresholds |
| `config/fred_series.yaml` | FRED ingest + Live insight templates + Outlook pack views |
| `config/polymarket_slugs.yaml` | odds slots + match rules (ingest rotates Gamma slugs) |
| `config/news_queries.yaml` | news ingest |
| `config/catalysts.yaml` | FOMC / CPI / PCE / NFP / GDP / JOLTS / speeches / minutes / Beige Book / ISM / Treasury / CBs / elections (hand-maintained from official calendars only; `ingest_calendar` warns and records `short_horizon` when a recurring series ends within 60 days) |

---

## 6. Serve

Two terminals, venv active in the API one:

```bash
uvicorn api.main:app --reload --port 8000
npm --prefix web run dev
```

Or `make api` and `make web`. UI: `http://localhost:3000`. Health: `http://localhost:8000/health`.

---

## 7. Backup

```bash
bash scripts/pg_dump.sh
bash scripts/pg_restore.sh data/backups/market_agent_YYYYMMDDTHHMMSSZ.dump
```

Dumps are gitignored under `data/`. Restore needs `docker compose up -d db`.

---

## 8. Check it worked

| Check | Expect |
|-------|--------|
| `GET /health` | Postgres ok; latest `job_run` rows `ok`; `metric_fy` / `quant_score` counts after those jobs |
| Header status dot | Tooltip matches those jobs |
| Live | SPY/XLK quotes, 10Y from FRED, odds present |
| Outlook sources table | Same vendors / as_of as `/health` |
| Dynamics | Quadrants after `compute_dynamics` |
| Valuation | “N of M with a comparable multiple” is a real count |
| Opportunities | Rank #1 explainable from EV/EBITDA, 5y %ile, FCF yield, ND/EBITDA, EBITDA 1y, trap — without the memo and without F/Z. Accrual badge is yes/no/— |
| Quant | `GET /health` `metric_fy` / `quant_score` > 0 after `ingest_sec --fy-only` and `compute_quant`. Do not check F-score in the UI |
| Stale badges | Show when the backing job is old or missing |

Yahoo mid-job kill: re-run with `--resume`; row counts in `bar_daily` must not grow as duplicates (same ticker+date).
