from datetime import UTC, date, datetime

from analytics.session import MarketClock, sessions_between
from api.freshness import FreshnessView
from store.repos import FreshnessDates

# Tuesday 2026-11-03 13:02 ET, cash session open.
INTRADAY = datetime(2026, 11, 3, 18, 2, tzinfo=UTC)


def _dates(**overrides: object) -> FreshnessDates:
    base: dict[str, object] = {
        "quotes_as_of": datetime(2026, 11, 3, 18, 0, tzinfo=UTC),
        "spy_last_bar": date(2026, 11, 3),
        "dgs10_last": date(2026, 10, 30),
        "sec_finished_at": datetime(2026, 10, 31, 18, 51, tzinfo=UTC),
        "sec_facts_as_of": date(2026, 10, 31),
        "ttm_names": 973,
        "ttm_older_than_cutoff": 50,
        "scores_as_of": date(2026, 11, 2),
        "rrg_as_of": date(2026, 11, 2),
        "outlook_as_of": date(2026, 11, 3),
    }
    base.update(overrides)
    return FreshnessDates(**base)  # type: ignore[arg-type]


def _status(view: FreshnessView) -> dict[str, str]:
    return {item.key: item.status for item in view.response().items}


def test_session_dates_follow_the_et_clock() -> None:
    assert MarketClock(INTRADAY).last_session() == date(2026, 11, 3)
    assert MarketClock(INTRADAY).last_close() == date(2026, 11, 2)
    # Monday 08:00 ET: neither has happened today, so both fall back to Friday.
    monday_pre = datetime(2026, 11, 2, 13, 0, tzinfo=UTC)
    assert MarketClock(monday_pre).last_session() == date(2026, 10, 30)
    assert MarketClock(monday_pre).last_close() == date(2026, 10, 30)
    assert sessions_between(date(2026, 10, 30), date(2026, 11, 3)) == 2


def test_everything_current_reads_ok() -> None:
    assert set(_status(FreshnessView(_dates(), now=INTRADAY)).values()) == {"ok"}


def test_partial_bar_does_not_make_yesterdays_rotation_late() -> None:
    status = _status(FreshnessView(_dates(rrg_as_of=date(2026, 11, 2)), now=INTRADAY))
    assert status["rotation"] == "ok"


def test_late_domains_are_flagged() -> None:
    dates = _dates(
        quotes_as_of=datetime(2026, 11, 2, 20, 0, tzinfo=UTC),
        dgs10_last=date(2026, 10, 27),
        ttm_older_than_cutoff=221,
        scores_as_of=date(2026, 10, 30),
        outlook_as_of=date(2026, 11, 2),
    )
    status = _status(FreshnessView(dates, now=INTRADAY))
    assert status == {
        "prices": "late",
        "macro": "late",
        "filings": "late",
        "scores": "late",
        "rotation": "ok",
        "outlook": "late",
    }


def test_missing_domain_and_filings_note() -> None:
    view = FreshnessView(_dates(outlook_as_of=None, ttm_older_than_cutoff=221), now=INTRADAY)
    items = {item.key: item for item in view.response().items}
    assert items["outlook"].status == "missing"
    assert items["filings"].note == (
        "SEC data from 2026-10-31; 221 of 973 names have a latest TTM older than 150 days"
    )


def test_filings_late_when_sec_data_is_old_even_if_ttm_share_is_fine() -> None:
    view = FreshnessView(_dates(sec_facts_as_of=date(2026, 8, 18)), now=INTRADAY)
    filings = next(item for item in view.response().items if item.key == "filings")
    assert filings.status == "late"
    assert filings.as_of == "2026-08-18"
    assert "(older than 10 days)" in (filings.note or "")


def test_filings_falls_back_to_run_date_without_facts_date() -> None:
    view = FreshnessView(_dates(sec_facts_as_of=None), now=INTRADAY)
    filings = next(item for item in view.response().items if item.key == "filings")
    assert filings.as_of == "2026-10-31"
    assert filings.status == "ok"


def test_stalled_bars_flag_scores_and_rotation() -> None:
    stalled = _status(
        FreshnessView(
            _dates(
                spy_last_bar=date(2026, 10, 28),
                scores_as_of=date(2026, 10, 28),
                rrg_as_of=date(2026, 10, 28),
            ),
            now=INTRADAY,
        )
    )
    assert stalled["scores"] == "late"
    assert stalled["rotation"] == "late"
    no_bars = FreshnessView(_dates(spy_last_bar=None), now=INTRADAY).response().items
    rotation = next(item for item in no_bars if item.key == "rotation")
    assert rotation.status == "late"
    assert rotation.note == "No SPY daily bars stored"
