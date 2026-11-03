"""Kalshi index close ranges and macro outcomes onto `odds_snapshot` (source = kalshi).

Each catalog series reads its soonest open event, so nothing rotates by hand. A range
series becomes an implied close distribution; an outcome or binary series becomes the
same shape as a Polymarket row so Live can show both on one line.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from decimal import Decimal

from analytics.prediction_markets import MIN_QUOTED_MASS, RangeDistribution, contract_mid
from ingest.kalshi import KalshiClient
from ingest.kalshi.errors import KalshiError
from jobs.runtime import tracked_job
from store.canonical import KalshiEvent, OddsPoint
from store.catalog import KalshiSeries, load_kalshi
from store.engine import session_scope
from store.repos import upsert_odds

log = logging.getLogger("jobs.ingest_kalshi")
JOB_NAME = "ingest_kalshi"
SOURCE = "kalshi"
QUANTILES = (0.1, 0.5, 0.9)


class KalshiSnapshotBuilder:
    """Turns one open Kalshi event into the `odds_snapshot` row for its catalog slot."""

    def __init__(self, series: KalshiSeries, *, now: datetime) -> None:
        self.series = series
        self.now = now

    def build(self, event: KalshiEvent) -> OddsPoint | None:
        if self.series.kind == "range":
            return self._range(event)
        return self._outcomes(event)

    def _range(self, event: KalshiEvent) -> OddsPoint | None:
        distribution = RangeDistribution.from_markets(event.markets)
        if distribution is None:
            return None
        p10, p50, p90 = (round(distribution.quantile(q), 2) for q in QUANTILES)
        return self._point(
            event,
            implied_yes=distribution.mode.probability,
            raw={
                "kind": "range",
                "buckets": [
                    [bucket.low, bucket.high, round(bucket.probability, 6)]
                    for bucket in distribution.buckets
                ],
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "quoted_mass": round(distribution.quoted_mass, 4),
                "thin": distribution.thin,
            },
        )

    def _outcomes(self, event: KalshiEvent) -> OddsPoint | None:
        markets = []
        for market in event.markets:
            mid = contract_mid(market)
            markets.append(
                {
                    "question": market.label,
                    "key": self.series.outcome_key(market.ticker) or "yes",
                    "yes": None if mid is None else str(round(mid, 4)),
                    "bid": None if market.yes_bid is None else str(market.yes_bid),
                    "ask": None if market.yes_ask is None else str(market.yes_ask),
                    "volume": str(market.volume),
                }
            )
        priced = [float(item["yes"]) for item in markets if item["yes"] is not None]
        if not priced:
            return None
        thin = self.series.kind == "outcomes" and sum(priced) < MIN_QUOTED_MASS
        return self._point(
            event,
            implied_yes=max(priced),
            raw={"kind": self.series.kind, "markets": markets, "thin": thin},
        )

    def _point(self, event: KalshiEvent, *, implied_yes: float, raw: dict) -> OddsPoint:
        strike = event.strike_date.isoformat() if event.strike_date else None
        return OddsPoint(
            source=SOURCE,
            slot=self.series.slot,
            slug=event.ticker,
            question=event.title,
            implied_yes=Decimal(str(round(implied_yes, 6))),
            liquidity=None,
            as_of=self.now,
            raw={
                "title": event.title,
                "sub_title": event.sub_title,
                "strike_date": strike,
                "closed": False,
                **raw,
            },
        )


def first_open_point(
    series: KalshiSeries, events: list[KalshiEvent], *, now: datetime
) -> OddsPoint | None:
    """Soonest event still before its strike: Kalshi keeps an event open until settlement."""
    builder = KalshiSnapshotBuilder(series, now=now)
    for event in events:
        if event.strike_date is not None and event.strike_date <= now:
            continue
        if (point := builder.build(event)) is not None:
            return point
    return None


def ingest(*, now: datetime | None = None) -> dict[str, object]:
    clock = now or datetime.now(UTC)
    catalog = load_kalshi()
    points: list[OddsPoint] = []
    failures: list[str] = []
    with KalshiClient() as client:
        for series in catalog.series:
            try:
                events = client.open_events(series.series)
            except KalshiError as exc:
                if getattr(exc, "status_code", None) == 429:
                    raise
                failures.append(f"{series.slot}: {exc}")
                continue
            point = first_open_point(series, events, now=clock)
            if point is None:
                failures.append(f"{series.slot}: no open event with a quoted book")
                continue
            points.append(point)
    with session_scope() as session:
        for point in points:
            upsert_odds(session, point)
    if not points:
        raise RuntimeError(f"no Kalshi rows written: {failures}")
    return {"rows": len(points), "failures": failures}


def main() -> None:
    argparse.ArgumentParser(description="Ingest Kalshi index ranges and macro odds.").parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        with tracked_job(JOB_NAME) as run:
            result = ingest()
            run.rows = int(result["rows"])
            run.extra = {"failures": result["failures"], "source": SOURCE}
            log.info("ingest_kalshi rows=%s failures=%s", result["rows"], result["failures"])
    except Exception:
        log.exception("ingest_kalshi failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    sys.exit(main())
