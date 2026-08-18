from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from analytics.rrg import BENCHMARK, QUADRANT_ORDER
from api.schemas import (
    DynamicsMember,
    DynamicsPoint,
    DynamicsResponse,
    DynamicsTrailPoint,
)
from store.catalog import UniversesFile, tape_with_roles
from store.models import Instrument, ReturnStats, RrgPoint

STALE_AFTER = timedelta(days=5)


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
) -> DynamicsResponse:
    by_ticker = {item.ticker: item for item in catalog.tape.instruments}
    allowed = {item.ticker for item in tape_with_roles(catalog, catalog.live.mover_roles)}
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
    stale = as_of is None or (now - as_of) > STALE_AFTER
    return DynamicsResponse(
        as_of=as_of,
        stale=stale,
        benchmark=benchmark,
        members=members,
    )
