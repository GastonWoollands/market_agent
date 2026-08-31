"""Tests for liquidity calculations in macro pack."""

from analytics.macro_pack import compute_net_liquidity


def test_compute_net_liquidity_basic():
    """Calculate net liquidity from Fed BS, RRP, and TGA."""
    rows = [
        {
            "series_id": "WALCL",
            "value": 7500000,  # $7.5T Fed balance sheet
            "w1": -50000,  # Down $50B WoW
        },
        {
            "series_id": "RRPONTSYD",
            "value": 500000,  # $500B RRP
            "w1": -30000,  # Down $30B WoW
        },
        {
            "series_id": "WTREGEN",
            "value": 600000,  # $600B TGA
            "w1": 20000,  # Up $20B WoW
        },
    ]

    result = compute_net_liquidity(rows)

    assert result is not None
    # Net liq = 7500 - 500 - 600 = 6400B
    assert result["net_liquidity_bn"] == 6400.0
    # Components
    assert result["components"]["fed_bs_bn"] == 7500.0
    assert result["components"]["rrp_bn"] == 500.0
    assert result["components"]["tga_bn"] == 600.0
    # WoW change
    assert result["wow_change_bn"] is not None


def test_compute_net_liquidity_missing_data():
    """Return None if any component is missing."""
    rows = [
        {"series_id": "WALCL", "value": 7500000},
        {"series_id": "RRPONTSYD", "value": None},  # Missing
    ]

    result = compute_net_liquidity(rows)
    assert result is None


def test_compute_net_liquidity_no_wow_change():
    """Handle case where WoW deltas not available."""
    rows = [
        {"series_id": "WALCL", "value": 7500000},
        {"series_id": "RRPONTSYD", "value": 500000},
        {"series_id": "WTREGEN", "value": 600000},
    ]

    result = compute_net_liquidity(rows)

    assert result is not None
    assert result["net_liquidity_bn"] == 6400.0
    assert result["wow_change_bn"] is None  # No w1 deltas provided


def test_compute_net_liquidity_rising_liquidity():
    """Net liquidity rising = supportive for risk assets."""
    rows = [
        {"series_id": "WALCL", "value": 7600000, "w1": 100000},  # Fed BS up
        {"series_id": "RRPONTSYD", "value": 450000, "w1": -50000},  # RRP down (liquidity injection)
        {"series_id": "WTREGEN", "value": 550000, "w1": -30000},  # TGA down (Treasury spending)
    ]

    result = compute_net_liquidity(rows)

    assert result is not None
    # Net liq = 7600 - 450 - 550 = 6600B
    assert result["net_liquidity_bn"] == 6600.0
    # Prior net liq = (7600-100) - (450+50) - (550+30) = 7500 - 500 - 580 = 6420
    # WoW change = 6600 - 6420 = +180B
    assert result["wow_change_bn"] > 0
    assert abs(result["wow_change_bn"] - 180.0) < 1.0  # Allow rounding


def test_compute_net_liquidity_falling_liquidity():
    """Net liquidity falling = headwind for risk assets."""
    rows = [
        {"series_id": "WALCL", "value": 7400000, "w1": -100000},  # Fed BS down (QT)
        {"series_id": "RRPONTSYD", "value": 550000, "w1": 50000},  # RRP up (liquidity parked)
        {"series_id": "WTREGEN", "value": 650000, "w1": 30000},  # TGA up (Treasury accumulating)
    ]

    result = compute_net_liquidity(rows)

    assert result is not None
    # Net liq = 7400 - 550 - 650 = 6200B
    assert result["net_liquidity_bn"] == 6200.0
    # Prior net liq = 7500 - 500 - 620 = 6380
    # WoW change = 6200 - 6380 = -180B
    assert result["wow_change_bn"] < 0
    assert abs(result["wow_change_bn"] + 180.0) < 1.0
