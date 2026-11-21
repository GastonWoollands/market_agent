from datetime import date
from decimal import Decimal
from math import isclose

import pytest

from analytics.splits import ShareBasis, is_whole_split

Q = [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31)]


def _rows(*shares: float) -> list[tuple[date, float]]:
    return list(zip(Q, shares, strict=False))


def test_forward_split_scales_rows_before_the_jump() -> None:
    # NOW: 5:1 on 2025-12-18; the 2025-12-31 10-K is the first post-split count.
    rows = _rows(207.0, 208.0, 208.0, 1047.0, 1031.0)
    basis = ShareBasis([(date(2025, 12, 18), Decimal("5"))])
    factors, matches = basis.explain(rows)
    assert factors == [5.0, 5.0, 5.0, 1.0, 1.0]
    assert matches[0].rule == "straddle"
    assert basis.adjust(rows)[:3] == [1035.0, 1040.0, 1040.0]


def test_reverse_split() -> None:
    # AMCR 1:5 on 2026-01-15; the earlier ×1.6 jump is a merger, not a split.
    rows = _rows(1445.0, 2305.0, 2306.0, 2308.0, 462.0)
    factors = ShareBasis([(date(2026, 1, 15), Decimal("0.2"))]).factors(rows)
    expected = [0.2, 0.2, 0.2, 0.2, 1.0]
    assert all(isclose(f, e) for f, e in zip(factors, expected, strict=True))


def test_restated_before_filing_is_not_scaled_twice() -> None:
    # Split 2025-10-15, after the 2025-09-30 close but before that 10-Q was issued (SAB 4C):
    # the Q3 count is already post-split, so the jump sits one pair earlier.
    rows = _rows(100.0, 101.0, 404.0, 405.0, 406.0)
    basis = ShareBasis([(date(2025, 10, 15), Decimal("4"))])
    factors, matches = basis.explain(rows)
    assert factors == [4.0, 4.0, 1.0, 1.0, 1.0]
    assert matches[0].rule == "restated_early"


def test_split_newer_than_last_filing_scales_everything() -> None:
    rows = _rows(100.0, 101.0, 102.0)
    basis = ShareBasis([(date(2026, 1, 10), Decimal("10"))])
    factors, matches = basis.explain(rows)
    assert factors == [10.0, 10.0, 10.0]
    assert matches[0].rule == "after_last_filing"


def test_restated_last_filing_before_split_date() -> None:
    # The split lands after the last period end, and that filing already restated its count.
    rows = _rows(100.0, 101.0, 303.0)
    factors, matches = ShareBasis([(date(2025, 10, 1), Decimal("3"))]).explain(rows)
    assert factors == [3.0, 3.0, 1.0]
    assert matches[0].rule == "restated_early"


def test_already_consistent_series_is_left_alone() -> None:
    # Restated history: no jump anywhere next to the split date.
    rows = _rows(1000.0, 1001.0, 1002.0, 1003.0, 1004.0)
    factors, matches = ShareBasis([(date(2025, 8, 1), Decimal("2"))]).explain(rows)
    assert factors == [1.0] * 5
    assert matches[0].rule == "unmatched"


def test_split_before_history_needs_nothing() -> None:
    rows = _rows(500.0, 501.0)
    factors, matches = ShareBasis([(date(2024, 1, 2), Decimal("2"))]).explain(rows)
    assert factors == [1.0, 1.0]
    assert matches[0].rule == "before_history"


def test_two_splits_compose() -> None:
    # CPRT-style: 2:1 then 2:1 again.
    rows = _rows(238.0, 476.0, 477.0, 957.0, 958.0)
    basis = ShareBasis([(date(2025, 6, 15), Decimal("2")), (date(2025, 12, 15), Decimal("2"))])
    assert basis.factors(rows) == [4.0, 2.0, 2.0, 1.0, 1.0]


def test_merger_jump_without_split_is_untouched() -> None:
    rows = _rows(80.0, 81.0, 131.0, 132.0)
    assert ShareBasis([]).factors(rows) == [1.0] * 4


def test_tolerance_accepts_reported_rounding() -> None:
    # BKNG 25:1 reported as 31.7 -> 774.9 (x24.47).
    rows = _rows(32.0, 31.7, 774.9)
    assert ShareBasis([(date(2025, 7, 1), Decimal("25"))]).factors(rows) == [25.0, 25.0, 1.0]


