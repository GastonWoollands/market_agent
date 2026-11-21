from datetime import date
from decimal import Decimal

from ingest.sec.shares import ShareCounts, rescale

AS_OF = date(2026, 6, 30)


def _instant(end: str, val: int, filed: str = "2026-08-01") -> dict[str, object]:
    return {"end": end, "val": val, "form": "10-Q", "filed": filed}


def _span(start: str, end: str, val: float) -> dict[str, object]:
    return {"start": start, "end": end, "val": val, "form": "10-Q", "filed": "2026-08-01"}


def _facts(
    *,
    cover: list | None = None,
    balance: list | None = None,
    average: list | None = None,
    income: list | None = None,
    eps: list | None = None,
) -> dict:
    gaap: dict = {}
    if balance:
        gaap["CommonStockSharesOutstanding"] = {"units": {"shares": balance}}
    if average:
        gaap["WeightedAverageNumberOfSharesOutstandingBasic"] = {"units": {"shares": average}}
    if income:
        gaap["NetIncomeLoss"] = {"units": {"USD": income}}
    if eps:
        gaap["EarningsPerShareBasic"] = {"units": {"USD/shares": eps}}
    facts: dict = {"us-gaap": gaap}
    if cover:
        facts["dei"] = {"EntityCommonStockSharesOutstanding": {"units": {"shares": cover}}}
    return facts


QUARTER_AVERAGE = [_span("2026-04-01", "2026-06-30", 89_900_000)]


def test_recent_cover_count_wins() -> None:
    facts = _facts(cover=[_instant("2026-05-01", 90_000_000)], average=QUARTER_AVERAGE)
    assert ShareCounts(facts).on(AS_OF) == Decimal("90000000")


def test_stale_cover_count_falls_back_to_the_average() -> None:
    # MA: the last undimensioned cover count is from 2010; later covers are per class.
    facts = _facts(
        cover=[_instant("2010-10-27", 122_530_193)],
        average=[_span("2026-04-01", "2026-06-30", 882_000_000)],
    )
    assert ShareCounts(facts).on(AS_OF) == Decimal("882000000")


def test_cover_count_in_thousands_of_shares_is_rescaled() -> None:
    # PKG: one cover page tagged 89,797,979,000 shares.
    facts = _facts(cover=[_instant("2026-05-01", 89_797_979_000)], average=QUARTER_AVERAGE)
    assert ShareCounts(facts).on(AS_OF) == Decimal("89797979")


def test_average_in_thousands_is_rescaled_by_net_income_over_eps() -> None:
    # WOOF: the weighted average is tagged in thousands; NI / EPS gives the real count.
    facts = _facts(
        average=[_span("2026-04-01", "2026-06-30", 273_074)],
        income=[_span("2026-04-01", "2026-06-30", 27_307_400)],
        eps=[_span("2026-04-01", "2026-06-30", 0.10)],
    )
    assert ShareCounts(facts).on(AS_OF) == Decimal("273074000")


def test_unfixable_tiny_count_is_unknown() -> None:
    # HUBG-style thousands with no EPS to check against; CHWY's pre-IPO 100-share shell.
    facts = _facts(average=[_span("2026-04-01", "2026-06-30", 60_096)])
    assert ShareCounts(facts).on(AS_OF) is None
    assert ShareCounts(_facts(balance=[_instant("2026-06-30", 100)])).on(AS_OF) is None


def test_no_recent_count_at_all_is_unknown() -> None:
    # COKE / V: only a decade-old cover count, no undimensioned average.
    facts = _facts(cover=[_instant("2016-03-04", 7_141_447)])
    assert ShareCounts(facts).on(AS_OF) is None


def test_zero_and_restated_comparatives_are_ignored() -> None:
    # SIRI: later filings restate the 2023 comparative as 0; the first filing's count stands.
    balance = [
        _instant("2026-06-30", 3_843_000_000, filed="2026-08-01"),
        _instant("2026-06-30", 0, filed="2026-11-01"),
        _instant("2026-03-31", 0, filed="2026-05-01"),
    ]
    assert ShareCounts(_facts(balance=balance)).on(AS_OF) == Decimal("3843000000")


def test_as_reported_count_is_kept_over_a_split_restatement() -> None:
    # KLAC: the next 10-K restates the comparative on the post-split basis; ShareBasis needs
    # the as-reported value to place the split.
    balance = [
        _instant("2026-06-30", 132_023_000, filed="2026-08-08"),
        _instant("2026-06-30", 1_320_227_000, filed="2027-08-06"),
    ]
    assert ShareCounts(_facts(balance=balance)).on(AS_OF) == Decimal("132023000")


def test_cover_page_beats_balance_sheet_on_the_same_day() -> None:
    facts = _facts(
        cover=[_instant("2026-06-30", 91_000_000)],
        balance=[_instant("2026-06-30", 90_000_000)],
    )
    assert ShareCounts(facts).on(AS_OF) == Decimal("91000000")


def test_split_sized_gap_is_not_rescaled() -> None:
    # A 10:1 split between the average period and the cover date stays for ShareBasis.
    assert rescale(Decimal(900_000_000), Decimal(90_000_000)) == Decimal(900_000_000)
    assert rescale(Decimal(90_000), Decimal(90_000_000)) == Decimal(90_000_000)
    assert rescale(Decimal(5), None) == Decimal(5)


def test_year_old_annual_count_is_used_when_nothing_fresher_exists() -> None:
    # HSY tags the undimensioned count only on the 10-K balance sheet.
    facts = _facts(balance=[_instant("2025-12-31", 202_839_656)])
    assert ShareCounts(facts).on(date(2026, 9, 30)) == Decimal("202839656")


def test_fresh_average_beats_a_year_old_cover_count() -> None:
    facts = _facts(
        cover=[_instant("2025-08-01", 70_000_000)],
        average=[_span("2026-04-01", "2026-06-30", 80_000_000)],
    )
    assert ShareCounts(facts).on(AS_OF) == Decimal("80000000")


def test_impossible_count_is_read_as_thousands() -> None:
    # TBLA tags both the average and EPS 1000x, so NI / EPS agrees with the wrong count.
    facts = _facts(
        average=[_span("2026-07-01", "2026-09-30", 274_600_849_000)],
        income=[_span("2026-07-01", "2026-09-30", 19_222_059)],
        eps=[_span("2026-07-01", "2026-09-30", 70)],
    )
    assert ShareCounts(facts).on(date(2026, 9, 30)) == Decimal("274600849")


def test_class_fragment_average_loses_to_a_recent_cover_count() -> None:
    # FOUR: the only undimensioned average is a 1.7M-share class; the cover says 81M.
    facts = _facts(
        cover=[_instant("2024-02-20", 82_921_152)],
        average=[_span("2024-01-01", "2024-12-31", 1_668_826)],
    )
    assert ShareCounts(facts).on(date(2024, 12, 31)) == Decimal("82921152")


def test_count_tagged_in_millions_of_thousands_is_rescaled_twice() -> None:
    facts = _facts(balance=[_instant("2026-06-30", 81_748_036_000_000)])
    assert ShareCounts(facts).on(AS_OF) == Decimal("81748036")
