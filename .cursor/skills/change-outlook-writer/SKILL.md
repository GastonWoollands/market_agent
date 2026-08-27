---
name: change-outlook-writer
description: Changes Outlook brief or opportunity memo prompts, citation checks, or pack-grounded generation. Use when editing Outlook, memos, SYSTEM_PROMPT, citations, evidence pack narration, or agent/prompts.py.
---

# Change Outlook / memo writer

The model only narrates the evidence pack. It must not gain tools, web search, or live fetches.

## Where to edit

| Change | File |
|---|---|
| Outlook voice / rules | `agent/prompts.py` (`SYSTEM_PROMPT`) |
| Outlook version stamp | `PROMPT_VERSION` in the same file (bump on any prompt change) |
| Memo voice / schema | `agent/memos.py` (`MEMO_SYSTEM`, `OpportunityMemo`, `MEMO_PROMPT_VERSION`) |
| Citation gate | `agent/citations.py` |
| Pack shape | `agent/pack.py` (Python only; the model does not compute) |
| Provider wiring | `agent/providers.py` (`anthropic` / `google-genai` only) |

## Rules that stay true

- Temperature low; structured JSON out.
- Missing field → write `unavailable`. No invented tickers, percents, or yields.
- Not a trading signal. No buy/sell/hold. No price targets.
- On citation failure: Outlook keeps yesterday’s report; memos skip that name.
- Template fallback when the SDK is down (`--template` or missing key).

## Verify

Run `pytest tests/test_outlook_agent.py tests/test_memos.py tests/test_outlook.py`.
Add a case for any new invented-ticker or invented-percent pattern you just forbade.
