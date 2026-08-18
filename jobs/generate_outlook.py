from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from agent.errors import AgentError, CitationError
from agent.outlook import narrate
from agent.providers import make_client
from jobs.runtime import record_job
from store.engine import session_scope
from store.repos import latest_evidence_pack, upsert_outlook_report
from store.settings import settings

log = logging.getLogger("jobs.generate_outlook")
JOB_NAME = "generate_outlook"
ET = ZoneInfo("America/New_York")


def generate(
    *,
    as_of: date | None = None,
    template: bool = False,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, object]:
    day = as_of or datetime.now(ET).date()
    with session_scope() as session:
        pack_row = latest_evidence_pack(session, day)
        if pack_row is None:
            raise RuntimeError(f"no evidence pack for {day.isoformat()}; run jobs.build_pack")
        payload = dict(pack_row.pack)
        pack_id = pack_row.id
    client = None
    if not template:
        try:
            client = make_client(settings, provider=provider, model=model)
        except AgentError as exc:
            log.warning("agent unavailable (%s); using template", exc)
            client = None
        if client is None:
            log.warning("no agent key configured; using template")
    written = narrate(payload, client=client)
    with session_scope() as session:
        upsert_outlook_report(
            session,
            as_of=day,
            model=written.model,
            prompt_version=written.prompt_version,
            body_md=written.body_md,
            body_json=written.body_json,
            pack_id=pack_id,
            status=written.status,
        )
    return {
        "as_of": day.isoformat(),
        "model": written.model,
        "status": written.status,
        "prompt_version": written.prompt_version,
        "pack_id": pack_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write today's Outlook brief from the stored evidence pack."
    )
    parser.add_argument("--as-of", help="YYYY-MM-DD (default: today America/New_York).")
    parser.add_argument("--template", action="store_true", help="Skip the model; fill from pack.")
    parser.add_argument(
        "--provider",
        choices=("anthropic", "gemini"),
        help="Override AGENT_PROVIDER.",
    )
    parser.add_argument("--model", help="Override AGENT_MODEL.")
    args = parser.parse_args()
    chosen = date.fromisoformat(args.as_of) if args.as_of else None
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    result: dict[str, object] = {"pack_id": 0}
    try:
        result = generate(
            as_of=chosen,
            template=args.template,
            provider=args.provider,
            model=args.model,
        )
    except CitationError as exc:
        record_job(JOB_NAME, status="error", rows_written=0, error=str(exc))
        log.exception("generate_outlook citation failed; yesterday's report kept")
        raise SystemExit(1) from exc
    except Exception as exc:
        record_job(JOB_NAME, status="error", rows_written=0, error=str(exc))
        log.exception("generate_outlook failed")
        raise SystemExit(1) from exc

    record_job(JOB_NAME, status="ok", rows_written=1, extra=result)
    log.info(
        "generate_outlook as_of=%s model=%s status=%s",
        result["as_of"],
        result["model"],
        result["status"],
    )


if __name__ == "__main__":
    sys.exit(main())
