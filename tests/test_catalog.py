from store.catalog import load_universes


def test_universes_yaml_loads() -> None:
    catalog = load_universes()
    tickers = {item.ticker for item in catalog.tape.instruments}
    assert "SPY" in tickers
    assert "XLK" in tickers
    assert catalog.watchlist.instruments
    assert {item.ticker for item in catalog.watchlist.instruments} >= {"NVDA", "SPY"}
    header = [item.ticker for item in catalog.live.header]
    assert header == ["^GSPC", "QQQ", "^RUT", "^DJI", "USO", "GLD"]
    assert "SPY" not in header
    assert catalog.live.header[0].label == "S&P 500"
