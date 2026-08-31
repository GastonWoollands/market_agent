# Generate Outlook Manually (Cursor Skill)

High-quality Outlook generation using Claude Sonnet 4 via Cursor.

## Quick Start

```
# In Cursor Chat
/generate-outlook-manual
```

## When to Use

**Use manual generation (20% of days) when:**
- ✅ Automated Gemini output was too generic
- ✅ High-severity anomalies detected (>0.7 severity score)
- ✅ Regime classification changed (e.g., expansion → slowdown)
- ✅ Complex cross-asset narratives (DXY transmission, carry unwinds)
- ✅ Testing prompt changes before deployment

**Use automated Gemini (80% of days) when:**
- ✅ Normal market day with routine updates
- ✅ Running unattended (cron/launchd)
- ✅ Speed matters (5-10 seconds vs 15-30 seconds)

## Prerequisites

Evidence pack must exist:

```bash
# Check if pack exists
python -c "from store.engine import session_scope; from store.repos import latest_evidence_pack; from datetime import date; with session_scope() as s: print(latest_evidence_pack(s, date.today()))"

# If None, build pack
make pack
```

## Example Usage

### Scenario 1: Review Then Generate

```
User: /generate-outlook-manual

Agent: [Shows pack highlights with regime, liquidity, anomalies]
       [Displays system prompt and evidence pack size]
       [Generates Outlook with Claude]
       [Validates citations]
       [Saves to Postgres]

Agent: ✅ Outlook saved (pack_id: 1234, model: cursor/claude-sonnet-4)
```

### Scenario 2: Iterate on Narrative

```
User: /generate-outlook-manual

Agent: [Generates initial Outlook]

User: The liquidity analysis is too shallow. Focus more on RRP drawdown from $500B.

Agent: [Regenerates with emphasis on RRP drawdown]
       [Updates outlook_report]
```

### Scenario 3: Test Prompt Change

```bash
# 1. Edit agent/prompts.py
# 2. Bump PROMPT_VERSION (e.g., outlook-v12 → outlook-v13)
```

```
User: /generate-outlook-manual

Agent: 📝 System Prompt: outlook-v13
       [Generates with new prompt]
       [Validates]
```

## Output Location

**Database:**
```sql
SELECT as_of, model, status, prompt_version
FROM outlook_report
WHERE as_of = CURRENT_DATE
ORDER BY created_at DESC
LIMIT 1;
```

**UI:**
http://localhost:3000/outlook

UI always displays latest report for the date.

## Comparison: Automated vs Manual

| Aspect | Automated (Gemini) | Manual (Cursor) |
|--------|-------------------|-----------------|
| Command | `make outlook` | `/generate-outlook-manual` |
| Model | gemini-2.5-flash | claude-sonnet-4 |
| Speed | 5-10 sec | 15-30 sec |
| Quality | Good | Superior |
| Iteration | No | Yes |
| Unattended | Yes | No |
| Cost | ~$0.01/run | Cursor subscription |

## Troubleshooting

### "No evidence pack for date"

```bash
make pack --as-of YYYY-MM-DD
```

### Citation Validation Fails

Check the error message for specific issues:

- **"ticker:TSLA"** → Invented ticker. Only use tickers from pack.
- **"pct:99.9%"** → Invented percent. Use `change_pct`, `yoy_pct`, `implied_yes`.
- **"DGS10:5.5"** → Invented yield. Use exact value from pack.

Fix in the generated JSON and regenerate.

### Want Different Date

```python
# In the skill execution, change:
target_date = date.fromisoformat("2026-08-30")
```

### Compare to Automated Output

```sql
-- Show both versions
SELECT 
  as_of,
  model,
  prompt_version,
  status,
  created_at
FROM outlook_report
WHERE as_of = '2026-08-30'
ORDER BY created_at;
```

## Architecture

```
Evidence Pack (JSONB)
       ↓
   SYSTEM_PROMPT (agent/prompts.py)
       ↓
   USER_PROMPT (writer_pack JSON)
       ↓
   Claude Sonnet 4 (via Cursor)
       ↓
   OutlookBrief (structured JSON)
       ↓
   Citation Validation
       ↓
   outlook_report table
       ↓
   UI (Next.js)
```

## Best Practices

1. **Review pack highlights before generation** — Understand regime, anomalies, liquidity
2. **Check citation errors immediately** — Fix and regenerate if validation fails
3. **Compare to automated output** — Learn when manual adds value
4. **Document why you override** — Comment in git commit or notes
5. **Bump PROMPT_VERSION** — When testing prompt changes

## Related Files

- `.cursor/skills/generate-outlook-manual/SKILL.md` — Full skill documentation
- `agent/prompts.py` — SYSTEM_PROMPT and PROMPT_VERSION
- `agent/brief.py` — OutlookBrief schema
- `agent/citations.py` — Validation rules
- `jobs/generate_outlook.py` — Automated equivalent
- `docs/pipelines.md` — Pipeline documentation

## Support

Questions? Check:
1. SKILL.md (detailed implementation steps)
2. `docs/pipelines.md` §4 (Outlook generation strategy)
3. `docs/northstar.md` §10.1 (Narrative structure requirements)
