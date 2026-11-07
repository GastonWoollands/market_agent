from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from analytics.desk import fcf_yield
from analytics.returns import LOOKBACK_3M, momentum_return, period_return
from analytics.scores import Exclusion, GateInput, ScoreGate, ScoreInput, score_universe
from jobs.runtime import record_job
from store.engine import session_scope
from store.models import MetricTtm
from store.repos import (
    adj_closes_for_instrument_ids,
    closes_for_instrument_ids,
    latest_valuation_rows,
    metric_ttm_history,
    prune_opportunity_scores,
    replace_score_exclusions,
    upsert_opportunity_scores,
)

log = logging.getLogger("jobs.compute_scores")
JOB_NAME = "compute_scores"
# 12-1 momentum needs 253 sessions.
CLOSE_DAYS = 400
# FCF one-off rule: the TTMs before the latest that it looks back over.
PRIOR_TTMS = 4
TOP_PREVIEW = 25


@dataclass(frozen=True)
class RowIn:
    id: int
    ticker: str
    sector: str | None
    comparable: bool
    pctile_5y: float | None
    ebitda_growth_1y: float | None
    ebitda: float
    revenue: float
    fcf: float | None
    net_debt: float | None
    as_of: date
    ret_3m: float | None
    ret_12_1: float | None
    fcf_margin: float | None
    fcf_yield: float | None
    net_debt_to_ebitda: float | None
    gate: GateInput


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


def _prior_fcf_low(history: Sequence[MetricTtm], as_of: date) -> float | None:
    """Lowest FCF over the TTMs just before `as_of` (the one-off rule's starting point)."""
    prior = [item.fcf for item in history if item.as_of < as_of and item.fcf is not None]
    if not prior:
        return None
    return float(min(prior[-PRIOR_TTMS:]))


def _reasons(found: list[Exclusion]) -> list[dict[str, object]]:
    return [{"rule": item.rule, "values": item.values} for item in found]


def compute(*, dry_run: bool = False, today: date | None = None) -> dict[str, object]:
    today = today or date.today()
    start = today - timedelta(days=CLOSE_DAYS)
    with session_scope() as session:
        raw = latest_valuation_rows(session)
        ids = [instrument.id for instrument, _metric, _value in raw]
        closes = closes_for_instrument_ids(session, ids, start=start)
        adjusted = adj_closes_for_instrument_ids(session, ids, start=start)
        histories = metric_ttm_history(session, ids)
        rows: list[RowIn] = []
        for instrument, metric, value in raw:
            prices = [float(close) for _day, close in closes.get(instrument.id, [])]
            adj = [float(close) for _day, close in adjusted.get(instrument.id, []) if close]
            fcf = None if metric.fcf is None else float(metric.fcf)
            net_debt = None if metric.net_debt is None else float(metric.net_debt)
            ebitda = float(value.ebitda)
            revenue = float(metric.revenue)
            growth = None if value.ebitda_growth_1y is None else float(value.ebitda_growth_1y)
            yield_ = fcf_yield(metric.fcf, value.ev)
            rows.append(
                RowIn(
                    id=instrument.id,
                    ticker=instrument.ticker,
                    sector=instrument.sector,
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
                    ret_12_1=momentum_return(adj),
                    fcf_margin=_margin(fcf, revenue),
                    fcf_yield=yield_,
                    net_debt_to_ebitda=_leverage(net_debt, ebitda),
                    gate=GateInput(
                        ticker=instrument.ticker,
                        ttm_as_of=metric.as_of,
                        revenue=revenue,
                        fcf=fcf,
                        prior_fcf_low=_prior_fcf_low(
                            histories.get(instrument.id, []), metric.as_of
                        ),
                        fcf_yield=yield_,
                        ebitda_growth_1y=growth,
                        ev_ebitda=None if value.ev_ebitda is None else float(value.ev_ebitda),
                    ),
                )
            )

    comparable = [item for item in rows if item.comparable]
    if not comparable:
        raise RuntimeError("no comparable valuation rows — run compute_valuation")
    gate = ScoreGate(today)
    excluded = {item.ticker: gate.check(item.gate) for item in comparable}
    eligible = [item for item in comparable if not excluded[item.ticker]]
    if not eligible:
        raise RuntimeError("every comparable row failed a data-quality rule")
    scored = score_universe(
        [
            ScoreInput(
                ticker=item.ticker,
                pctile_5y=item.pctile_5y,
                ebitda_growth_1y=item.ebitda_growth_1y,
                fcf_margin=item.fcf_margin,
                fcf_yield=item.fcf_yield,
                net_debt_to_ebitda=item.net_debt_to_ebitda,
                momentum=item.ret_12_1,
                sector=item.sector,
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
                "ret_12_1": _dec(source.ret_12_1),
            }
        )
    exclusions = [
        {"instrument_id": item.id, "as_of": item.as_of, "reasons": _reasons(excluded[item.ticker])}
        for item in comparable
        if excluded[item.ticker]
    ]
    rules: dict[str, int] = {}
    for found in excluded.values():
        for reason in found:
            rules[reason.rule] = rules.get(reason.rule, 0) + 1
    written = 0
    if not dry_run:
        with session_scope() as session:
            written = upsert_opportunity_scores(session, payload)
            prune_opportunity_scores(session, {int(item["instrument_id"]) for item in payload})
            replace_score_exclusions(session, exclusions)
    top = scored[0]
    return {
        "written": written,
        "excluded": len(exclusions),
        "excluded_by_rule": rules,
        "top": [item.ticker for item in scored[:TOP_PREVIEW]],
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
        description="Rank the valuation universe from stored TTM, multiples, and 12-1 momentum."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the top 25 and exclusions, write nothing"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.dry_run:
        preview = compute(dry_run=True)
        log.info("top %s: %s", TOP_PREVIEW, " ".join(preview["top"]))
        log.info("excluded %s by rule %s", preview["excluded"], preview["excluded_by_rule"])
        return
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
        "compute_scores as_of=%s written=%s excluded=%s #1=%s total=%s cheap=%s quality=%s trap=%s",
        result["as_of"],
        result["written"],
        result["excluded"],
        result["top_ticker"],
        result["top_total"],
        result["top_cheap"],
        result["top_quality"],
        result["top_trap"],
    )


if __name__ == "__main__":
    sys.exit(main())
