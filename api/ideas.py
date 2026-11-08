"""Ideas: the valuation universe with its score, its data-quality exclusions, and a shortlist.

One read replaces the old Valuation and Opportunities grids. Every valuation member appears
once with a status: `ranked` (has a score this run), `excluded` (comparable but failed a
`ScoreGate` rule; the reasons are shown, never a rank), or `no_score` (not comparable: the
EV/EBITDA history is too short for a 5y percentile). Sorting and filtering happen in the
browser; the universe is ~1k rows.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from statistics import median
from typing import Any

from analytics.desk import accrual_from_fy, fcf_yield, nd_ebitda
from analytics.scores import (
    FCF_JUMP_SHARE,
    FCF_YIELD_MAX,
    GROWTH_MAX,
    MULTIPLE_MAX,
    RISK_WEIGHT,
    TTM_STALE_DAYS,
    WEIGHTS,
)
from api.schemas import (
    IdeaExclusion,
    IdeaMember,
    IdeaMemo,
    IdeaRule,
    IdeaScore,
    IdeaSectorCount,
    IdeaShortlistStats,
    IdeasResponse,
)
from store.models import (
    Instrument,
    MetricTtm,
    OpportunityMemoRow,
    OpportunityScore,
    ScoreExclusion,
    ValuationDaily,
)

STALE_AFTER_DAYS = 7
SHORTLIST_N = 25
STATUS_ORDER = {"ranked": 0, "excluded": 1, "no_score": 2}
# Same order and thresholds as `analytics.scores.ScoreGate`; the UI reads them from here.
RULES = [
    IdeaRule(
        rule="fcf_one_off",
        label="FCF one-off",
        detail=(
            f"FCF TTM rose from a TTM at or below zero (last four) by more than "
            f"{FCF_JUMP_SHARE:.0%} of revenue, or FCF yield above {FCF_YIELD_MAX:.0%}."
        ),
    ),
    IdeaRule(
        rule="base_effect",
        label="Base effect",
        detail=f"EBITDA 1y change beyond ±{GROWTH_MAX:.0%}: the prior year is near zero.",
    ),
    IdeaRule(
        rule="extreme_multiple",
        label="Extreme multiple",
        detail=f"EV/EBITDA above {MULTIPLE_MAX:.0f}x: EBITDA too small to compare.",
    ),
    IdeaRule(
        rule="stale_ttm",
        label="Stale TTM",
        detail=f"Latest TTM more than {TTM_STALE_DAYS} days old.",
    ),
]


class IdeasBoard:
    """Builds the Ideas response from stored rows; no queries, so it tests with plain objects."""

    def __init__(
        self,
        rows: Sequence[tuple[Instrument, MetricTtm, ValuationDaily]],
        *,
        scores: Mapping[int, tuple[OpportunityScore, OpportunityMemoRow | None]],
        exclusions: Mapping[int, ScoreExclusion],
        fy_by_id: Mapping[int, Any] | None = None,
        shortlist_n: int = SHORTLIST_N,
    ) -> None:
        self.rows = rows
        self.scores = scores
        self.exclusions = exclusions
        self.fy_by_id = fy_by_id or {}
        self.shortlist_n = shortlist_n

    def build(self, *, stale: bool) -> IdeasResponse:
        members = sorted((self._member(*row) for row in self.rows), key=_order)
        ranked = [item for item in members if item.status == "ranked"]
        excluded = [item for item in members if item.status == "excluded"]
        rules = Counter(rule.rule for item in excluded for rule in item.exclusions)
        score_days = [score.as_of for score, _ in self.scores.values()]
        return IdeasResponse(
            as_of=max(score_days, default=None),
            stale=stale or not ranked,
            universe_n=len(members),
            with_data_n=len(ranked) + len(excluded),
            ranked_n=len(ranked),
            excluded_n=len(excluded),
            no_score_n=len(members) - len(ranked) - len(excluded),
            shortlist_n=self.shortlist_n,
            excluded_by_rule=dict(sorted(rules.items())),
            rules=RULES,
            weights={**WEIGHTS, "risk": RISK_WEIGHT},
            shortlist=_shortlist_stats(ranked[: self.shortlist_n]),
            members=members,
        )

    def _member(
        self, instrument: Instrument, metric: MetricTtm, value: ValuationDaily
    ) -> IdeaMember:
        key = getattr(instrument, "id", None)
        scored = self.scores.get(key)
        excluded = self.exclusions.get(key)
        if scored is not None:
            status = "ranked"
        elif excluded is not None:
            status = "excluded"
        else:
            status = "no_score"
        score, memo = scored if scored is not None else (None, None)
        return IdeaMember(
            ticker=instrument.ticker,
            name=instrument.name,
            sector=getattr(instrument, "sector", None),
            industry=getattr(instrument, "industry", None),
            status=status,
            as_of=getattr(value, "as_of", None),
            ttm_as_of=getattr(metric, "as_of", None),
            ttm_source=str(getattr(metric, "source", "sec") or "sec"),
            revenue=_num(getattr(metric, "revenue", None)),
            ebitda=_num(value.ebitda),
            ev=_num(value.ev),
            ev_ebitda=_num(value.ev_ebitda),
            pctile_5y=_num(value.pctile_5y),
            ebitda_growth_1y=_num(value.ebitda_growth_1y),
            multiple_change_1y=_num(getattr(value, "multiple_change_1y", None)),
            fcf_yield=fcf_yield(getattr(metric, "fcf", None), value.ev),
            nd_ebitda=nd_ebitda(getattr(metric, "net_debt", None), value.ebitda),
            accrual=accrual_from_fy(self.fy_by_id.get(key)),
            score=None if score is None else _score(score),
            exclusions=[] if excluded is None or scored is not None else _reasons(excluded),
            memo=None if memo is None else _memo(memo),
        )


def _order(item: IdeaMember) -> tuple[int, int, str]:
    rank = item.score.rank if item.score is not None else 0
    return (STATUS_ORDER[item.status], rank, item.ticker)


def _score(score: OpportunityScore) -> IdeaScore:
    return IdeaScore(
        rank=score.rank,
        total=_num(score.total) or 0.0,
        cheap=_num(score.cheap) or 0.0,
        quality=_num(score.quality) or 0.0,
        change=_num(score.change) or 0.0,
        setup=_num(score.setup) or 0.0,
        risk=_num(score.risk) or 0.0,
        trap=bool(score.trap),
        fcf_margin=_num(score.fcf_margin),
        ret_12_1=_num(getattr(score, "ret_12_1", None)),
    )


def _memo(memo: OpportunityMemoRow) -> IdeaMemo:
    return IdeaMemo(
        why_scored=memo.why_scored,
        what_10q_changed=memo.what_10q_changed,
        invalidation=memo.invalidation,
        caveats=memo.caveats,
        model=memo.model,
        status=memo.status,
    )


def _reasons(row: ScoreExclusion) -> list[IdeaExclusion]:
    return [
        IdeaExclusion(rule=str(item.get("rule", "")), values=dict(item.get("values") or {}))
        for item in (row.reasons or [])
    ]


def _shortlist_stats(top: Sequence[IdeaMember]) -> IdeaShortlistStats:
    multiples = [item.ev_ebitda for item in top if item.ev_ebitda is not None]
    pctiles = [item.pctile_5y for item in top if item.pctile_5y is not None]
    ttm_days: list[date] = [item.ttm_as_of for item in top if item.ttm_as_of is not None]
    sectors = Counter(item.sector or "Unclassified" for item in top)
    return IdeaShortlistStats(
        size=len(top),
        median_ev_ebitda=median(multiples) if multiples else None,
        median_pctile_5y=median(pctiles) if pctiles else None,
        net_cash=sum(1 for item in top if item.nd_ebitda is not None and item.nd_ebitda < 0),
        traps=sum(1 for item in top if item.score is not None and item.score.trap),
        oldest_ttm=min(ttm_days, default=None),
        sectors=[
            IdeaSectorCount(sector=name, count=count)
            for name, count in sorted(sectors.items(), key=lambda pair: (-pair[1], pair[0]))
        ],
    )


def _num(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
