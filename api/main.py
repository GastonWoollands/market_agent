from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.live import build_live
from api.schemas import HealthResponse, JobStatus, LiveResponse
from store.catalog import load_fred_series, load_universes
from store.engine import get_db
from store.models import BarDaily, MacroObservation, QuoteLatest
from store.repos import latest_jobs, live_macro_rows, live_tape_rows, table_count, universe_size
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
            jobs=jobs,
        )
    except Exception as exc:
        payload = HealthResponse(ok=False, database="error", database_error=str(exc))
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))


@app.get("/live", response_model=LiveResponse)
def live(db: Session = Depends(get_db)) -> LiveResponse | JSONResponse:
    try:
        return build_live(
            live_tape_rows(db),
            load_universes(),
            macro_rows=live_macro_rows(db),
            fred=load_fred_series(),
        )
    except Exception:
        payload = LiveResponse(stale=True)
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))
