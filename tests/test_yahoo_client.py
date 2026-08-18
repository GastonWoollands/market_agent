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


def test_fetch_intraday_passes_prepost_and_5m() -> None:
    ticker = MagicMock()
    ticker.history.return_value = pd.DataFrame(
        {
            "Open": [1.0, 1.1],
            "High": [1.0, 1.2],
            "Low": [1.0, 1.0],
            "Close": [1.0, 1.15],
            "Volume": [1, 2],
        },
        index=pd.DatetimeIndex(["2024-08-14 08:00", "2024-08-14 09:35"]),
    )
    with patch("ingest.yahoo.client.yf.Ticker", return_value=ticker):
        client = YahooClient(session=object(), rate=100.0)
        bars = client.fetch_intraday("SPY")
    assert ticker.history.call_args.kwargs["prepost"] is True
    assert ticker.history.call_args.kwargs["interval"] == "5m"
    assert ticker.history.call_args.kwargs["auto_adjust"] is False
    assert len(bars) == 2
    client.close()


def test_fetch_quotes_refreshes_1d_when_only_chart_previous_close() -> None:
    ticker = MagicMock()

    def history(**_kwargs: object) -> pd.DataFrame:
        ticker.history_metadata = {
            "regularMarketPrice": 641.25,
            "previousClose": 642.56,
            "regularMarketTime": 1_723_665_600,
        }
        return _frame()

    ticker.history.side_effect = history
    ticker.history_metadata = {"regularMarketPrice": 641.25, "chartPreviousClose": 400.0}
    with patch("ingest.yahoo.client.yf.Ticker", return_value=ticker):
        client = YahooClient(session=object(), rate=100.0)
        snaps = client.fetch_quotes(["SPY"])
    assert ticker.history.call_args.kwargs["period"] == "1d"
    assert ticker.history.call_args.kwargs["interval"] == "1d"
    assert len(snaps) == 1
    assert snaps[0].change_pct is not None
    assert abs(float(snaps[0].change_pct)) < 1
    client.close()
