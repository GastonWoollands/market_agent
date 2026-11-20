from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd

from ingest.yahoo.parse import (
    bars_from_history,
    bars_from_intraday,
    listing_from_chart_meta,
    snapshot_from_chart_meta,
    splits_from_history,
)

NY = ZoneInfo("America/New_York")
SESSION = datetime(2024, 8, 14, 16, 0, tzinfo=NY)


def test_bars_from_history_skips_null_sessions() -> None:
    frame = pd.DataFrame(
        {
            "Open": [640.1, None],
            "High": [642.0, None],
            "Low": [638.5, None],
            "Close": [641.2, None],
            "Adj Close": [641.2, None],
            "Volume": [51_000_000, None],
        },
        index=[SESSION, SESSION.replace(day=15)],
    )
    bars = bars_from_history(frame, "SPY")
    assert len(bars) == 1
    assert bars[0].yahoo_symbol == "SPY"
    assert bars[0].date == SESSION.date()
    assert bars[0].close == Decimal("641.2")
    assert bars[0].volume == 51_000_000


def test_snapshot_from_chart_meta_skips_missing_price() -> None:
    assert snapshot_from_chart_meta("XLK", {"regularMarketPrice": None}) is None
    snap = snapshot_from_chart_meta(
        "SPY",
        {
            "regularMarketPrice": 641.25,
            "previousClose": 642.56,
            "chartPreviousClose": 400.0,
            "regularMarketVolume": 48_200_000,
            "marketState": "CLOSED",
            "regularMarketTime": int(SESSION.timestamp()),
        },
    )
    assert snap is not None
    assert snap.yahoo_symbol == "SPY"
    assert snap.market_state == "CLOSED"
    assert snap.price == Decimal("641.25")
    assert snap.as_of == SESSION.astimezone(UTC)
    assert snap.change_pct is not None
    assert abs(float(snap.change_pct) - ((641.25 / 642.56 - 1) * 100)) < 0.0001


def test_snapshot_from_chart_meta_accepts_pandas_timestamp() -> None:
    snap = snapshot_from_chart_meta(
        "SPY",
        {
            "regularMarketPrice": 641.25,
            "chartPreviousClose": 642.56,
            "regularMarketVolume": 48_200_000,
            "regularMarketTime": pd.Timestamp(SESSION),
        },
    )
    assert snap is not None
    assert snap.as_of == SESSION.astimezone(UTC)


def test_intraday_keeps_two_bars_on_the_same_session() -> None:
    pre = datetime(2024, 8, 14, 8, 0, tzinfo=NY)
    rth = datetime(2024, 8, 14, 9, 35, tzinfo=NY)
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [100.5, 101.5],
            "Low": [99.5, 100.5],
            "Close": [100.2, 101.1],
            "Volume": [1_000, 2_000],
        },
        index=[pre, rth],
    )
    collapsed = bars_from_history(frame, "NVDA")
    assert len(collapsed) == 1
    bars = bars_from_intraday(frame, "NVDA", "5m")
    assert len(bars) == 2
    assert bars[0].ts.date() == bars[1].ts.date()
    assert bars[0].ts != bars[1].ts
    assert bars[0].interval == "5m"
    assert bars[1].close == Decimal("101.1")


def test_listing_from_chart_meta_uses_short_name() -> None:
    name, exchange = listing_from_chart_meta(
        "NVDA", {"shortName": "NVIDIA Corporation", "exchangeName": "NMS"}
    )
    assert name == "NVIDIA Corporation"
    assert exchange == "NMS"


def test_splits_from_history_reads_forward_and_reverse() -> None:
    days = [SESSION.replace(day=d) for d in (14, 15, 16)]
    frame = pd.DataFrame(
        {"Close": [1.0, 1.0, 1.0], "Stock Splits": [0.0, 5.0, 0.2]},
        index=days,
    )
    splits = splits_from_history(frame, "NOW")
    assert [(item.date.day, item.ratio) for item in splits] == [
        (15, Decimal("5.0")),
        (16, Decimal("0.2")),
    ]
    assert splits[0].yahoo_symbol == "NOW"


def test_splits_from_history_without_actions_column() -> None:
    frame = pd.DataFrame({"Close": [1.0]}, index=[SESSION])
    assert splits_from_history(frame, "SPY") == []
