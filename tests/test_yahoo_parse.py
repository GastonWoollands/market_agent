from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd

from ingest.yahoo.parse import bars_from_history, snapshot_from_chart_meta

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
            "chartPreviousClose": 642.56,
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
