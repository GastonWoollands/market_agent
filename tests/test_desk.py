from analytics.desk import accrual_ok, fcf_yield, nd_ebitda


def test_fcf_yield_and_nd_ebitda() -> None:
    assert fcf_yield(80, 1000) == 0.08
    assert nd_ebitda(250, 100) == 2.5
    assert fcf_yield(-10, 1000) == -0.01
    assert nd_ebitda(-40, 100) == -0.4


def test_desk_ratios_blank_on_missing_or_nonpositive_den() -> None:
    assert fcf_yield(None, 100) is None
    assert fcf_yield(10, 0) is None
    assert fcf_yield(10, -1) is None
    assert nd_ebitda(10, 0) is None
    assert nd_ebitda(10, None) is None


def test_accrual_is_cfo_gt_ni() -> None:
    assert accrual_ok(30, 20) is True
    assert accrual_ok(10, 12) is False
    assert accrual_ok(None, 12) is None
    assert accrual_ok(10, None) is None


def test_interest_coverage_dilution_and_financing_gap() -> None:
    from analytics.desk import financing_gap, interest_coverage, share_change

    assert interest_coverage(300, 100) == 3.0
    assert interest_coverage(-50, 100) == -0.5
    assert interest_coverage(300, 0) is None
    assert interest_coverage(300, None) is None
    assert abs(share_change(551, 435) - 0.2667) < 1e-3
    assert abs(share_change(95, 100) + 0.05) < 1e-12
    assert share_change(100, None) is None
    # CRWV-like: capex 20.6B, CFO 6.9B, market cap 33.6B.
    assert abs(financing_gap(20.6, 6.9, 33.6) - 0.4077) < 1e-3
    assert financing_gap(5, 10, 100) == -0.05
    assert financing_gap(None, 10, 100) is None
