import pytest

from store.tickers import TickerError, normalize_us_ticker, tv_symbol


def test_normalize_rejects_non_us_suffix() -> None:
    with pytest.raises(TickerError, match="US listings"):
        normalize_us_ticker("VOD.L")


def test_normalize_accepts_index_and_share_class() -> None:
    assert normalize_us_ticker(" spy ") == "SPY"
    assert normalize_us_ticker("^GSPC") == "^GSPC"
    assert normalize_us_ticker("BRK-B") == "BRK-B"


def test_tv_symbol_maps_yahoo_indices() -> None:
    assert tv_symbol("^GSPC") == "SPX"
    assert tv_symbol("NVDA") == "NVDA"
    assert tv_symbol("^VIX") == "VIX"
