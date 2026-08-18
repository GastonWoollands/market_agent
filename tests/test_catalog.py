from store.catalog import load_fred_series, load_universes


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


def test_fred_series_yaml_has_ten_year() -> None:
    catalog = load_fred_series()
    ids = [item.id for item in catalog.series]
    assert len(ids) == 13
    assert ids[0] == "DGS10"
    assert catalog.series[0].unit == "percent"
    assert {item.id for item in catalog.series} >= {"DGS10", "DGS2", "VIXCLS", "UNRATE"}
