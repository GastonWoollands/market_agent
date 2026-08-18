from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from analytics.corr import (
    CORR_WINDOW,
    DEFAULT_LAG,
    DEFAULT_LEAD,
    corr_matrix,
    lead_lag,
    lead_lag_note,
    peak_lag,
)
from analytics.returns import INDEX_WINDOW, relative_to_benchmark
from analytics.rrg import BENCHMARK, QUADRANT_ORDER
from api.schemas import (
    DynamicsCorr,
    DynamicsLagBar,
    DynamicsLeadLag,
    DynamicsMember,
    DynamicsOverlay,
    DynamicsPoint,
    DynamicsResponse,
    DynamicsTrailPoint,
)
from store.catalog import UniversesFile, tape_with_roles
from store.models import Instrument, ReturnStats, RrgPoint

STALE_AFTER = timedelta(days=5)
HISTORY_DAYS = 150
SECTOR_ROLE = "sector"


@dataclass(frozen=True)
class StoredMember:
    ticker: str
    name: str
    sector: str | None
    as_of: date
    rs_ratio: float
    rs_momentum: float
    quadrant: str
    trail: list[tuple[date, float, float]]
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_1y: float | None = None
    indexed: list[tuple[date, float]] | None = None


def _to_float(value: Decimal | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _indexed_from_json(raw: object) -> list[tuple[date, float]]:
    if not isinstance(raw, list):
        return []
    out: list[tuple[date, float]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        day = item.get("date")
        value = item.get("value")
        if not isinstance(day, str) or not isinstance(value, (int, float)):
            continue
        out.append((date.fromisoformat(day), float(value)))
    return out


def stored_from_rows(
    pairs: list[tuple[Instrument, RrgPoint]],
    trails: dict[int, list[RrgPoint]],
    stats: dict[int, ReturnStats],
) -> list[StoredMember]:
    members: list[StoredMember] = []
    for instrument, point in pairs:
        trail_rows = trails.get(instrument.id, [point])
        stat = stats.get(instrument.id)
        members.append(
            StoredMember(
                ticker=instrument.ticker,
                name=instrument.name,
                sector=instrument.sector,
                as_of=point.as_of,
                rs_ratio=float(point.rs_ratio),
                rs_momentum=float(point.rs_momentum),
                quadrant=point.quadrant,
                trail=[
                    (row.as_of, float(row.rs_ratio), float(row.rs_momentum))
                    for row in trail_rows
                ],
                ret_1w=float(stat.ret_1w) if stat and stat.ret_1w is not None else None,
                ret_1m=float(stat.ret_1m) if stat and stat.ret_1m is not None else None,
                ret_3m=float(stat.ret_3m) if stat and stat.ret_3m is not None else None,
                ret_1y=float(stat.ret_1y) if stat and stat.ret_1y is not None else None,
                indexed=_indexed_from_json(stat.indexed if stat else None),
            )
        )
    return members


def build_dynamics(
    stored: list[StoredMember],
    catalog: UniversesFile,
    *,
    now: date,
    benchmark: str = BENCHMARK,
    closes: Mapping[str, Sequence[tuple[date, float]]] | None = None,
    lead: str = DEFAULT_LEAD,
    lag: str = DEFAULT_LAG,
) -> DynamicsResponse:
    by_ticker = {item.ticker: item for item in catalog.tape.instruments}
    allowed = {item.ticker for item in tape_with_roles(catalog, catalog.live.mover_roles)}
    series = closes or {}
    members: list[DynamicsMember] = []
    as_of: date | None = None
    for row in stored:
        if row.ticker not in allowed:
            continue
        catalog_item = by_ticker.get(row.ticker)
        as_of = row.as_of if as_of is None or row.as_of > as_of else as_of
        members.append(
            DynamicsMember(
                ticker=row.ticker,
                name=row.name,
                role=catalog_item.role if catalog_item else None,
                sector=row.sector or (catalog_item.sector if catalog_item else None),
                quadrant=row.quadrant,
                rs_ratio=_to_float(row.rs_ratio) or 0.0,
                rs_momentum=_to_float(row.rs_momentum) or 0.0,
                trail=[
                    DynamicsTrailPoint(
                        as_of=day,
                        rs_ratio=_to_float(ratio) or 0.0,
                        rs_momentum=_to_float(mom) or 0.0,
                    )
                    for day, ratio, mom in row.trail
                ],
                ret_1w=_to_float(row.ret_1w),
                ret_1m=_to_float(row.ret_1m),
                ret_3m=_to_float(row.ret_3m),
                ret_1y=_to_float(row.ret_1y),
                indexed=[
                    DynamicsPoint(date=day, value=round(value, 4))
                    for day, value in (row.indexed or [])
                ],
            )
        )
    rank = {name: index for index, name in enumerate(QUADRANT_ORDER)}
    members.sort(key=lambda item: (rank.get(item.quadrant, 9), item.ticker))
    if as_of is None:
        as_of = _last_close_date(series)
    stale = as_of is None or (now - as_of) > STALE_AFTER
    left, right = _resolve_pair(allowed, lead, lag)
    return DynamicsResponse(
        as_of=as_of,
        stale=stale,
        benchmark=benchmark,
        members=members,
        overlay=_overlay(catalog, series, benchmark),
        corr=_corr(catalog, series),
        lead_lag=_lead_lag(series, left, right),
    )


def _last_close_date(series: Mapping[str, Sequence[tuple[date, float]]]) -> date | None:
    latest: date | None = None
    for rows in series.values():
        if not rows:
            continue
        day = rows[-1][0]
        if latest is None or day > latest:
            latest = day
    return latest


def _points(rows: Sequence[tuple[date, float]]) -> list[DynamicsPoint]:
    return [DynamicsPoint(date=day, value=round(value, 4)) for day, value in rows]


def _resolve_pair(allowed: set[str], lead: str, lag: str) -> tuple[str, str]:
    left = lead.upper()
    right = lag.upper()
    if left not in allowed:
        left = DEFAULT_LEAD
    if right not in allowed:
        right = DEFAULT_LAG
    return left, right


def _overlay(
    catalog: UniversesFile,
    series: Mapping[str, Sequence[tuple[date, float]]],
    benchmark: str,
) -> list[DynamicsOverlay]:
    bench = series.get(benchmark, [])
    if not bench:
        return []
    out: list[DynamicsOverlay] = []
    for item in tape_with_roles(catalog, [SECTOR_ROLE]):
        points = relative_to_benchmark(series.get(item.ticker, []), bench, window=INDEX_WINDOW)
        if len(points) < 2:
            continue
        out.append(DynamicsOverlay(ticker=item.ticker, name=item.name, points=_points(points)))
    return out


def _corr(
    catalog: UniversesFile,
    series: Mapping[str, Sequence[tuple[date, float]]],
) -> DynamicsCorr | None:
    tickers = [item.ticker for item in tape_with_roles(catalog, [SECTOR_ROLE])]
    if not tickers or not series:
        return None
    matrix = corr_matrix(series, tickers)
    if all(cell is None for row in matrix for cell in row):
        return None
    rounded = [
        [None if cell is None else round(cell, 4) for cell in row] for row in matrix
    ]
    return DynamicsCorr(window=CORR_WINDOW, tickers=tickers, matrix=rounded)


def _lead_lag(
    series: Mapping[str, Sequence[tuple[date, float]]],
    left: str,
    right: str,
) -> DynamicsLeadLag | None:
    left_rows = series.get(left, [])
    right_rows = series.get(right, [])
    if not left_rows or not right_rows:
        return None
    bars = lead_lag(series.get(left, []), series.get(right, []))
    chosen = peak_lag(bars)
    return DynamicsLeadLag(
        left=left,
        right=right,
        peak_lag=chosen,
        note=lead_lag_note(left, right, chosen),
        bars=[
            DynamicsLagBar(lag=lag, corr=None if corr is None else round(corr, 4))
            for lag, corr in bars
        ],
    )
