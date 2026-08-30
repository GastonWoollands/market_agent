# Outlook Generation Strategy: Hybrid Approach

## Executive Summary

Market Agent now supports **two methods** for generating the daily Outlook brief:

1. **Automated (Gemini)** — Default, fast, unattended (80% of days)
2. **Manual (Cursor)** — High-quality override with Claude Sonnet 4 (20% of days)

Both methods write to the same `outlook_report` table. The UI displays the latest report for each date.

---

## Architecture

```
Evidence Pack (Postgres)
       ↓
   ┌────────────────────────────────────────┐
   │  Two Generation Paths                  │
   ├────────────────────────────────────────┤
   │                                        │
   │  Automated (Gemini)    Manual (Cursor)│
   │  ──────────────────    ───────────────│
   │                                        │
   │  python -m jobs.       /generate-     │
   │  generate_outlook      outlook-manual │
   │        ↓                      ↓        │
   │  Gemini 2.5 Flash     Claude Sonnet 4 │
   │  (5-10 sec, $0.01)    (15-30 sec, $0) │
   │        ↓                      ↓        │
   └────────────────────────────────────────┘
                   ↓
            outlook_report
                   ↓
            UI (Next.js)
```

---

## Method 1: Automated (Gemini) — Default

### Command

```bash
python -m jobs.generate_outlook
```

Or via Makefile:
```bash
make outlook
```

### Configuration

In `.env` or environment:
```bash
# Default: Gemini
AGENT_PROVIDER=gemini
AGENT_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your-key-here

# Or use Claude via API
AGENT_PROVIDER=anthropic
AGENT_MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=your-key-here
```

### Characteristics

| Aspect | Details |
|--------|---------|
| Model | `gemini-2.5-flash` (default) |
| Speed | 5-10 seconds |
| Cost | ~$0.01 per run |
| Quality | Good for routine analysis |
| Iteration | No (one-shot) |
| Unattended | Yes (cron/launchd) |
| Fallback | Template if API fails |

### When to Use

✅ Normal market days with routine updates  
✅ Running unattended (overnight/early morning)  
✅ Speed matters  
✅ Cost-sensitive environments  

### Daily Workflow

```bash
#!/bin/bash
# Morning automation script
cd /path/to/market_agent
source .venv/bin/activate

# Data pipeline
python -m jobs.ingest_yahoo
python -m jobs.ingest_fred
python -m jobs.compute_regime
python -m jobs.ingest_news
python -m jobs.ingest_fed_rss
python -m jobs.ingest_calendar
python -m jobs.build_pack

# Generate Outlook (automated)
python -m jobs.generate_outlook

# Result: outlook_report with model="gemini/gemini-2.5-flash"
```

---

## Method 2: Manual (Cursor Skill) — High Quality

### Command

In Cursor Chat:
```
/generate-outlook-manual
```

Or via Makefile reminder:
```bash
make outlook-manual
# Displays: "In Cursor Chat, run: /generate-outlook-manual"
```

### Characteristics

| Aspect | Details |
|--------|---------|
| Model | `claude-sonnet-4` (via Cursor) |
| Speed | 15-30 seconds (with streaming) |
| Cost | Included in Cursor subscription |
| Quality | Superior reasoning and nuance |
| Iteration | Yes (can refine narrative) |
| Unattended | No (requires manual trigger) |
| Fallback | N/A (manual operation) |

### When to Use

✅ High-severity anomalies detected (>0.7 severity)  
✅ Regime classification changed (expansion → slowdown)  
✅ Complex cross-asset narratives (carry unwinds, correlation breaks)  
✅ Automated Gemini output was too generic  
✅ Testing prompt changes before deployment  

### Workflow

1. **Verify pack exists:**
   ```bash
   make pack
   ```

2. **Invoke skill in Cursor Chat:**
   ```
   /generate-outlook-manual
   ```

3. **Agent will:**
   - Load latest evidence pack from Postgres
   - Display pack highlights (regime, liquidity, anomalies)
   - Show system prompt and evidence pack size
   - Generate Outlook with Claude Sonnet 4
   - Validate citations (no invented data)
   - Store in `outlook_report` table

4. **Result:**
   ```
   ✅ Outlook saved (pack_id: 1234, model: cursor/claude-sonnet-4)
   ```

### Iteration Example

```
User: /generate-outlook-manual

Agent: [Generates Outlook]

User: The liquidity analysis is too shallow. Focus more on RRP drawdown.

Agent: [Regenerates with emphasis on RRP drawdown]
       [Updates outlook_report]
```

