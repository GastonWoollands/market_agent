from datetime import date

from api.schemas import ValuationMember, ValuationResponse
from store.models import Instrument, MetricTtm, ValuationDaily

STALE_AFTER_DAYS = 7
DEFAULT_SORT = "pctile"
SORTS: dict[str, tuple[str, bool]] = {
    "pctile": ("pctile_5y", False),
    "ev_ebitda": ("ev_ebitda", False),
    "growth": ("ebitda_growth_1y", True),
    "rerate": ("multiple_change_1y", True),
    "revenue": ("revenue", True),
    "ticker": ("ticker", False),
}


def build_valuation(
    rows: list[tuple[Instrument, MetricTtm, ValuationDaily]],
    *,
    comparable_n: int,
    comparable_m: int,
    min_revenue: float,
    as_of: date | None,
    stale: bool,
    q: str = "",
    industry: str = "",
    sort: str = DEFAULT_SORT,
    min_rev: float | None = None,
) -> ValuationResponse:
    members = [_member(instrument, metric, value) for instrument, metric, value in rows]
    industries = sorted({item.industry for item in members if item.industry})
    needle = q.strip().lower()
    visible = members
    if needle:
        visible = [
            item
            for item in visible
            if needle in item.ticker.lower() or needle in item.name.lower()
        ]
    if industry.strip():
        wanted = industry.strip()
        visible = [item for item in visible if (item.industry or "") == wanted]
    floor = min_rev if min_rev is not None else None
    if floor is not None:
        visible = [item for item in visible if (item.revenue or 0) >= floor]
    key, descending = SORTS.get(sort, SORTS[DEFAULT_SORT])
    resolved_sort = sort if sort in SORTS else DEFAULT_SORT
    visible = sorted(visible, key=lambda item: _sort_key(item, key, descending))
    return ValuationResponse(
        as_of=as_of,
        stale=stale,
        min_revenue=min_revenue,
        comparable_n=comparable_n,
        comparable_m=comparable_m,
        count=len(visible),
        q=q.strip(),
        industry=industry.strip(),
        sort=resolved_sort,
        min_rev=floor,
        industries=industries,
        members=visible,
    )


def _member(instrument: Instrument, metric: MetricTtm, value: ValuationDaily) -> ValuationMember:
    return ValuationMember(
        ticker=instrument.ticker,
        name=instrument.name,
        exchange=instrument.exchange,
        industry=instrument.industry,
        cik=instrument.cik,
        as_of=value.as_of,
        revenue=_num(metric.revenue),
        ebitda=_num(value.ebitda),
        fcf=_num(metric.fcf),
        net_debt=_num(metric.net_debt),
        ev=_num(value.ev),
        ev_ebitda=_num(value.ev_ebitda),
        pctile_5y=_num(value.pctile_5y),
        ebitda_growth_1y=_num(value.ebitda_growth_1y),
        multiple_change_1y=_num(value.multiple_change_1y),
        comparable=bool(value.comparable),
    )


def _sort_key(item: ValuationMember, attr: str, descending: bool) -> tuple[int, object]:
    value = getattr(item, attr)
    if value is None:
        return (1, "")
    if descending and isinstance(value, int | float):
        return (0, -value)
    return (0, value)


def _num(value) -> float | None:
    if value is None:
        return None
    return float(value)
