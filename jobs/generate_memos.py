from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from agent.errors import AgentError
from agent.memos import MEMO_LIMIT, name_pack, narrate_memo
from agent.providers import make_client
from jobs.runtime import record_job
from store.engine import session_scope
from store.repos import events_for_ticker, latest_opportunity_rows, upsert_opportunity_memo
from store.settings import settings

log = logging.getLogger("jobs.generate_memos")
JOB_NAME = "generate_memos"


def generate(
    *, template: bool = False, provider: str | None = None, model: str | None = None
) -> dict[str, object]:
    with session_scope() as session:
        rows = latest_opportunity_rows(session)
        top = [item for item in rows if item[1].rank <= MEMO_LIMIT]
        packs: list[tuple[int, date, int, dict]] = []
        for instrument, score, value, _memo in top:
            events = [
                {"date": event.date.isoformat(), "title": event.title, "kind": event.kind}
                for event in events_for_ticker(session, instrument.ticker)
            ]
            packs.append(
                (
                    instrument.id,
                    score.as_of,
                    score.rank,
                    name_pack(
                        ticker=instrument.ticker,
                        name=instrument.name,
                        rank=score.rank,
                        total=float(score.total),
                        cheap=float(score.cheap),
                        quality=float(score.quality),
                        change=float(score.change),
                        setup=float(score.setup),
                        insider=float(score.insider),
                        risk=float(score.risk),
                        trap=bool(score.trap),
                        pctile_5y=None if value.pctile_5y is None else float(value.pctile_5y),
                        ev_ebitda=float(value.ev_ebitda),
                        ebitda_growth_1y=(
                            None
                            if value.ebitda_growth_1y is None
                            else float(value.ebitda_growth_1y)
                        ),
                        fcf_margin=(
                            None if score.fcf_margin is None else float(score.fcf_margin)
                        ),
                        ret_3m=None if score.ret_3m is None else float(score.ret_3m),
                        events=events,
                    ),
                )
            )
    if not packs:
        raise RuntimeError("no opportunity scores — run compute_scores")

    client = None
    if not template:
        try:
            client = make_client(settings, provider=provider, model=model)
        except AgentError as exc:
            log.warning("agent unavailable (%s); using template", exc)
            client = None
        if client is None:
            log.warning("no agent key configured; using template")

    written = 0
    fallbacks = 0
    with session_scope() as session:
        for instrument_id, as_of, rank, pack in packs:
            memo = narrate_memo(pack, client=client)
            if memo.status == "fallback":
                fallbacks += 1
            upsert_opportunity_memo(
                session,
                {
                    "instrument_id": instrument_id,
                    "as_of": as_of,
                    "rank": rank,
                    "model": memo.model,
                    "prompt_version": memo.prompt_version,
                    "why_scored": memo.memo.why_scored,
                    "what_10q_changed": memo.memo.what_10q_changed,
                    "invalidation": memo.memo.invalidation,
                    "caveats": memo.memo.caveats,
                    "pack": memo.pack,
                    "status": memo.status,
                },
            )
            written += 1
    return {
        "written": written,
        "fallbacks": fallbacks,
        "limit": MEMO_LIMIT,
        "as_of": packs[0][1].isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write pack-grounded memos for opportunity ranks ≤ 20."
    )
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--provider", choices=("anthropic", "gemini"))
    parser.add_argument("--model")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    result: dict[str, object] = {"written": 0}
    try:
        result = generate(template=args.template, provider=args.provider, model=args.model)
    except Exception as exc:
        record_job(
            JOB_NAME,
            status="error",
            rows_written=int(result.get("written") or 0),
            error=str(exc),
        )
        log.exception("generate_memos failed")
        raise SystemExit(1) from exc
    record_job(JOB_NAME, status="ok", rows_written=int(result["written"]), extra=result)
    log.info(
        "generate_memos as_of=%s written=%s fallbacks=%s",
        result["as_of"],
        result["written"],
        result["fallbacks"],
    )


if __name__ == "__main__":
    sys.exit(main())
