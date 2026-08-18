from datetime import date, timedelta

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from analytics.risk_on import CURVE_SERIES, RISK_ON_TICKERS, VIX_SERIES
from analytics.rrg import TRAIL_WEEKS
from api.dynamics import build_dynamics, stored_from_rows
from api.live import HISTORY_DAYS, build_live, resolve_lever, risk_on_from_store
from api.schemas import DynamicsResponse, HealthResponse, JobStatus, LiveResponse
from store.catalog import load_fred_series, load_polymarket, load_universes
from store.engine import get_db
from store.models import (
    BarDaily,
    MacroObservation,
    OddsSnapshot,
    QuoteLatest,
    ReturnStats,
    RrgPoint,
)
from store.repos import (
    closes_for_tickers,
    latest_jobs,
    latest_odds,
    latest_return_stats,
    latest_rrg_points,
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
    db: Session = Depends(get_db),
) -> DynamicsResponse | JSONResponse:
    try:
        pairs = latest_rrg_points(db, as_of)
        if not pairs:
            return DynamicsResponse(stale=True)
        ids = [instrument.id for instrument, _ in pairs]
        cutoff = as_of or max(point.as_of for _, point in pairs)
        stored = stored_from_rows(
            pairs,
            rrg_trails(db, ids, as_of=cutoff, limit=TRAIL_WEEKS + 1),
            latest_return_stats(db, cutoff),
        )
        return build_dynamics(stored, load_universes(), now=date.today())
    except Exception:
        payload = DynamicsResponse(stale=True)
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))