---

## Decision Tree

```
Morning Arrives
      ↓
┌─────────────────────┐
│ Run automated job?  │
└─────────────────────┘
      ↓ YES (default)
make outlook
      ↓
┌──────────────────────────┐
│ Review output in UI      │
└──────────────────────────┘
      ↓
┌────────────────────┐
│ Quality sufficient?│
└────────────────────┘
 ↓ YES        ↓ NO
Done    /generate-outlook-manual
               ↓
        Claude regenerates
               ↓
             Done
```

---

## Database Schema

Both methods write to the same table:

```sql
CREATE TABLE outlook_report (
    id BIGSERIAL PRIMARY KEY,
    as_of DATE NOT NULL UNIQUE,
    model TEXT NOT NULL,                -- "gemini/..." or "cursor/..."
    prompt_version TEXT NOT NULL,       -- "outlook-v12"
    body_md TEXT NOT NULL,              -- Rendered markdown
    body_json JSONB NOT NULL,           -- Structured brief
    pack_id BIGINT REFERENCES evidence_pack(id),
    status TEXT NOT NULL,               -- "ok", "fallback", "error"
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Example Queries

**Check today's Outlook method:**
```sql
SELECT as_of, model, status, prompt_version, created_at
FROM outlook_report
WHERE as_of = CURRENT_DATE;
```

**Compare last 7 days by method:**
```sql
SELECT 
    as_of,
    CASE 
        WHEN model LIKE 'cursor/%' THEN 'Manual (Cursor)'
        WHEN model LIKE 'gemini/%' THEN 'Automated (Gemini)'
        WHEN model LIKE 'anthropic/%' THEN 'Automated (Claude API)'
        ELSE 'Template Fallback'
    END as method,
    prompt_version,
    status
FROM outlook_report
WHERE as_of >= CURRENT_DATE - 7
ORDER BY as_of DESC;
```

---

## Quality Comparison

### Automated (Gemini)

**Strengths:**
- Fast generation (5-10 seconds)
- Runs unattended (cron/launchd)
- Cheap (~$0.01 per run)
- Good for routine market days
- Template fallback if API fails

**Weaknesses:**
- Generic analysis on complex days
- Cannot iterate on narrative
- May miss nuanced regime implications

**Best for:** 80% of days (normal markets, routine updates)

### Manual (Cursor)

**Strengths:**
- Superior reasoning (Claude Sonnet 4)
- Can iterate and refine
- Better regime/anomaly interpretation
- Free (Cursor subscription)
- Real-time streaming

**Weaknesses:**
- Requires manual trigger
- Slower (15-30 seconds)
- Cannot run unattended
- No template fallback

**Best for:** 20% of days (regime shifts, anomalies, complex narratives)

---

## Integration Points

### Phase 1 Analytics (Regime, Liquidity, Anomalies)

Both methods have access to:

```json
{
  "regime": {
    "growth": "expansion",
    "inflation": "stable",
    "policy": "neutral",
    "volatility": "suppressed",
    "confidence": {
      "growth": 0.85,
      "inflation": 0.75,
      "policy": 0.70,
      "volatility": 0.85
    }
  },
  "liquidity": {
    "net_liquidity_bn": 6400.0,
    "wow_change_bn": 80.0,
    "components": {...}
  },
  "anomalies": [
    {
      "type": "breadth_divergence",
      "description": "SPY +0.6% while RSP -0.4%, IWM -0.7%",
      "severity": 0.60
    }
  ]
}
```

**Manual skill advantage:** Claude better interprets regime transitions and high-severity anomalies.

### Prompt Engineering

Both use the same `SYSTEM_PROMPT` from `agent/prompts.py` (version: `outlook-v12`).

Manual skill allows testing prompt changes before committing:
1. Edit `agent/prompts.py`
2. Bump `PROMPT_VERSION`
3. Run `/generate-outlook-manual` to test
4. Commit if satisfied

---

## Usage Statistics (Recommended)

Track method usage to optimize strategy:

```sql
-- Method distribution last 30 days
SELECT 
    CASE 
        WHEN model LIKE 'cursor/%' THEN 'Manual'
        ELSE 'Automated'
    END as method,
    COUNT(*) as days,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) as pct
