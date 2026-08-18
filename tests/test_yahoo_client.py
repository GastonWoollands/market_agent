from unittest.mock import MagicMock, patch

import pandas as pd
from yfinance.exceptions import YFRateLimitError

from ingest.yahoo.client import YahooClient
from ingest.yahoo.errors import YahooHttpError


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [1.0],
            "High": [1.0],
            "Low": [1.0],
            "Close": [1.0],
            "Adj Close": [1.0],
            "Volume": [1],
        },
        index=pd.DatetimeIndex(["2024-08-14"]),
    )


def test_fetch_chart_passes_caret_symbol() -> None:
    ticker = MagicMock()
    ticker.history.return_value = _frame()
    with patch("ingest.yahoo.client.yf.Ticker", return_value=ticker) as ctor:
        client = YahooClient(session=object(), rate=100.0)
        bars = client.fetch_chart("^GSPC", range_="1y")
    ctor.assert_called_once()
    assert ctor.call_args.args[0] == "^GSPC"
    assert ticker.history.call_args.kwargs["auto_adjust"] is False
    assert bars[0].yahoo_symbol == "^GSPC"
    client.close()


def test_fetch_chart_maps_rate_limit() -> None:
    ticker = MagicMock()
    ticker.history.side_effect = YFRateLimitError()
    with patch("ingest.yahoo.client.yf.Ticker", return_value=ticker):
        client = YahooClient(session=object(), rate=100.0)
        try:
            client.fetch_chart("SPY")
        except YahooHttpError as exc:
            assert exc.status_code == 429
        else:
            raise AssertionError("expected YahooHttpError")
        client.close()
