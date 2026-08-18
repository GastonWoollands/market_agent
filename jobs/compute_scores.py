from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from analytics.returns import LOOKBACK_3M, period_return
from analytics.scores import ScoreInput, score_universe
from jobs.runtime import record_job
from store.engine import session_scope
from store.repos import (
    closes_for_instrument_ids,
    latest_valuation_rows,
    upsert_opportunity_scores,
)

log = logging.getLogger("jobs.compute_scores")
JOB_NAME = "compute_scores"
CLOSE_DAYS = 180


@dataclass(frozen=True)
class RowIn:
    id: int
    ticker: str
    comparable: bool
    pctile_5y: float | None
    ebitda_growth_1y: float | None
    ebitda: float
    revenue: float
    fcf: float | None
    net_debt: float | None
    as_of: date
    ret_3m: float | None
    fcf_margin: float | None
    net_debt_to_ebitda: float | None


def _dec(value: float | None, places: int = 6) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(value, places)))


def _margin(fcf: float | None, revenue: float) -> float | None:
    if fcf is None or revenue <= 0:
        return None
    return fcf / revenue


def _leverage(net_debt: float | None, ebitda: float) -> float | None:
    if net_debt is None or ebitda <= 0:
        return None
    return net_debt / ebitda


def compute() -> dict[str, object]:
    start = date.today() - timedelta(days=CLOSE_DAYS)
    with session_scope() as session:
        raw = latest_valuation_rows(session)
        ids = [instrument.id for instrument, _metric, _value in raw]
        closes = closes_for_instrument_ids(session, ids, start=start)
        rows: list[RowIn] = []
        for instrument, metric, value in raw:
            prices = [float(close) for _day, close in closes.get(instrument.id, [])]
            fcf = None if metric.fcf is None else float(metric.fcf)
            net_debt = None if metric.net_debt is None else float(metric.net_debt)
            ebitda = float(value.ebitda)
            revenue = float(metric.revenue)
            rows.append(
                RowIn(
                    id=instrument.id,
                    ticker=instrument.ticker,
                    comparable=bool(value.comparable),
                    pctile_5y=None if value.pctile_5y is None else float(value.pctile_5y),
                    ebitda_growth_1y=(
                        None if value.ebitda_growth_1y is None else float(value.ebitda_growth_1y)
                    ),
                    ebitda=ebitda,
                    revenue=revenue,
                    fcf=fcf,
                    net_debt=net_debt,
                    as_of=value.as_of,
                    ret_3m=period_return(prices, LOOKBACK_3M),
                    fcf_margin=_margin(fcf, revenue),
                    net_debt_to_ebitda=_leverage(net_debt, ebitda),
                )
            )

    eligible = [item for item in rows if item.comparable]
    if not eligible:
        raise RuntimeError("no comparable valuation rows — run compute_valuation")
    scored = score_universe(
        [
            ScoreInput(
                ticker=item.ticker,
                pctile_5y=item.pctile_5y,
                ebitda_growth_1y=item.ebitda_growth_1y,
                fcf_margin=item.fcf_margin,
                net_debt_to_ebitda=item.net_debt_to_ebitda,
                ret_3m=item.ret_3m,
            )
            for item in eligible
        ]
    )
    by_ticker = {item.ticker: item for item in eligible}
    payload: list[dict[str, object]] = []
    for item in scored:
        source = by_ticker[item.ticker]
        payload.append(
            {
                "instrument_id": source.id,
                "as_of": source.as_of,
                "rank": item.rank,
                "total": _dec(item.total),
                "cheap": _dec(item.cheap),
                "quality": _dec(item.quality),
                "change": _dec(item.change),
                "setup": _dec(item.setup),
                "insider": _dec(item.insider),
                "risk": _dec(item.risk),
                "trap": item.trap,
                "fcf_margin": _dec(source.fcf_margin),
                "ret_3m": _dec(source.ret_3m),
            }
        )
    with session_scope() as session:
        written = upsert_opportunity_scores(session, payload)
    top = scored[0]
    return {
        "written": written,
        "as_of": max(item.as_of for item in eligible).isoformat(),
        "top_ticker": top.ticker,
        "top_rank": top.rank,
        "top_total": round(top.total, 4),
        "top_cheap": round(top.cheap, 4),
        "top_quality": round(top.quality, 4),
        "top_change": round(top.change, 4),
        "top_setup": round(top.setup, 4),
        "top_risk": round(top.risk, 4),
        "top_trap": top.trap,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rank the valuation universe from stored TTM, multiples, and 63d returns."
    )
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result: dict[str, object] = {"written": 0}
    try:
        result = compute()
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("written") or 0),
            error=str(exc),
        )
        log.exception("compute_scores failed")
        raise SystemExit(1) from exc
    record_job(JOB_NAME, status="ok", rows_written=int(result["written"]), extra=result)
    log.info(
        "compute_scores as_of=%s written=%s #1=%s total=%s cheap=%s quality=%s trap=%s",
        result["as_of"],
        result["written"],
        result["top_ticker"],
        result["top_total"],
        result["top_cheap"],
        result["top_quality"],
        result["top_trap"],
    )


if __name__ == "__main__":
    sys.exit(main())
