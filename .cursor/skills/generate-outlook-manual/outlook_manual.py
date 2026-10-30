"""Manual Outlook helper: dump the writer slice, check a brief, save it.

Run from the repo root with the project venv:

    python .claude/skills/generate-outlook-manual/outlook_manual.py dump --out DIR
    python .claude/skills/generate-outlook-manual/outlook_manual.py check DIR/brief.json
    python .claude/skills/generate-outlook-manual/outlook_manual.py save DIR/brief.json \
        --model manual/claude-opus-5-5

Reads the stored pack only. Never fetches.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agent.brief import OutlookBrief
from agent.citations import citation_issues, coverage_issues, validate_brief_fields
from agent.outlook import render_markdown, user_prompt
from agent.pack import writer_pack
from agent.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from store.engine import session_scope
from store.repos import latest_evidence_pack, upsert_outlook_report


def _today_et() -> date:
    return datetime.now(ZoneInfo("America/New_York")).date()


def _load(as_of: date) -> tuple[dict[str, Any], int]:
    with session_scope() as session:
        row = latest_evidence_pack(session, as_of)
        if row is None:
            raise SystemExit(f"No evidence pack for {as_of}. Run: python -m jobs.build_pack")
        return dict(row.pack), row.id


def dump(as_of: date, out: Path) -> None:
    pack, pack_id = _load(as_of)
    out.mkdir(parents=True, exist_ok=True)
    (out / "system.txt").write_text(SYSTEM_PROMPT)
    (out / "user.txt").write_text(user_prompt(pack))
    (out / "writer.json").write_text(json.dumps(writer_pack(pack), indent=1, default=str))
    clock = pack.get("session") or {}
    regime = pack.get("regime") or {}
    print(f"pack {pack_id} as_of {pack.get('as_of')} prompt {PROMPT_VERSION}")
    print(f"session {clock.get('phase')} built {clock.get('built_at_et')} ET")
    if regime:
        print(
            "regime "
            + "/".join(str(regime.get(k)) for k in ("growth", "inflation", "policy", "volatility"))
        )
    for row in (pack.get("extended_hours") or [])[:8]:
        print(f"  {row['side']:4} {row['ticker']:6} {row['gap_pct']:+.2f}% at {row['as_of_et']}")
    news = writer_pack(pack)["news"]
    print(f"headlines {len(news)}: " + ", ".join(sorted({str(n.get('category')) for n in news})))
    for row in pack.get("anomalies") or []:
        print(f"  anomaly {row.get('severity')}: {row.get('description')}")
    print(f"wrote {out}/system.txt user.txt writer.json")


def _issues(pack: dict[str, Any], brief_json: dict[str, Any]) -> tuple[OutlookBrief, list[str]]:
    brief = OutlookBrief.model_validate(brief_json)
    text = render_markdown(brief)
    issues = (
        citation_issues(pack, text)
        + coverage_issues(pack, text)
        + validate_brief_fields(brief_json)
    )
    return brief, issues


def check(as_of: date, path: Path) -> bool:
    pack, _ = _load(as_of)
    _, issues = _issues(pack, json.loads(path.read_text()))
    print("ok" if not issues else "issues: " + ", ".join(issues))
    return not issues


def save(as_of: date, path: Path, model: str) -> bool:
    if not model.startswith("manual/"):
        raise SystemExit("--model must look like manual/<agent-model>")
    pack, pack_id = _load(as_of)
    brief, issues = _issues(pack, json.loads(path.read_text()))
    if issues:
        print("issues: " + ", ".join(issues))
        return False
    with session_scope() as session:
        upsert_outlook_report(
            session,
            as_of=as_of,
            model=model,
            prompt_version=PROMPT_VERSION,
            body_md=render_markdown(brief),
            body_json=brief.model_dump(),
            pack_id=pack_id,
            status="ok",
        )
    print(f"saved {as_of} pack {pack_id} {model} {PROMPT_VERSION}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("dump", "check", "save"))
    parser.add_argument("brief", nargs="?", type=Path, help="brief.json (check/save)")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="default: ET today")
    parser.add_argument("--out", type=Path, default=Path("outlook_manual"))
    parser.add_argument("--model", default="")
    args = parser.parse_args()
    as_of = args.as_of or _today_et()
    if args.command == "dump":
        dump(as_of, args.out)
        return 0
    if args.brief is None:
        parser.error("brief.json path required")
    ok = check(as_of, args.brief) if args.command == "check" else save(
        as_of, args.brief, args.model
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
