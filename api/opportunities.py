from datetime import date
from typing import Any

from analytics.desk import accrual_from_fy, fcf_yield, nd_ebitda
from api.schemas import OpportunityMember, OpportunityMemo, OpportunityResponse
from store.models import Instrument, OpportunityMemoRow, OpportunityScore, ValuationDaily

STALE_AFTER_DAYS = 7
DEFAULT_SORT = "rank"
SORTS: dict[str, tuple[str, bool]] = {
    "rank": ("rank", False),
    "ticker": ("ticker", False),
    "ev_ebitda": ("ev_ebitda", False),
    "pctile": ("pctile_5y", False),
    "fcf_yield": ("fcf_yield", True),
    "nd_ebitda": ("nd_ebitda", False),
    "growth": ("ebitda_growth_1y", True),
}


def build_opportunities(
    rows: list[tuple[Instrument, OpportunityScore, ValuationDaily, OpportunityMemoRow | None]],
    *,
    as_of: date | None,
    stale: bool,
    sort: str = DEFAULT_SORT,
    ttm_by_id: dict[int, Any] | None = None,
    fy_by_id: dict[int, Any] | None = None,
) -> OpportunityResponse:
    ttm_map = ttm_by_id or {}
    fy_map = fy_by_id or {}
    members = [
        _member(
            instrument,
            score,
            value,
            memo,
            ttm=ttm_map.get(getattr(instrument, "id", None)),
            fy=fy_map.get(getattr(instrument, "id", None)),
        )
        for instrument, score, value, memo in rows
    ]
    key, descending = SORTS.get(sort, SORTS[DEFAULT_SORT])
    resolved = sort if sort in SORTS else DEFAULT_SORT
    members = sorted(members, key=lambda item: _sort_key(item, key, descending))
    return OpportunityResponse(
        as_of=as_of,
        stale=stale,
        count=len(members),
        sort=resolved,
        members=members,
    )


def _member(
    instrument: Instrument,
    score: OpportunityScore,
    value: ValuationDaily,
    memo: OpportunityMemoRow | None,
    *,
    ttm: Any | None = None,
    fy: Any | None = None,
) -> OpportunityMember:
    fcf = None if ttm is None else getattr(ttm, "fcf", None)
    net_debt = None if ttm is None else getattr(ttm, "net_debt", None)
    ev = getattr(value, "ev", None)
    ebitda = getattr(value, "ebitda", None)
    return OpportunityMember(
        ticker=instrument.ticker,
        name=instrument.name,
        rank=score.rank,
        total=_num(score.total) or 0.0,
        cheap=_num(score.cheap) or 0.0,
        quality=_num(score.quality) or 0.0,
        change=_num(score.change) or 0.0,
        setup=_num(score.setup) or 0.0,
        insider=_num(score.insider) or 0.0,
        risk=_num(score.risk) or 0.0,
        trap=bool(score.trap),
        pctile_5y=_num(value.pctile_5y),
        ev_ebitda=_num(value.ev_ebitda),
        ebitda_growth_1y=_num(value.ebitda_growth_1y),
        fcf_margin=_num(score.fcf_margin),
        fcf_yield=fcf_yield(fcf, ev),
        nd_ebitda=nd_ebitda(net_debt, ebitda),
        accrual=accrual_from_fy(fy),
        ret_3m=_num(score.ret_3m),
        memo=None
        if memo is None
        else OpportunityMemo(
            why_scored=memo.why_scored,
            what_10q_changed=memo.what_10q_changed,
            invalidation=memo.invalidation,
            caveats=memo.caveats,
            model=memo.model,
            status=memo.status,
        ),
    )


def _sort_key(item: OpportunityMember, attr: str, descending: bool) -> tuple[int, object]:
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
