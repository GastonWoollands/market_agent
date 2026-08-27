# System map

As-built orientation for Market Agent (Sector Panel). Product contract: [northstar.md](northstar.md). Job runbook: [pipelines.md](pipelines.md).

```text
config yaml  +  vendor APIs
        ↓
   ingest jobs  →  PostgreSQL  →  compute jobs  →  PostgreSQL
                                      ↓
                              evidence pack / brief
                                      ↓
                         FastAPI (read)  →  Next.js
```

Canonical examples: `ingest/yahoo/client.py`, `ingest/fred/client.py`, `jobs/ingest_yahoo.py`, `store/repos.py`, `api/live.py`, `web/lib/api.ts`, `agent/outlook.py`.

Add types + fetchers in `web/lib/api.ts` to match `api/schemas.py` before new UI. `api/` must not import `ingest`.

---

## Surfaces

| Surface | Writers | Tables | API | UI |
|---------|---------|--------|-----|----|
| Live | `seed_tape`, `ingest_yahoo`, `ingest_fred`, `ingest_polymarket` | `instrument`, `universe_member`, `bar_daily`, `quote_latest`, `macro_observation`, `odds_snapshot` | `GET /live`, `GET /health` | `web/app/page.tsx` → `LiveTape.tsx` |
| Dynamics | `compute_dynamics` | `rrg_point`, `return_stats` | `GET /dynamics` | `web/app/dynamics/page.tsx` → `DynamicsView.tsx` |
| Outlook | `ingest_news`, `ingest_calendar`, `build_pack`, `generate_outlook` | `news_item`, `event_item`, `evidence_pack`, `outlook_report` | `GET /outlook` | `web/app/outlook/page.tsx` → `OutlookView.tsx` (macro / market / near-term + snapshot) |
| Valuation | `ingest_sec`, `ingest_yahoo --universe valuation`, `compute_valuation` | `metric_ttm`, `valuation_daily`, `universe_member` (valuation) | `GET /valuation` | `web/app/valuation/page.tsx` → `ValuationView.tsx` |
| Opportunities | `compute_scores`, `generate_memos` | `opportunity_score`, `opportunity_memo` | `GET /opportunities` | `web/app/opportunities/page.tsx` → `OpportunitiesView.tsx` |
| Watchlist | `ingest_yahoo --universe watchlist`, `ingest_intraday`, `jobs/watchlist_add.py` (from `POST /watchlist`) | `universe_member` (watchlist), `quote_latest`, `bar_daily`, `bar_intraday` | `GET/POST /watchlist`, `DELETE /watchlist/{ticker}`, `GET /search` | `web/app/watchlist/page.tsx` → `WatchlistView.tsx` |

`jobs/backfill.py` re-runs Yahoo / intraday / FRED with the same upserts. Every job writes `job_run`.

Read-time (no extra tables): Risk-On in `GET /live` (`analytics/risk_on.py`); correlation / lead-lag in `GET /dynamics` (`analytics/corr.py`). Both read stored daily closes.

Analytics (no vendor I/O): `analytics/risk_on.py`, `rrg.py`, `valuation.py`, `scores.py`, `corr.py`, `returns.py`. Writer: `agent/pack.py`, `outlook.py`, `memos.py`, `citations.py`, `prompts.py`.

---

## Catalogs

Edit yaml, not code, for lists:

| File | Used by |
|------|---------|
| `config/universes.yaml` | seed, Yahoo universes, Live header, valuation floor |
| `config/fred_series.yaml` | FRED ingest + Live insight templates + Outlook pack views |
| `config/polymarket_slugs.yaml` | odds (edit when a contract expires) |
| `config/news_queries.yaml` | news ingest |
| `config/catalysts.yaml` | FOMC / CPI / PCE / NFP / GDP / JOLTS / central banks / elections |

---

## Gaps vs contract

See Northstar §12. Insider sleeve is `0.5` in `analytics/scores.py`. No scheduler, Alpaca, Form 4, or `filing` tables.
