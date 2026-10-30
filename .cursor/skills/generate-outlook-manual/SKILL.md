---
name: generate-outlook-manual
description: Generate the Outlook with the coding agent (Cursor or Claude Code) from the stored evidence pack. Use for the operator's manual morning/afternoon Outlook, when the automated SDK writer is off or too generic, or when testing prompt changes.
---

# Generate Outlook Manually

The coding agent writes the Outlook from the stored evidence pack. This is the one sanctioned
exception to the writer/coder split in `AGENTS.md`. Same rules as the SDK writer: narrate the
pack only, no web, no outside facts, and the citation gate must pass before saving.

Current operating mode: the SDK writer keys are off on purpose; the operator runs this skill
each weekday morning (pre-open) and afternoon (intraday or after the close).

## 1. Refresh data and build the pack

Run from the repo root with `.venv` active. Order matters: regime needs FRED, the pack needs all.

```bash
python -m jobs.ingest_yahoo                        # tape quotes + daily bars
python -m jobs.ingest_yahoo --universe watchlist   # default run is tape only
python -m jobs.ingest_fred
python -m jobs.compute_regime
python -m jobs.ingest_intraday                     # pre/post 5m bars -> extended_hours
python -m jobs.ingest_polymarket
python -m jobs.ingest_news
python -m jobs.ingest_fed_rss
python -m jobs.ingest_calendar
python -m jobs.build_pack
```

`build_pack` stamps `session.phase` from the ET clock (`pre_open`, `intraday`, `after_close`,
`closed`). Outside the cash session it also adds `extended_hours` (pre/post-market gaps vs the
last daily close), so build the pack after `ingest_intraday`.

If a job fails, say so to the operator and continue only if the pack still makes sense
(e.g. Finnhub down = no earnings rows; FRED down = stale macro).

## 2. Dump what the writer sees

```bash
H=.claude/skills/generate-outlook-manual/outlook_manual.py
python $H dump --out <scratchpad>/outlook
```

Writes `system.txt` (SYSTEM_PROMPT), `user.txt` (exact SDK user prompt) and `writer.json`,
and prints session phase, regime, the largest extended-hours gaps, headline categories and
anomalies. Read `system.txt` and `user.txt` in full before writing.

## 3. Write `brief.json`

Write the `OutlookBrief` JSON (`agent/brief.py`) following `system.txt` exactly. Checklist:

- **Timing:** `pre_open` = last session is the story and `extended_hours` is the overnight
  reaction (lead with big gaps, e.g. post-earnings); `intraday` = say "so far today";
  `after_close` = today's full session plus post-market gaps.
- **World:** use the headlines (one per category) for central banks, energy, fiscal, FX and
  corporate news in `drivers` and `geopolitical_deep`. Headline numbers are not citable unless
  the same value is elsewhere in the pack.
- **Rates:** `yields_live` for today's move (bp), FRED DGS* for curve facts with `as_of`.
- **Dollar:** DXY for today, DTWEXBGS only with its `as_of`; never compare levels.
- Every ticker and percent must be a pack value at the written precision.

## 4. Check and save

```bash
python $H check <scratchpad>/outlook/brief.json
python $H save  <scratchpad>/outlook/brief.json --model manual/<agent-model>
```

`check` runs `citation_issues` + `coverage_issues` + `validate_brief_fields`; `save` reruns them
and refuses on any issue, then `upsert_outlook_report` (overwrites the same `as_of`) with
`PROMPT_VERSION` and the pack id. Stamp the real author, e.g. `manual/claude-opus-5-5`.
`--as-of YYYY-MM-DD` targets another pack date (default: today in ET).

Common issues:

- `pct:X%` — percent not in the pack at that precision; copy the pack value.
- `ticker:X` — word read as a ticker; rephrase or use a pack ticker.
- `coverage:CPIAUCSL` — mention CPI with its `yoy_pct`.
- `watch_today:generic_outcome` — each bullish outcome must name a market (2Y, equities,
  dollar, odds, credit, VIX...).

## 5. Report to the operator

Summarize in the operator's language: what happened, positioning, what to expect, the
invalidation line, and any data gaps (failed jobs, stale series). The UI shows the report on
`/outlook` once the API runs (`make api`, port 8000; web on 3000 or the next free port).
