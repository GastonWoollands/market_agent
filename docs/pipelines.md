# Pipelines

How data gets into Postgres, when to run each job, and how to serve the UI.

Product and schema live in [NORTHSTAR.md](NORTHSTAR.md). This file is the operator guide.

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
| `AGENT_PROVIDER` | `anthropic` or `gemini` (empty = auto) |

Activate `.venv` in every terminal before `python -m jobs…`.

---

## 2. When to run what

| Situation | What to run |
|-----------|-------------|
| Empty database | [First load](#3-first-load-run-in-this-order) — all steps, in order |
| Weekday morning | Tape Yahoo + FRED, then Outlook chain (news → calendar → pack → outlook) |
| During the session | Polymarket anytime; tape Yahoo for delayed quotes |
| After the close (~16:30) | Tape Yahoo daily bars, then Dynamics |
| Nightly | SEC (monthly is enough after the first zip), valuation Yahoo, valuation, scores, memos |
| After Ctrl-C on Yahoo | `--resume` on the same job |
| Before a Pi move / wipe | `pg_dump` |

Fast path once the DB is already loaded:

```bash
# morning Live + Outlook
python -m jobs.ingest_yahoo
python -m jobs.ingest_fred
python -m jobs.ingest_news
python -m jobs.ingest_calendar
python -m jobs.build_pack
python -m jobs.generate_outlook
```

---

## 3. First load (run in this order)

Each step needs the ones above it. Skip a block only if you do not care about that tab yet.

### A — Live

| # | Command | Why |
|---|---------|-----|
| 1 | `python -m jobs.seed_tape` | Instruments + `tape` / `watchlist` from `config/universes.yaml` |
| 2 | `python -m jobs.ingest_yahoo` | 5y daily bars + delayed quotes for the tape (~25 names) |
| 3 | `python -m jobs.ingest_fred` | 13 macro series (needs `FRED_API_KEY`) |
| 4 | `python -m jobs.ingest_polymarket` | Fed / inflation / recession odds |

Live tab works after this. Required tape names: **SPY**, **XLK**. Required FRED series: **DGS10**.

### B — Dynamics

| # | Command | Why |
|---|---------|-----|
| 5 | `python -m jobs.compute_dynamics` | RRG, returns, correlation from stored tape bars |

No vendor call. Re-run after a fresh Yahoo daily ingest.

### C — Outlook

| # | Command | Why |
|---|---------|-----|
| 6 | `python -m jobs.ingest_news` | Google News RSS (`config/news_queries.yaml`) |
| 7 | `python -m jobs.ingest_calendar` | YAML catalysts + Finnhub watchlist earnings |
| 8 | `python -m jobs.build_pack` | JSON evidence pack from **Postgres only** |
| 9 | `python -m jobs.generate_outlook` | Brief from that pack |

Use `--template` on step 9 to skip the LLM. Without a key, the job falls back to the template on its own.

Calendar still writes FOMC/CPI dates if Finnhub is unset; earnings just stay empty.

### D — Valuation (slow)

| # | Command | Why |
|---|---------|-----|
| 10 | `python -m jobs.ingest_sec` | SEC tickers + TTM; builds the ~700–1000 name universe |
| 11 | `python -m jobs.ingest_yahoo --universe valuation` | Daily bars for those names (≤2 req/s — long) |
| 12 | `python -m jobs.compute_valuation` | EV/EBITDA, 5y percentile, growth × re-rating |

First `ingest_sec` downloads `companyfacts.zip` into `data/sec/` (gitignored). Set `SEC_USER_AGENT` to a real email.

If Yahoo dies mid-universe:

```bash
python -m jobs.ingest_yahoo --universe valuation --resume
```

Smoke-test one name: `--tickers MSFT`.

### E — Opportunities

| # | Command | Why |
|---|---------|-----|
| 13 | `python -m jobs.compute_scores` | Rank from stored TTM + multiples + returns |
| 14 | `python -m jobs.generate_memos --template` | Pack-grounded memos for rank ≤ 20 |

Drop `--template` when an LLM key is set.

### F — Watchlist extras

| # | Command | Why |
|---|---------|-----|
| 15 | `python -m jobs.ingest_yahoo --universe watchlist` | Daily bars for seeded watchlist names |
| 16 | `python -m jobs.ingest_intraday` | 5m extended-hours for **tape ∪ watchlist** only |

Adding a ticker in the UI hydrates that name on demand. This job is the batch path.

Make equivalent of A–F:

```bash
make db migrate seed yahoo fred poly dynamics news calendar pack outlook \
  sec yahoo-val valuation scores memos yahoo-watch intraday
```

---

## 4. Recurring recipes

Intended times if you automate later. Until then, run the same commands by hand.

### Weekday morning (~07:30–07:45)

1. `python -m jobs.ingest_yahoo` — delayed tape quotes
2. `python -m jobs.ingest_fred` — 06:00 cadence
3. `python -m jobs.ingest_intraday` — pre/post 5m gaps
4. `python -m jobs.ingest_news`
5. `python -m jobs.ingest_calendar` — Finnhub ~07:00
6. `python -m jobs.build_pack`
7. `python -m jobs.generate_outlook` — ~07:45

Open Outlook: the sources table must match `/health` job rows. Hover the header status dot for latest `job_run`.

### During the session

```bash
python -m jobs.ingest_polymarket     # every 15–60 min
python -m jobs.ingest_news           # every ~30 min
python -m jobs.ingest_yahoo          # quotes when you want a fresher tape
```

### After the close (~16:30)

```bash
python -m jobs.ingest_yahoo
python -m jobs.compute_dynamics
```

### Nightly / monthly (Valuation + Opportunities)

```bash
python -m jobs.ingest_sec            # monthly after the first zip; --refresh-zip when you want a new bulk file
python -m jobs.ingest_yahoo --universe valuation --resume
python -m jobs.compute_valuation
python -m jobs.compute_scores
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

---

## 5. Job reference

| Job | Writes | Flags |
|-----|--------|-------|
| `jobs.seed_tape` | `instrument`, `universe`, `universe_member` | — |
| `jobs.ingest_yahoo` | `bar_daily`, `quote_latest` | `--universe tape\|valuation\|watchlist`, `--tickers A,B`, `--resume` |
| `jobs.ingest_fred` | `macro_series`, `macro_observation` | `--series DGS10,VIXCLS` |
| `jobs.ingest_polymarket` | `odds_snapshot` | `--slugs slug-a,slug-b` |
| `jobs.compute_dynamics` | `rrg_point`, `return_stats` | — |
| `jobs.ingest_news` | `news_item` | `--categories macro,fed` |
| `jobs.ingest_calendar` | `event_item` | `--skip-finnhub` |
| `jobs.build_pack` | `evidence_pack` | `--as-of YYYY-MM-DD` |
| `jobs.generate_outlook` | `outlook_report` | `--template`, `--as-of`, `--provider`, `--model` |
| `jobs.ingest_sec` | valuation membership, `metric_ttm` | `--refresh-zip`, `--zip PATH`, `--tickers`, `--limit` |
| `jobs.compute_valuation` | `valuation_daily` | — |
| `jobs.compute_scores` | `opportunity_score` | — |
| `jobs.generate_memos` | `opportunity_memo` | `--template`, `--provider`, `--model` |
| `jobs.ingest_intraday` | `bar_intraday` (5m) | `--tickers`, `--resume` |
| `jobs.backfill` | same as yahoo / intraday / fred | `yahoo\|intraday\|fred` plus the flags above |

Every job writes `job_run` (`running` → `ok` / `error` on Yahoo/intraday/backfill; others record on finish).

Catalogs you may edit without code:

| File | Used by |
|------|---------|
| `config/universes.yaml` | seed, Yahoo universes, valuation floor |
| `config/fred_series.yaml` | FRED ingest + Live insight templates |
| `config/polymarket_slugs.yaml` | odds (edit when a contract expires) |
| `config/news_queries.yaml` | news ingest |
| `config/catalysts.yaml` | FOMC / CPI / elections (hand-maintained) |

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
| `GET /health` | Postgres ok; latest `job_run` rows `ok` |
| Header status dot | Tooltip matches those jobs |
| Live | SPY/XLK quotes, 10Y from FRED, odds present |
| Outlook sources table | Same vendors / as_of as `/health` |
| Dynamics | Quadrants after `compute_dynamics` |
| Valuation | “N of M with a comparable multiple” is a real count |
| Opportunities | Rank #1 explainable from SQL without the memo |
| Stale badges | Show when the backing job is old or missing |

Yahoo mid-job kill: re-run with `--resume`; row counts in `bar_daily` must not grow as duplicates (same ticker+date).
