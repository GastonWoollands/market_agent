"""Shares outstanding on a balance-sheet date, cleaned of stale and mis-scaled XBRL counts."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ingest.sec.xbrl import as_date, as_decimal, unit_rows

INSTANT_CONCEPTS = (
    ("dei", "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesOutstanding"),
)
AVERAGE_CONCEPTS = (
    ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
    ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
)
NET_INCOME = ("us-gaap", "NetIncomeLoss")
EPS_BASIC = ("us-gaap", "EarningsPerShareBasic")
SHARE_UNITS = ("shares", "pure")
# A count older than FRESH_DAYS loses to a fresh weighted average; past STALE_DAYS it is not
# used at all. Multi-class filers (MA, V, CME) tag the cover count per class, so their last
# undimensioned value can be a decade old; 10-K-only tags (HSY) are up to a year old.
FRESH_DAYS = 200
STALE_DAYS = 400
# Cover pages and averages tagged in thousands (or as thousands of thousands) are off by
# exactly this factor; a split never is.
UNIT_SCALE = Decimal(1000)
SCALE_TOLERANCE = Decimal("0.10")
# EPS rounded to the cent makes NI / EPS useless below this.
MIN_EPS = Decimal("0.05")
# Below this the count is a pre-IPO or pre-spin shell placeholder, or an unfixable unit typo.
MIN_SHARES = Decimal(100_000)
# No US listing has this many shares (NVDA ~24.5B, AAPL ~15B): above it the tag is in
# thousands (TBLA tags both the average and EPS 1000x, so NI / EPS cannot catch it).
MAX_SHARES = Decimal(50_000_000_000)
# An average this many times below a recent cover count is a class fragment, not the total.
FRAGMENT_RATIO = 10
AGREE_TOLERANCE = Decimal("0.5")
QUARTER_DAYS = (60, 120)


class ShareCounts:
    """Common shares outstanding for one filer, at any balance-sheet date.

    The cover-page count (dei) is preferred, as reported: a split shows as a jump that
    `analytics.splits.ShareBasis` matches later, so restated comparatives are not used. When
    no recent cover count exists, the period's weighted average stands in. Either is checked
    against an independent reference (the average, else net income / basic EPS) and rescaled
    when it is off by exactly 1000x; a count no listing could have is read as thousands.
    """

    def __init__(self, facts: dict[str, Any]) -> None:
        self._instants = self._load_instants(facts)
        self._averages = self._load_averages(facts)
        self._implied = self._load_implied(facts)

    def on(self, as_of: date) -> Decimal | None:
        """Fresh cover count, else fresh average, else either up to STALE_DAYS old."""
        for days in (FRESH_DAYS, STALE_DAYS):
            floor = as_of - timedelta(days=days)
            average = self._average(as_of, floor)
            instant = self._instant(as_of, floor)
            if instant is not None:
                reference = average if average is not None else self._latest_implied(as_of, floor)
                return _plausible(rescale(instant, reference))
            if average is not None:
                return _plausible(self._unless_fragment(average, as_of, floor))
        return None

    def _unless_fragment(self, average: Decimal, as_of: date, floor: date) -> Decimal:
        """An average 10x below the last cover count is one share class (FOUR), unless NI / EPS
        backs it (FUBO after a 1:12 reverse split). Without EPS the older count wins."""
        older = self._instant(as_of, date.min)
        if older is None or average * FRAGMENT_RATIO >= older:
            return average
        implied = self._latest_implied(as_of, floor)
        if implied is not None and abs(average / implied - 1) <= AGREE_TOLERANCE:
            return average
        return older

    def _instant(self, as_of: date, floor: date) -> Decimal | None:
        best: tuple[date, Decimal] | None = None
        for end, value in self._instants:
            if floor <= end <= as_of and (best is None or end > best[0]):
                best = (end, value)
        return None if best is None else best[1]

    def _latest_implied(self, as_of: date, floor: date) -> Decimal | None:
        spans = [span for span in self._implied if floor <= span[1] <= as_of]
        return self._implied[max(spans, key=lambda span: (span[1], span[0]))] if spans else None

    def _average(self, as_of: date, floor: date) -> Decimal | None:
        best: tuple[tuple[date, int], Decimal, tuple[date, date] | None] | None = None
        for start, end, value in self._averages:
            if not floor <= end <= as_of:
                continue
            days = (end - start).days if start is not None else 90
            quarter = 1 if QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1] else 0
            score = (end, quarter)
            if best is None or score > best[0]:
                best = (score, value, (start, end) if start is not None else None)
        if best is None:
            return None
        _score, value, span = best
        return rescale(value, self._implied.get(span) if span else None)

    @staticmethod
    def _load_instants(facts: dict[str, Any]) -> list[tuple[date, Decimal]]:
        """One positive count per date: the first concept, then the first filing (as reported)."""
        picked: dict[date, tuple[int, str, Decimal]] = {}
        for rank, (taxonomy, concept) in enumerate(INSTANT_CONCEPTS):
            for row in unit_rows(facts, taxonomy, concept, SHARE_UNITS):
                if row.get("start"):
                    continue
                end = as_date(row.get("end"))
                value = as_decimal(row.get("val"))
                if end is None or value is None or value <= 0:
                    continue
                key = (rank, str(row.get("filed") or ""))
                if end not in picked or key < picked[end][:2]:
                    picked[end] = (*key, value)
        return sorted((end, value) for end, (_rank, _filed, value) in picked.items())

    @staticmethod
    def _load_averages(facts: dict[str, Any]) -> list[tuple[date | None, date, Decimal]]:
        out: list[tuple[date | None, date, Decimal]] = []
        for taxonomy, concept in AVERAGE_CONCEPTS:
            for row in unit_rows(facts, taxonomy, concept, SHARE_UNITS):
                end = as_date(row.get("end"))
                value = as_decimal(row.get("val"))
                if end is None or value is None or value <= 0:
                    continue
                out.append((as_date(row.get("start")), end, value))
        return out

    @staticmethod
    def _load_implied(facts: dict[str, Any]) -> dict[tuple[date, date], Decimal]:
        """Net income / basic EPS per period: a share count the filer did not type directly."""
        income = _spans(facts, NET_INCOME, ("USD",))
        eps = _spans(facts, EPS_BASIC, ("USD/shares",))
        out: dict[tuple[date, date], Decimal] = {}
        for span, per_share in eps.items():
            total = income.get(span)
            if total is None or abs(per_share) < MIN_EPS:
                continue
            implied = total / per_share
            if implied > 0:
                out[span] = implied
        return out


def _plausible(value: Decimal) -> Decimal | None:
    while value > MAX_SHARES:
        value = value / UNIT_SCALE
    return value if MIN_SHARES <= value <= MAX_SHARES else None


def rescale(value: Decimal, reference: Decimal | None) -> Decimal:
    """Undo a 1000x unit slip against an independent count; anything else is left alone."""
    if reference is None or reference <= 0:
        return value
    ratio = value / reference
    if abs(ratio / UNIT_SCALE - 1) <= SCALE_TOLERANCE:
        return value / UNIT_SCALE
    if abs(ratio * UNIT_SCALE - 1) <= SCALE_TOLERANCE:
        return value * UNIT_SCALE
    return value


def _spans(
    facts: dict[str, Any], key: tuple[str, str], units: tuple[str, ...]
) -> dict[tuple[date, date], Decimal]:
    out: dict[tuple[date, date], Decimal] = {}
    taxonomy, concept = key
    for row in unit_rows(facts, taxonomy, concept, units):
        start = as_date(row.get("start"))
        end = as_date(row.get("end"))
        value = as_decimal(row.get("val"))
        if start is not None and end is not None and value is not None:
            out.setdefault((start, end), value)
    return out
