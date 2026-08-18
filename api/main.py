from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from analytics.corr import DEFAULT_LAG, DEFAULT_LEAD
from analytics.risk_on import CURVE_SERIES, RISK_ON_TICKERS, VIX_SERIES
from analytics.rrg import BENCHMARK, TRAIL_WEEKS
from api.dynamics import HISTORY_DAYS as DYNAMICS_LOOKBACK
from api.dynamics import build_dynamics, stored_from_rows
from api.live import HISTORY_DAYS, build_live, resolve_lever, risk_on_from_store
from api.outlook import outlook_from_store
from api.schemas import (
    DynamicsResponse,
    HealthResponse,
    JobStatus,
    LiveResponse,
    OutlookResponse,
    ValuationResponse,
)
from api.valuation import DEFAULT_SORT, STALE_AFTER_DAYS, build_valuation
from store.catalog import load_fred_series, load_polymarket, load_universes, tape_with_roles
from store.engine import get_db
from store.models import (
    BarDaily,
    EventItem,
    EvidencePack,
    MacroObservation,
    MetricTtm,
    NewsItem,
    OddsSnapshot,
    OutlookReport,
    QuoteLatest,
    ReturnStats,
    RrgPoint,
    ValuationDaily,
)
from store.repos import (
    closes_for_tickers,
    comparable_valuation_counts,
    latest_jobs,
    latest_odds,
    latest_return_stats,
    latest_rrg_points,
    latest_valuation_rows,
    live_macro_rows,
    live_tape_rows,
    macro_observations,
    rrg_trails,
    table_count,
    universe_size,
)
from store.settings import settings

app = FastAPI(title="Market Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse | JSONResponse:
    try:
        db.execute(text("SELECT 1"))
        jobs = [
            JobStatus(
                job_name=row.job_name,
                status=row.status,
                started_at=row.started_at,
                finished_at=row.finished_at,
                rows_written=row.rows_written,
                error=row.error,
            )
            for row in latest_jobs(db)
        ]
        return HealthResponse(
            ok=True,
            database="ok",
            tape_instruments=universe_size(db, "tape"),
            watchlist_instruments=universe_size(db, "watchlist"),
            daily_bars=table_count(db, BarDaily),
            quotes=table_count(db, QuoteLatest),
            macro_observations=table_count(db, MacroObservation),
            odds_snapshots=table_count(db, OddsSnapshot),
            rrg_points=table_count(db, RrgPoint),
            return_stats=table_count(db, ReturnStats),
            news_items=table_count(db, NewsItem),
            event_items=table_count(db, EventItem),
            evidence_packs=table_count(db, EvidencePack),
            outlook_reports=table_count(db, OutlookReport),
            valuation_instruments=universe_size(db, "valuation"),
            metric_ttm=table_count(db, MetricTtm),
            valuation_daily=table_count(db, ValuationDaily),
            jobs=jobs,
        )
    except Exception as exc:
        payload = HealthResponse(ok=False, database="error", database_error=str(exc))
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))


@app.get("/live", response_model=LiveResponse)
def live(lever: str = "DGS10", db: Session = Depends(get_db)) -> LiveResponse | JSONResponse:
    try:
        fred = load_fred_series()
        chosen = resolve_lever(lever, fred)
        start = date.today() - timedelta(days=HISTORY_DAYS)
        tape_rows = live_tape_rows(db)
        return build_live(
            tape_rows,
            load_universes(),
            macro_rows=live_macro_rows(db),
            fred=fred,
            lever=chosen,
            history=macro_observations(db, chosen, start=start),
            risk_on=risk_on_from_store(
                closes_for_tickers(db, RISK_ON_TICKERS, start=start),
                macro_observations(db, VIX_SERIES, start=start),
                macro_observations(db, CURVE_SERIES, start=start),
                now=date.today(),
            ),
            odds_rows=latest_odds(db),
            polymarket=load_polymarket(),
        )
    except Exception:
        payload = LiveResponse(stale=True)
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))


@app.get("/dynamics", response_model=DynamicsResponse)
def dynamics(
    as_of: date | None = None,
    lead: str = DEFAULT_LEAD,
    lag: str = DEFAULT_LAG,
    db: Session = Depends(get_db),
) -> DynamicsResponse | JSONResponse:
    try:
        catalog = load_universes()
        pairs = latest_rrg_points(db, as_of)
        stored = []
        if pairs:
            ids = [instrument.id for instrument, _ in pairs]
            cutoff = as_of or max(point.as_of for _, point in pairs)
            stored = stored_from_rows(
                pairs,
                rrg_trails(db, ids, as_of=cutoff, limit=TRAIL_WEEKS + 1),
                latest_return_stats(db, cutoff),
            )
        names = [
            BENCHMARK,
            *[item.ticker for item in tape_with_roles(catalog, catalog.live.mover_roles)],
        ]
        start = (as_of or date.today()) - timedelta(days=DYNAMICS_LOOKBACK)
        raw = closes_for_tickers(db, names, start=start)
        closes: dict[str, list[tuple[date, float]]] = {}
        for ticker, rows in raw.items():
            points = [(day, float(value)) for day, value in rows]
            if as_of is not None:
                points = [item for item in points if item[0] <= as_of]
            closes[ticker] = points
        return build_dynamics(
            stored,
            catalog,
            now=date.today(),
            closes=closes,
            lead=lead,
            lag=lag,
        )
    except Exception:
        payload = DynamicsResponse(stale=True)
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))


@app.get("/outlook", response_model=OutlookResponse)
def outlook(
    as_of: date | None = None,
    db: Session = Depends(get_db),
) -> OutlookResponse | JSONResponse:
    try:
        return outlook_from_store(db, as_of=as_of)
    except Exception:
        payload = OutlookResponse(stale=True)
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))


@app.get("/valuation", response_model=ValuationResponse)
def valuation(
    q: str = "",
    industry: str = "",
    sort: str = DEFAULT_SORT,
    min_rev: float | None = None,
    db: Session = Depends(get_db),
) -> ValuationResponse | JSONResponse:
    try:
        catalog = load_universes()
        rows = latest_valuation_rows(db)
        comparable_n, comparable_m = comparable_valuation_counts(db)
        as_of = max((value.as_of for _, _, value in rows), default=None)
        stale = not rows
        job = next((item for item in latest_jobs(db) if item.job_name == "compute_valuation"), None)
        if job is None or job.status != "ok":
            stale = True
        elif job.finished_at is not None:
            clock = datetime.now(job.finished_at.tzinfo)
            if (clock - job.finished_at).days > STALE_AFTER_DAYS:
                stale = True
        return build_valuation(
            rows,
            comparable_n=comparable_n,
            comparable_m=comparable_m,
            min_revenue=float(catalog.valuation.min_revenue_usd),
            as_of=as_of,
            stale=stale,
            q=q,
            industry=industry,
            sort=sort,
            min_rev=min_rev,
        )
    except Exception:
        payload = ValuationResponse(stale=True)
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))
