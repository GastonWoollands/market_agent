from analytics.sectors import SECTORS, load_sic_map


def test_sic_ranges_carve_out_narrow_codes() -> None:
    sic = load_sic_map()
    assert sic.sector_for(7372) == "Information Technology"  # prepackaged software
    assert sic.sector_for(3674) == "Information Technology"  # semiconductors
    assert sic.sector_for(2834) == "Health Care"  # pharma inside chemicals
    assert sic.sector_for(2821) == "Materials"  # plastics
    assert sic.sector_for(1311) == "Energy"
    assert sic.sector_for(3711) == "Consumer Discretionary"  # motor vehicles
    assert sic.sector_for(3720) == "Industrials"  # aircraft
    assert sic.sector_for(5331) == "Consumer Staples"  # variety stores
    assert sic.sector_for(5311) == "Consumer Discretionary"  # department stores
    assert sic.sector_for(6798) == "Real Estate"  # REITs inside holding offices
    assert sic.sector_for(6022) == "Financials"
    assert sic.sector_for(4911) == "Utilities"
    assert sic.sector_for(4953) == "Industrials"  # refuse systems
    assert sic.sector_for(4813) == "Communication Services"
    assert sic.sector_for(8731) == "Health Care"
    assert sic.sector_for(4610) == "Energy"  # pipelines inside transportation


def test_ticker_overrides_and_unknowns() -> None:
    sic = load_sic_map()
    assert sic.sector_for(7370, "GOOG") == "Communication Services"
    assert sic.sector_for(7389, "v") == "Financials"
    assert sic.sector_for(7370, "ORCL") == "Information Technology"
    assert sic.sector_for(7389, "GPN") == "Financials"
    assert sic.sector_for(4400, "RCL") == "Consumer Discretionary"
    assert sic.sector_for(None) is None
    assert sic.sector_for(9999) is None


def test_every_mapped_sector_is_a_tape_sector() -> None:
    sic = load_sic_map()
    assert {item.sector for item in sic.ranges} <= SECTORS
    assert set(sic.tickers.values()) <= SECTORS
