from datetime import date

from api.schemas import ValuationMember, ValuationResponse
from store.models import Instrument, MetricTtm

STALE_AFTER_DAYS = 40


def build_valuation(
    rows: list[tuple[Instrument, MetricTtm]],
    *,
    min_revenue: float,
    as_of: date | None,
    stale: bool,
) -> ValuationResponse:
    members = [
        ValuationMember(
            ticker=instrument.ticker,
            name=instrument.name,
            exchange=instrument.exchange,
            cik=instrument.cik,
            as_of=metric.as_of,
            revenue=_num(metric.revenue),
            ebitda=_num(metric.ebitda),
            fcf=_num(metric.fcf),
            net_debt=_num(metric.net_debt),
        )
        for instrument, metric in rows
    ]
    return ValuationResponse(
        as_of=as_of,
        stale=stale,
        min_revenue=min_revenue,
        count=len(members),
        members=members,
    )


def _num(value) -> float | None:
    if value is None:
        return None
    return float(value)