FROM outlook_report
WHERE as_of >= CURRENT_DATE - 30
GROUP BY 1;
```

**Target:** ~80% automated, ~20% manual override

---

## Troubleshooting

### "No evidence pack for date"

```bash
# Build pack for today
make pack

# Or specific date
python -m jobs.build_pack --as-of 2026-08-30
```

### Citation validation fails

Common errors:
- **"ticker:TSLA"** → Invented ticker. Only use tickers from pack.
- **"pct:99.9%"** → Invented percent. Use `change_pct`, `yoy_pct`, `implied_yes`.
- **"DGS10:5.5"** → Invented yield. Use exact value from pack.

Fix and regenerate.

### Want to compare outputs

Generate with both methods:
```bash
# Automated
make outlook

# Manual override
/generate-outlook-manual
```

Query to compare:
```sql
SELECT model, LENGTH(body_md) as chars, status
FROM outlook_report
WHERE as_of = CURRENT_DATE
ORDER BY created_at;
```

---

## Files and Documentation

### Skill Implementation
- `.cursor/skills/generate-outlook-manual/SKILL.md` — Full skill spec
- `.cursor/skills/generate-outlook-manual/README.md` — Usage guide
- `tests/test_outlook_manual_skill.py` — Validation tests

### Core System
- `agent/prompts.py` — SYSTEM_PROMPT and PROMPT_VERSION
- `agent/outlook.py` — Generation logic (used by both methods)
- `agent/brief.py` — OutlookBrief schema
- `agent/citations.py` — Validation rules
- `jobs/generate_outlook.py` — Automated job

### Documentation
- `docs/pipelines.md` — Pipeline workflow (§4: Outlook generation strategy)
- `docs/system.md` — System map (updated with hybrid approach)
- `docs/northstar.md` — Product contract (§10.1: Narrative structure)
- `IMPLEMENTATION_PHASE1.md` — Phase 1 analytics implementation
- `OUTLOOK_GENERATION_STRATEGY.md` — This document

---

## Best Practices

### For Operators

1. **Default to automated** — Use Gemini for routine days
2. **Monitor pack highlights** — Check regime/anomalies after `build_pack`
3. **Override when needed** — Use manual skill for complex days
4. **Document overrides** — Note why you chose manual in git commits
5. **Track usage** — Review method distribution monthly

### For Developers

1. **Test prompts with manual skill** — Safer than automated deployment
2. **Bump PROMPT_VERSION** — Always increment on prompt changes
3. **Add citation tests** — For any new validation rules
4. **Preserve both paths** — Don't optimize away either method
5. **Monitor quality** — Compare manual vs automated on same days

### For AI Engineers

1. **Improve automated first** — 80% of days should be good enough
2. **Enhance regime interpretation** — Help both methods leverage Phase 1 data
3. **Document edge cases** — When manual consistently outperforms
4. **Experiment with Cursor** — Manual skill is sandbox for prompts
5. **Measure quality delta** — Quantify manual vs automated improvement

---

## Success Metrics

### Quantitative
- **Automated success rate:** >95% (no citation failures)
- **Manual usage:** 15-25% of days
- **Generation time:** <10s automated, <30s manual
- **Cost:** <$0.50 per day total

### Qualitative
- Operators can identify when manual override needed
- Manual skill used proactively (not as backup)
- Prompt changes tested with manual before deployment
- Quality gap between methods understood and documented

---

## Roadmap

### Near-term (Implemented)
- ✅ Cursor skill for manual generation
- ✅ Phase 1 analytics (regime, liquidity, anomalies)
- ✅ Documentation and tests
- ✅ Makefile integration

### Short-term (Next)
- [ ] Automated anomaly alerts (suggest manual review)
- [ ] Quality scoring (compare manual vs automated)
- [ ] Usage dashboard (method distribution, timing)

### Long-term (Future)
- [ ] Hybrid mode (Gemini draft → Claude polish)
- [ ] Auto-route to manual (if anomalies >0.7)
- [ ] A/B testing framework
- [ ] Fine-tune Gemini on manual outputs

---

## Summary

The hybrid approach gives you:

1. **Reliability** — Automated Gemini for daily baseline
2. **Quality** — Manual Claude for complex days
3. **Flexibility** — Choose method based on market conditions
4. **Cost-effectiveness** — Use expensive model only when needed
5. **Experimentation** — Test prompts safely with manual skill

**80/20 rule:** Automated handles most days, manual elevates the rest.

**Result:** Professional-grade Outlook analysis with operational flexibility.
