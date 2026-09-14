from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from analytics.quant import score_quant
from jobs.runtime import record_job
from store.canonical import MetricFy
from store.catalog import load_universes
from store.engine import session_scope
from store.models import MetricFy as MetricFyRow
from store.repos import (
    closes_for_instrument_ids,
    instruments_in_universe,
    latest_valuation_rows,
    metric_fy_history,
    upsert_quant_scores,
)

log = logging.getLogger("jobs.compute_quant")
JOB_NAME = "compute_quant"
UNIVERSE = "valuation"
PRICE_DAYS = 45


@dataclass(frozen=True)
class Member:
    id: int
    ticker: str
    cik: str


def _dec(value: Decimal | None, places: int = 6) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal(10) ** -places)


def compute() -> dict[str, object]:
    gems = load_universes().gems
    start = date.today() - timedelta(days=PRICE_DAYS)
    with session_scope() as session:
        instruments = [
            Member(item.id, item.ticker, item.cik or "")
            for item in instruments_in_universe(session, UNIVERSE)
        ]
        ids = [item.id for item in instruments]
        cik_map = {item.id: item.cik for item in instruments}
        fy_by_id = {
            instrument_id: [
                _canonical_fy(cik_map.get(instrument_id, ""), row) for row in rows
            ]
            for instrument_id, rows in metric_fy_history(session, ids).items()
        }
        closes = closes_for_instrument_ids(session, ids, start=start)
        valuation = {
            instrument.id: (metric.shares, metric.fcf, metric.revenue, value.ev)
            for instrument, metric, value in latest_valuation_rows(session, UNIVERSE)
        }

    if not instruments:
        raise RuntimeError("valuation universe is empty — run ingest_sec first")

    rows: list[dict[str, object]] = []
    skipped: list[str] = []
    complete_f = 0
    gems_n = 0
    z_na = 0
    for instrument in instruments:
        years = fy_by_id.get(instrument.id, [])
        if not years:
            skipped.append(instrument.ticker)
            continue
        shares, fcf, ttm_revenue, ev = valuation.get(
            instrument.id, (None, None, None, None)
        )
        price_rows = closes.get(instrument.id, [])
        price_day, price = (price_rows[-1] if price_rows else (None, None))
        scored = score_quant(
            years,
            price=price,
            shares=shares,
            fcf=fcf,
            ev=ev,
            ttm_revenue=ttm_revenue,
            gems=gems,
        )
        if scored is None:
            skipped.append(instrument.ticker)
            continue
        as_of = price_day or scored.fy_as_of or date.today()
        if scored.f_score is not None:
            complete_f += 1
        if scored.is_gem_candidate:
            gems_n += 1
        if scored.z_inapplicable:
            z_na += 1
        rows.append(
            {
                "instrument_id": instrument.id,
                "as_of": as_of,
                "fy_as_of": scored.fy_as_of,
                "f_score": scored.f_score,
                "z_score": _dec(scored.z_score, 4),
                "z_inapplicable": scored.z_inapplicable,
                "market_cap": scored.market_cap,
                "revenue_growth_yoy": _dec(scored.revenue_growth_yoy),
                "fcf_yield": _dec(scored.fcf_yield),
                "debt_to_equity": _dec(scored.debt_to_equity),
                "is_gem_candidate": scored.is_gem_candidate,
                "f_tests": scored.f_tests,
                "z_components": scored.z_components,
            }
        )

    if not rows:
        raise RuntimeError("no fiscal-year rows — run ingest_sec so metric_fy is populated")

    with session_scope() as session:
        written = upsert_quant_scores(session, rows)

    as_of = max(row["as_of"] for row in rows)
    return {
        "as_of": as_of.isoformat() if isinstance(as_of, date) else str(as_of),
        "written": written,
        "members": len(instruments),
        "complete_f_score": complete_f,
        "gem_candidates": gems_n,
        "z_inapplicable": z_na,
        "skipped": skipped,
    }


def _canonical_fy(cik: str, row: MetricFyRow) -> MetricFy:
    return MetricFy(
        cik=cik or "0",
        as_of=row.as_of,
        fiscal_year=row.fiscal_year,
        revenue=row.revenue,
        net_income=row.net_income,
        cfo=row.cfo,
        gross_profit=row.gross_profit,
        ebit=row.ebit,
        total_assets=row.total_assets,
        current_assets=row.current_assets,
        current_liabilities=row.current_liabilities,
        long_term_debt=row.long_term_debt,
        total_liabilities=row.total_liabilities,
        retained_earnings=row.retained_earnings,
        equity=row.equity,
        shares=row.shares,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Piotroski F-Score, Altman Z, and gem-candidate flags from stored FY metrics."
    )
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result: dict[str, object] = {"written": 0, "skipped": []}
    try:
        result = compute()
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("written") or 0),
            error=str(exc),
            extra={"skipped": result.get("skipped", [])},
        )
        log.exception("compute_quant failed")
        raise SystemExit(1) from exc
    record_job(JOB_NAME, status="ok", rows_written=int(result["written"]), extra=result)
    log.info(
        "compute_quant as_of=%s written=%s f_complete=%s gems=%s z_na=%s skipped=%s",
        result["as_of"],
        result["written"],
        result["complete_f_score"],
        result["gem_candidates"],
        result["z_inapplicable"],
        len(result["skipped"]) if isinstance(result["skipped"], list) else result["skipped"],
    )


if __name__ == "__main__":
    sys.exit(main())
