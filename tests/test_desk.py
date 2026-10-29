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
