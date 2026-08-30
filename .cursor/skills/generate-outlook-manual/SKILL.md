---
name: generate-outlook-manual
description: Generate Outlook with Claude via Cursor for higher quality analysis. Use when automated Gemini output needs better reasoning, or when testing prompt changes.
---

# Generate Outlook Manually

Manual Outlook generation using Claude through Cursor. Use when you need superior reasoning on regime shifts, anomalies, or complex market narratives.

## When to Use

- Automated Gemini output was too generic
- High-severity anomalies detected (correlation breaks, z-score extremes)
- Regime classification changed (expansion → slowdown, etc.)
- Testing prompt changes before deployment
- Major market events requiring nuanced analysis

## Prerequisites

Evidence pack must exist for target date:

```bash
python -m jobs.build_pack
```

If pack is stale, refresh data first:

```bash
python -m jobs.ingest_yahoo
python -m jobs.ingest_fred
python -m jobs.compute_regime
python -m jobs.ingest_news
python -m jobs.ingest_fed_rss
python -m jobs.ingest_calendar
python -m jobs.build_pack
```

## Workflow

1. **Load evidence pack** from Postgres (latest for today or specified date)
2. **Display pack highlights** (regime, liquidity, anomalies, calendar)
3. **Generate Outlook** with Claude using `SYSTEM_PROMPT` from `agent/prompts.py`
4. **Validate citations** (no invented tickers, percents, or yields)
5. **Store in `outlook_report`** table (overwrites existing for same date)

## Implementation Steps

Execute the following Python code to generate the Outlook:

```python
from datetime import date
from agent.brief import OutlookBrief
from agent.outlook import user_prompt, render_markdown
from agent.prompts import SYSTEM_PROMPT, PROMPT_VERSION
from agent.citations import citation_issues, coverage_issues, validate_brief_fields
from store.engine import session_scope
from store.repos import latest_evidence_pack, upsert_outlook_report

# 1. Load evidence pack
target_date = date.today()  # or date.fromisoformat("2026-08-30")

with session_scope() as session:
    pack_row = latest_evidence_pack(session, target_date)
    if not pack_row:
        raise RuntimeError(f"No evidence pack for {target_date}. Run: python -m jobs.build_pack")
    pack = dict(pack_row.pack)
    pack_id = pack_row.id

# 2. Show pack highlights
print(f"📊 Evidence Pack: {pack['as_of']}")
if 'regime' in pack:
    r = pack['regime']
    print(f"   Regime: {r['growth']}/{r['inflation']}/{r['policy']}/{r['volatility']}")
    print(f"   Confidence: G={r['confidence']['growth']:.2f} I={r['confidence']['inflation']:.2f}")
if 'liquidity' in pack:
    liq = pack['liquidity']
    wow = liq.get('wow_change_bn')
    print(f"   Net Liquidity: ${liq['net_liquidity_bn']:.0f}B" + (f" (WoW {wow:+.0f}B)" if wow else ""))
if 'anomalies' in pack and pack['anomalies']:
    print(f"   Anomalies ({len(pack['anomalies'])}):")
    for a in pack['anomalies'][:3]:
        print(f"     • {a['description']} (severity: {a['severity']:.2f})")
print(f"   Sources: {len(pack.get('news', []))} news, {len(pack.get('events', []))} events")

# 3. Generate prompt
prompt = user_prompt(pack)
print(f"\n📝 System Prompt: {PROMPT_VERSION}")
print(f"📝 User Prompt: {len(prompt)} chars")
print("\n" + "="*80)
print("SYSTEM PROMPT:")
print("="*80)
print(SYSTEM_PROMPT[:500] + "...\n")
print("="*80)
print("USER PROMPT (evidence pack JSON):")
print("="*80)
print(prompt[:500] + "...\n")

# 4. Now call Claude via Cursor to generate OutlookBrief
# The agent will use the above SYSTEM_PROMPT and prompt
# and respond with structured JSON matching OutlookBrief schema

# 5. After Claude responds, parse and validate
# (This section will be filled by Claude's response)
```

## After Claude Generates

Once Claude returns the JSON, execute validation and storage:

```python
# Parse Claude's response into OutlookBrief
brief_json = {
    # Claude's JSON response here
}
brief = OutlookBrief.model_validate(brief_json)

# Render markdown
text = render_markdown(brief)

# Validate citations
issues = (
    citation_issues(pack, text) + 
    coverage_issues(pack, text) + 
    validate_brief_fields(brief_json)
)

if issues:
    print(f"❌ Validation failed: {', '.join(issues)}")
    print("\nFix these issues and regenerate.")
else:
    # Store in Postgres
    with session_scope() as session:
        upsert_outlook_report(
            session,
            as_of=target_date,
            model="cursor/claude-sonnet-4",
            prompt_version=PROMPT_VERSION,
            body_md=text,
            body_json=brief.model_dump(),
            pack_id=pack_id,
            status="ok"
        )
    print(f"✅ Outlook saved (pack_id: {pack_id}, model: cursor/claude-sonnet-4)")
    print(f"   View at: http://localhost:3000/outlook")
```

## Validation Rules

Same as automated job (`agent/citations.py`):

- **No invented tickers:** All tickers must exist in pack (tape, macro, or watchlist)
- **No invented percents:** All percentages must be from pack (change_pct, yoy_pct, implied_yes)
- **No invented yields:** All yield values must match pack (DGS2, DGS10, DGS30, etc.)
- **Required fields:** All brief fields must be present (use "unavailable" if data missing)
- **Coverage checks:** Spine series and judgment items must be mentioned

## Notes

- Uses Claude Sonnet 4 via Cursor subscription (no API key needed)
- Overwrites existing Outlook for the same date
- Markdown and JSON both stored in `outlook_report` table
- UI reads latest report for the date (manual overrides automated)
- Temperature: 0.2 (consistent with automated job)
- Max tokens: 4096 (same as automated)

## Comparison to Automated Job

| Aspect | Automated (Gemini) | Manual (Cursor) |
|--------|-------------------|-----------------|
| Model | gemini-2.5-flash | claude-sonnet-4 |
| Speed | 5-10 seconds | 15-30 seconds |
| Cost | $0.075/$0.30 per 1M tokens | Cursor subscription |
| Quality | Good for routine days | Superior for complex days |
| Iteration | No (one-shot) | Yes (can refine) |
| Unattended | Yes (cron/launchd) | No (manual trigger) |
| Streaming | No | Yes (see generation live) |

## Troubleshooting

**"No evidence pack for date"**
```bash
python -m jobs.build_pack --as-of YYYY-MM-DD
```

**Citation validation fails**
- Check pack JSON for the cited value
- Verify ticker exists in pack.macro, pack.header, pack.drivers
- Verify percent came from change_pct, yoy_pct, or implied_yes field

**Want to regenerate with same pack**
- Just run the skill again
- Latest Outlook overwrites previous for the same date

## See Also

- `agent/prompts.py` — system prompt and version
- `agent/brief.py` — OutlookBrief schema
- `agent/citations.py` — validation rules
- `jobs/generate_outlook.py` — automated job equivalent
