"""Peer comps for the Ticker page: same-sector valuation members nearest by market cap.

Peers come from the stored valuation universe only (`valuation_daily` + latest TTM), so a
peer row reads the same numbers as the Valuation grid. The page's own name is always the
first row, built from its Ticker desk, even when it sits outside the universe.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from analytics.desk import fcf_yield, nd_ebitda
from analytics.technicals import trailing_return
from api.schemas import PeerPoint, PeerRow, TickerPeers
from store.repos import (
    adj_closes_for_instrument_ids,
    latest_risk_stats,
    latest_valuation_rows,
    opportunity_score_map,
)

MAX_PEERS = 10
YEAR_SESSIONS = 252
LOOKBACK_DAYS = 400


@dataclass(frozen=True)
class PeerInput:
    ticker: str
    name: str | None
    sector: str | None
    market_cap: float | None
    ev_ebitda: float | None
    pctile_5y: float | None
    fcf_yield: float | None
    nd_ebitda: float | None
    ebitda_growth_1y: float | None
    ret_1y: float | None = None
    vol_1y: float | None = None
    rank: int | None = None


def build_peers(
    me: PeerInput, universe: Sequence[PeerInput], *, limit: int = MAX_PEERS
) -> TickerPeers | None:
    """`me` first, then the `limit` sector members closest in log market cap."""
    if not me.sector:
        return None
    sector = [item for item in universe if item.sector == me.sector and item.ticker != me.ticker]
    if not sector:
        return None
    if me.market_cap:
        basis = "nearest_cap"
        nearest = sorted(sector, key=lambda item: _cap_distance(item, me.market_cap))[:limit]
    else:
        # No market cap for this name yet (SEC shares not stored): show the sector leaders.
        basis = "largest_cap"
        nearest = sorted(sector, key=lambda item: -(item.market_cap or 0.0))[:limit]
    members = [*sector, me]
    return TickerPeers(
        sector=me.sector,
        sector_size=len(members),
        basis=basis,
        rows=[_row(me, is_self=True), *(_row(item) for item in nearest)],
        medians=_medians(members),
        scatter=[
            PeerPoint(
                ticker=item.ticker,
                ev_ebitda=item.ev_ebitda,
                ebitda_growth_1y=item.ebitda_growth_1y,
                market_cap=item.market_cap,
                is_self=item.ticker == me.ticker,
            )
            for item in members
            if item.ev_ebitda is not None
            and item.ev_ebitda > 0
            and item.ebitda_growth_1y is not None
        ],
    )


def _cap_distance(item: PeerInput, cap: float | None) -> float:
    if not cap or not item.market_cap or item.market_cap <= 0 or cap <= 0:
        return math.inf
    return abs(math.log(item.market_cap / cap))


def _row(item: PeerInput, *, is_self: bool = False) -> PeerRow:
    return PeerRow(
        ticker=item.ticker,
        name=item.name,
        is_self=is_self,
        market_cap=item.market_cap,
        ev_ebitda=item.ev_ebitda,
        pctile_5y=item.pctile_5y,
        fcf_yield=item.fcf_yield,
        nd_ebitda=item.nd_ebitda,
        ebitda_growth_1y=item.ebitda_growth_1y,
        ret_1y=item.ret_1y,
        vol_1y=item.vol_1y,
        rank=item.rank,
    )


def _medians(items: Sequence[PeerInput]) -> PeerRow:
    """Sector medians. EV/EBITDA counts positive multiples only."""

    def median(pick: Callable[[PeerInput], float | None], *, positive: bool = False) -> Any:
        values = [v for item in items if (v := pick(item)) is not None and (v > 0 or not positive)]
        return statistics.median(values) if values else None

    return PeerRow(
        ticker="Median",
        market_cap=median(lambda item: item.market_cap),
        ev_ebitda=median(lambda item: item.ev_ebitda, positive=True),
        pctile_5y=median(lambda item: item.pctile_5y),
        fcf_yield=median(lambda item: item.fcf_yield),
        nd_ebitda=median(lambda item: item.nd_ebitda),
        ebitda_growth_1y=median(lambda item: item.ebitda_growth_1y),
        ret_1y=median(lambda item: item.ret_1y),
        vol_1y=median(lambda item: item.vol_1y),
    )


def load_peer_universe(db: Any, sector: str | None, *, today: date) -> list[PeerInput]:
    """Valuation members of one sector with their latest stored desk inputs."""
    if not sector:
        return []
    rows = [row for row in latest_valuation_rows(db) if row[0].sector == sector]
    ids = [instrument.id for instrument, _, _ in rows]
    risk = latest_risk_stats(db, ids)
    adj = adj_closes_for_instrument_ids(db, ids, start=today - timedelta(days=LOOKBACK_DAYS))
    scores, _ranked = opportunity_score_map(db, ids)
    out: list[PeerInput] = []
    for instrument, ttm, value in rows:
        ev = _num(value.ev)
        net_debt = _num(ttm.net_debt)
        ebitda = _num(ttm.ebitda)
        closes = [float(value) for _day, value in adj.get(instrument.id, []) if value]
        score = scores.get(instrument.id)
        out.append(
            PeerInput(
                ticker=instrument.ticker,
                name=instrument.name,
                sector=instrument.sector,
                market_cap=ev - net_debt if ev is not None and net_debt is not None else None,
                ev_ebitda=_num(value.ev_ebitda),
                pctile_5y=_num(value.pctile_5y),
                fcf_yield=fcf_yield(ttm.fcf, ev),
                nd_ebitda=nd_ebitda(net_debt, ebitda),
                ebitda_growth_1y=_num(value.ebitda_growth_1y),
                ret_1y=trailing_return(closes, YEAR_SESSIONS),
                vol_1y=_num(getattr(risk.get(instrument.id), "vol_1y", None)),
                rank=score.rank if score is not None else None,
            )
        )
    return out


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def self_input(page: Any) -> PeerInput | None:
    """The Ticker page's own name as a peer row, from the numbers the page already shows."""
    identity = page.identity
    if identity is None:
        return None
    desk = page.desk
    return PeerInput(
        ticker=identity.ticker,
        name=identity.name,
        sector=identity.sector,
        market_cap=getattr(desk, "market_cap", None),
        ev_ebitda=getattr(desk, "ev_ebitda", None),
        pctile_5y=getattr(desk, "pctile_5y", None),
        fcf_yield=getattr(desk, "fcf_yield", None),
        nd_ebitda=getattr(desk, "nd_ebitda", None),
        ebitda_growth_1y=getattr(desk, "ebitda_growth_1y", None),
        ret_1y=getattr(page.technicals, "ret_1y", None),
        vol_1y=getattr(page.risk, "vol_1y", None),
        rank=getattr(desk, "rank", None),
    )
