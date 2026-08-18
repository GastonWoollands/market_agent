from datetime import date

from api.schemas import OpportunityMember, OpportunityMemo, OpportunityResponse
from store.models import Instrument, OpportunityMemoRow, OpportunityScore, ValuationDaily

STALE_AFTER_DAYS = 7
DEFAULT_SORT = "rank"
SORTS: dict[str, tuple[str, bool]] = {
    "rank": ("rank", False),
    "total": ("total", True),
    "cheap": ("cheap", True),
    "quality": ("quality", True),
    "change": ("change", True),
    "setup": ("setup", True),
}


def build_opportunities(
    rows: list[
        tuple[Instrument, OpportunityScore, ValuationDaily, OpportunityMemoRow | None]
    ],
    *,
    as_of: date | None,
    stale: bool,
    sort: str = DEFAULT_SORT,
) -> OpportunityResponse:
    members = [_member(*row) for row in rows]
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
) -> OpportunityMember:
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
