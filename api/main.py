from datetime import UTC, date, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Response
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
from api.opportunities import DEFAULT_SORT as OPP_SORT
from api.opportunities import STALE_AFTER_DAYS as OPP_STALE
from api.opportunities import build_opportunities
from api.outlook import outlook_from_store
from api.schemas import (
    DynamicsResponse,
    HealthResponse,
    JobStatus,
    LiveResponse,
    OpportunityResponse,
    OutlookResponse,
    SearchHit,
    SearchResponse,
    ValuationResponse,
    WatchlistAdd,
    WatchlistResponse,
)
from api.valuation import DEFAULT_SORT, STALE_AFTER_DAYS, build_valuation
from api.watchlist import build_watchlist
from store.catalog import load_fred_series, load_polymarket, load_universes, tape_with_roles
from store.engine import get_db
from store.models import (
    BarDaily,
    BarIntraday,
    EventItem,
    EvidencePack,
    MacroObservation,
    MetricTtm,
    NewsItem,
    OddsSnapshot,
    OpportunityMemoRow,
    OpportunityScore,
    OutlookReport,
    QuoteLatest,
    ReturnStats,
    RrgPoint,
    ValuationDaily,
)
from store.repos import (
    closes_for_tickers,
    comparable_valuation_counts,
    drop_membership,
    instrument_by_ticker,
    intraday_closes_for_tickers,
    latest_jobs,
    latest_odds,
    latest_opportunity_rows,
    latest_return_stats,
    latest_rrg_points,
    latest_valuation_rows,
    live_macro_rows,
    live_tape_rows,
    macro_observations,
    rrg_trails,
    search_instruments,
    table_count,
    universe_by_name,
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
            opportunity_scores=table_count(db, OpportunityScore),
            opportunity_memos=table_count(db, OpportunityMemoRow),
            intraday_bars=table_count(db, BarIntraday),
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


@app.get("/opportunities", response_model=OpportunityResponse)
def opportunities(
    sort: str = OPP_SORT,
    as_of: date | None = None,
    db: Session = Depends(get_db),
) -> OpportunityResponse | JSONResponse:
    try:
        rows = latest_opportunity_rows(db, as_of=as_of)
        as_of_value = max((score.as_of for _, score, _, _ in rows), default=None)
        stale = not rows
        job = next((item for item in latest_jobs(db) if item.job_name == "compute_scores"), None)
        if job is None or job.status != "ok":
            stale = True
        elif job.finished_at is not None:
            clock = datetime.now(job.finished_at.tzinfo)
            if (clock - job.finished_at).days > OPP_STALE:
                stale = True
        return build_opportunities(rows, as_of=as_of_value, stale=stale, sort=sort)
    except Exception:
        payload = OpportunityResponse(stale=True)
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))


SPARK_DAYS = 120
INTRA_DAYS = 5


def _watchlist_from_db(db: Session, selected: str | None = None) -> WatchlistResponse:
    rows = live_tape_rows(db, "watchlist")
    tickers = [row.ticker for row in rows]
    start = date.today() - timedelta(days=SPARK_DAYS)
    since = datetime.now(UTC) - timedelta(days=INTRA_DAYS)
    return build_watchlist(
        rows,
        sparklines=closes_for_tickers(db, tickers, start=start),
        intraday=intraday_closes_for_tickers(db, tickers, since=since),
        selected=selected,
    )


@app.get("/watchlist", response_model=WatchlistResponse)
def watchlist(
    ticker: str | None = None,
    db: Session = Depends(get_db),
) -> WatchlistResponse | JSONResponse:
    try:
        return _watchlist_from_db(db, ticker)
    except Exception:
        payload = WatchlistResponse(stale=True)
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))


@app.post("/watchlist", response_model=WatchlistResponse)
def watchlist_add(
    body: WatchlistAdd,
    db: Session = Depends(get_db),
) -> WatchlistResponse:
    from jobs.watchlist_add import add_watchlist_ticker
    from store.tickers import TickerError

    try:
        added = add_watchlist_ticker(body.ticker)
    except TickerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.expire_all()
    return _watchlist_from_db(db, added)


@app.delete("/watchlist/{ticker}", status_code=204)
def watchlist_remove(ticker: str, db: Session = Depends(get_db)) -> Response:
    from store.tickers import TickerError, normalize_us_ticker

    try:
        symbol = normalize_us_ticker(ticker)
    except TickerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    universe = universe_by_name(db, "watchlist")
    instrument = instrument_by_ticker(db, symbol)
    if universe is None or instrument is None:
        raise HTTPException(status_code=404, detail=f"{symbol} is not on the watchlist")
    if not drop_membership(db, universe.id, instrument.id):
        raise HTTPException(status_code=404, detail=f"{symbol} is not on the watchlist")
    db.commit()
    return Response(status_code=204)


@app.get("/search", response_model=SearchResponse)
def search(q: str = "", db: Session = Depends(get_db)) -> SearchResponse:
    hits = search_instruments(db, q)
    return SearchResponse(
        q=q,
        hits=[
            SearchHit(
                ticker=item.ticker,
                name=item.name,
                exchange=item.exchange,
                asset_class=item.asset_class,
            )
            for item in hits
        ],
    )
