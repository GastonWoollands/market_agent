"""
Compute and store macro regime classification.

Classifies current market environment based on growth, inflation, policy, volatility.
Run after ingest_fred and before build_pack.

Usage:
    python -m jobs.compute_regime [--as-of YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from sqlalchemy.dialects.postgresql import insert

from analytics.regime_detect import classify_regime
from jobs.runtime import record_job
from store.engine import session_scope
from store.models import RegimeSnapshot

log = logging.getLogger("jobs.compute_regime")
JOB_NAME = "compute_regime"


def compute(as_of: date) -> dict[str, object]:
    """Compute and upsert regime classification."""
    with session_scope() as session:
        regime = classify_regime(session, as_of)

        stmt = (
            insert(RegimeSnapshot)
            .values(
                as_of=as_of,
                growth_regime=regime.growth,
                inflation_regime=regime.inflation,
                policy_regime=regime.policy,
                volatility_regime=regime.volatility,
                growth_confidence=regime.growth_confidence,
                inflation_confidence=regime.inflation_confidence,
                policy_confidence=regime.policy_confidence,
                volatility_confidence=regime.volatility_confidence,
                metrics=regime.metrics,
            )
            .on_conflict_do_update(
                index_elements=["as_of"],
                set_={
                    "growth_regime": regime.growth,
                    "inflation_regime": regime.inflation,
                    "policy_regime": regime.policy,
                    "volatility_regime": regime.volatility,
                    "growth_confidence": regime.growth_confidence,
                    "inflation_confidence": regime.inflation_confidence,
                    "policy_confidence": regime.policy_confidence,
                    "volatility_confidence": regime.volatility_confidence,
                    "metrics": regime.metrics,
                },
            )
        )
        session.execute(stmt)
        session.commit()

        log.info(
            f"Regime snapshot {as_of}: growth={regime.growth} ({regime.growth_confidence:.2f}), "
            f"inflation={regime.inflation} ({regime.inflation_confidence:.2f}), "
            f"policy={regime.policy} ({regime.policy_confidence:.2f}), "
            f"volatility={regime.volatility} ({regime.volatility_confidence:.2f})"
        )

        return {
            "as_of": as_of.isoformat(),
            "growth": regime.growth,
            "inflation": regime.inflation,
            "policy": regime.policy,
            "volatility": regime.volatility,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=date.fromisoformat, help="YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    target_date = args.as_of or date.today()
    result = compute(target_date)
    record_job(JOB_NAME, status="ok", rows_written=1, extra=result)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