def test_unit_and_zero_ratios_are_ignored() -> None:
    rows = _rows(10.0, 10.0)
    assert ShareBasis([(date(2025, 5, 1), Decimal("1")), (date(2025, 5, 2), 0)]).splits == []
    assert ShareBasis([]).factors(rows) == [1.0, 1.0]


def test_rows_must_be_sorted() -> None:
    with pytest.raises(ValueError):
        ShareBasis([]).factors([(Q[1], 1.0), (Q[0], 1.0)])


def test_lagged_cover_count_jumps_one_row_after_the_split() -> None:
    # NVDA 10:1 on 2024-06-10: the 2024-07-28 row still carries the pre-split cover count.
    rows = [
        (date(2024, 4, 28), 2500.0),
        (date(2024, 7, 28), 2460.0),
        (date(2024, 10, 27), 24530.0),
    ]
    factors, matches = ShareBasis([(date(2024, 6, 10), Decimal("10"))]).explain(rows)
    assert factors == [10.0, 10.0, 1.0]
    assert matches[0].rule == "lagged"


def test_late_filer_restated_two_rows_early() -> None:
    # SMCI 10:1 on 2024-10-01: the delayed FY 10-K restated the 2024-06-30 count.
    rows = [
        (date(2024, 3, 31), 58.6),
        (date(2024, 6, 30), 588.1),
        (date(2024, 9, 30), 591.0),
        (date(2024, 12, 31), 593.5),
        (date(2025, 3, 31), 596.8),
    ]
    factors, matches = ShareBasis([(date(2024, 10, 1), Decimal("10"))]).explain(rows)
    assert factors == [10.0, 1.0, 1.0, 1.0, 1.0]
    assert matches[0].rule == "restated_early"


def test_only_row_after_split_without_jump_is_pending() -> None:
    # APH 2:1 on 2026-09-03; the 2026-09-30 row may still be the lagged pre-split count.
    rows = [(date(2026, 3, 31), 1229.2), (date(2026, 6, 30), 1230.2), (date(2026, 9, 30), 1233.0)]
    factors, matches = ShareBasis([(date(2026, 9, 3), Decimal("2"))]).explain(rows)
    assert factors == [2.0, 2.0, 2.0]
    assert matches[0].rule == "pending_lag"


def test_spin_off_adjustment_near_one_scales_by_date() -> None:
    # HON: Yahoo books a spin-off as a 1.061 "split" and scales the closes before it.
    rows = [(date(2025, 6, 30), 640.0), (date(2025, 9, 30), 636.0), (date(2025, 12, 31), 634.0)]
    factors, matches = ShareBasis([(date(2025, 10, 30), Decimal("1.061"))]).explain(rows)
    assert factors == [1.061, 1.061, 1.0]
    assert matches[0].rule == "date"


def test_one_jump_explains_one_split() -> None:
    # Two 2:1 splits two quarters apart; the second is newer than the last filing and must not
    # reuse the first one's jump through the two-rows-early candidate.
    rows = _rows(100.0, 200.0, 201.0)
    basis = ShareBasis([(date(2025, 6, 15), Decimal("2")), (date(2025, 10, 15), Decimal("2"))])
    factors, matches = basis.explain(rows)
    assert [m.rule for m in matches] == ["straddle", "after_last_filing"]
    assert factors == [4.0, 2.0, 2.0]


def test_spin_off_factor_far_from_one_scales_by_date() -> None:
    # T: Yahoo books the 2022 spin-off as 1.324; the share count does not move.
    rows = [(date(2021, 12, 31), 7141.0), (date(2022, 3, 31), 7142.9), (date(2022, 6, 30), 7159.0)]
    factors, matches = ShareBasis([(date(2022, 4, 11), Decimal("1.324"))]).explain(rows)
    assert factors == [1.324, 1.324, 1.0]
    assert matches[0].rule == "date"


@pytest.mark.parametrize(
    ("ratio", "whole"),
    [
        (2.0, True),
        (1.5, True),
        (5.0, True),
        (0.1, True),
        (1 / 12, True),
        (1.061, False),
        (1.528, False),
        (1.941, False),
        (0.581, False),
        (0.9535, False),
    ],
)
def test_is_whole_split(ratio: float, whole: bool) -> None:
    assert is_whole_split(ratio) is whole
