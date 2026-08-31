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
| Live | `seed_tape`, `ingest_yahoo`, `ingest_fred`, `ingest_polymarket`, `compute_regime` (read-time: calendar + stored outlook slice + drivers + regime + net liquidity + anomalies) | `instrument`, `universe_member`, `bar_daily`, `quote_latest`, `macro_observation`, `odds_snapshot`, `event_item`, `outlook_report`, `regime_snapshot` | `GET /live`, `GET /health` | `web/app/page.tsx` → `LiveTape.tsx` |
| Dynamics | `compute_dynamics` | `rrg_point`, `return_stats` | `GET /dynamics` | `web/app/dynamics/page.tsx` → `DynamicsView.tsx` |
| Outlook | `ingest_news`, `ingest_fed_rss`, `ingest_calendar`, `build_pack`, `generate_outlook` (automated: Gemini) or Cursor skill (manual: Claude) | `news_item`, `event_item`, `policy_item`, `evidence_pack`, `outlook_report` | `GET /outlook` | `web/app/outlook/page.tsx` → `OutlookView.tsx` (macro / market / near-term + snapshot) |
| Valuation | `ingest_sec`, `ingest_yahoo --universe valuation`, `compute_valuation` | `metric_ttm`, `valuation_daily`, `universe_member` (valuation) | `GET /valuation` | `web/app/valuation/page.tsx` → `ValuationView.tsx` |
| Opportunities | `compute_scores`, `generate_memos` | `opportunity_score`, `opportunity_memo` | `GET /opportunities` | `web/app/opportunities/page.tsx` → `OpportunitiesView.tsx` |
| Watchlist | `ingest_yahoo --universe watchlist`, `ingest_intraday`, `jobs/watchlist_add.py` (from `POST /watchlist`) | `universe_member` (watchlist), `quote_latest`, `bar_daily`, `bar_intraday` | `GET/POST /watchlist`, `DELETE /watchlist/{ticker}`, `GET /search` | `web/app/watchlist/page.tsx` → `WatchlistView.tsx` |

`jobs/backfill.py` re-runs Yahoo / intraday / FRED with the same upserts. Every job writes `job_run`.

Read-time (no extra tables): Risk-On and outliers/co-moves in `GET /live` (`analytics/risk_on.py`, `analytics/drivers.py`); correlation / lead-lag in `GET /dynamics` (`analytics/corr.py`). All read stored daily closes / FRED. Live also mounts today’s `event_item` rows and the stored Outlook `headline` / `live_md` / `expect`. Live additionally surfaces the latest stored `regime_snapshot`, read-time net liquidity (`analytics/macro_pack.compute_net_liquidity`), read-time anomalies (`analytics/anomaly_detect.py`), and the international `intl_section` tape quotes (`config/universes.yaml` → `live.intl_section`).

Analytics (no vendor I/O): `analytics/risk_on.py`, `rrg.py`, `valuation.py`, `scores.py`, `corr.py`, `returns.py`, `drivers.py`. Writer: `agent/pack.py`, `outlook.py`, `memos.py`, `citations.py`, `prompts.py`.

---

## Catalogs

Edit yaml, not code, for lists:

| File | Used by |
|------|---------|
| `config/universes.yaml` | seed, Yahoo universes, Live header, valuation floor |
| `config/fred_series.yaml` | FRED ingest + Live insight templates + Outlook pack views |
| `config/polymarket_slugs.yaml` | odds (edit when a contract expires) |
| `config/news_queries.yaml` | news ingest |
| `config/catalysts.yaml` | FOMC / CPI / PCE / NFP / GDP / JOLTS / speeches / minutes / Beige Book / ISM / Treasury / central banks / elections |

---

## Gaps vs contract

See Northstar §12. Insider sleeve is `0.5` in `analytics/scores.py`. No scheduler, Alpaca, Form 4, or `filing` tables.
