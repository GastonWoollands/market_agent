from datetime import date, timedelta
from decimal import Decimal
from math import isclose

from api.credit import build_credit_curve
from api.peers import PeerInput, build_peers

TODAY = date(2026, 10, 30)


def _peer(ticker: str, cap: float, **kwargs) -> PeerInput:
    row = {
        "name": f"{ticker} Inc",
        "sector": "Information Technology",
        "market_cap": cap,
        "ev_ebitda": 20.0,
        "pctile_5y": 50.0,
        "fcf_yield": 0.03,
        "nd_ebitda": 0.5,
        "ebitda_growth_1y": 0.1,
    }
    row.update(kwargs)
    return PeerInput(ticker=ticker, **row)


def test_peers_nearest_by_log_cap_with_self_first() -> None:
    me = _peer("ME", 100.0)
    universe = [
        _peer("ME", 100.0),
        _peer("BIG", 10_000.0),
        _peer("NEAR", 120.0),
        _peer("HALF", 50.0),
        _peer("OTHER", 100.0, sector="Energy"),
        _peer("NOCAP", None),
    ]
    peers = build_peers(me, universe, limit=2)
    assert peers is not None
    assert [row.ticker for row in peers.rows] == ["ME", "NEAR", "HALF"]
    assert peers.rows[0].is_self
    assert peers.sector_size == 5  # ME + BIG + NEAR + HALF + NOCAP; Energy excluded


def test_unknown_own_cap_falls_back_to_sector_leaders() -> None:
    universe = [_peer("SMALL", 10.0), _peer("BIG", 900.0), _peer("MID", 100.0)]
    peers = build_peers(_peer("ME", None), universe, limit=2)
    assert peers.basis == "largest_cap"
    assert [row.ticker for row in peers.rows] == ["ME", "BIG", "MID"]


def test_medians_skip_negative_multiples_and_scatter_needs_both_axes() -> None:
    me = _peer("ME", 100.0, ev_ebitda=-5.0)
    universe = [
        _peer("A", 90.0, ev_ebitda=10.0),
        _peer("B", 110.0, ev_ebitda=30.0, ebitda_growth_1y=None),
    ]
    peers = build_peers(me, universe)
    assert isclose(peers.medians.ev_ebitda, 20.0)
    assert [point.ticker for point in peers.scatter] == ["A"]


def test_no_sector_or_no_members_means_no_peers() -> None:
    assert build_peers(_peer("ME", 1.0, sector=None), [_peer("A", 1.0)]) is None
    assert build_peers(_peer("ME", 1.0), [_peer("A", 1.0, sector="Energy")]) is None


def _daily(days: int, start: float, step: float) -> list[tuple[date, Decimal]]:
    return [
        (TODAY - timedelta(days=days - i), Decimal(str(round(start + step * i, 4))))
        for i in range(days + 1)
    ]


def test_credit_curve_bp_and_lookbacks() -> None:
    series = {
        "BAMLC0A4CBBB": _daily(400, 1.0, 0.0005),
        "BAMLC0A4CBBBEY": _daily(400, 5.0, 0.0),
        "NFCI": [(TODAY - timedelta(days=7), Decimal("-0.45"))],
    }
    curve = build_credit_curve(series, today=TODAY)
    bbb = next(item for item in curve.buckets if item.rating == "BBB")
    assert curve.as_of == TODAY
    assert not curve.stale
    assert isclose(bbb.oas_bp, 120.0)
    assert isclose(bbb.oas_1m_bp, 118.5)
    assert isclose(bbb.oas_1y_bp, 101.75, abs_tol=0.1)
    assert bbb.yield_pct == 5.0
    assert curve.nfci == -0.45
    aaa = next(item for item in curve.buckets if item.rating == "AAA")
    assert aaa.oas_bp is None and aaa.oas_1y_bp is None


def test_credit_curve_without_data_is_stale() -> None:
    curve = build_credit_curve({}, today=TODAY)
    assert curve.stale
    assert len(curve.buckets) == 7
