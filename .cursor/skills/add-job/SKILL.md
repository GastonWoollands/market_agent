---
name: add-job
description: Adds a market_agent CLI job with job_run tracking, argparse, Makefile, and pipelines.md entry. Use when adding a job, cron, ingest CLI, compute job, or python -m jobs module.
---

# Add job

Jobs are the only writers of market data. One module per schedule entry.

## Template

- Long/resumable vendor pulls: `jobs/ingest_yahoo.py` (`tracked_job` so `/health` shows `running`).
- Short compute/LLM: `jobs/ingest_fred.py` or `jobs/generate_outlook.py` (`record_job` on finish is OK).
- Prefer `tracked_job` for new vendor ingest.

```python
from jobs.runtime import tracked_job

def main() -> None:
    parser = argparse.ArgumentParser(description="...")
    # flags only
    with tracked_job("ingest_foo") as run:
        result = ingest(...)
        run.rows = result["rows"]
        run.extra = result
```

## Steps

1. `jobs/<name>.py` with `JOB_NAME`, `ingest`/`compute` function, `main()`, `if __name__ == "__main__"`.
2. Idempotent writes via `store/repos.py` upserts. Optional `--resume` skips names that already have rows.
3. `pyproject.toml`: console script `market-<short> = "jobs.<name>:main"` if other jobs have one.
4. `Makefile` target + `.PHONY`.
5. Row in `docs/pipelines.md` §5 (writes + flags) and the first-load table if operators must run it.
6. Test the dry path (parse/upsert unit tests). Do not hit vendors in pytest.

Do not call vendors from FastAPI routes. Do not skip `job_run`.
