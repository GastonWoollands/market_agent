from datetime import UTC, datetime
from typing import Any

from store.engine import session_scope
from store.models import JobRun


def record_job(
    job_name: str,
    *,
    status: str,
    rows_written: int,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        session.add(
            JobRun(
                job_name=job_name,
                started_at=now,
                finished_at=now,
                status=status,
                rows_written=rows_written,
                error=error,
                extra=extra,
            )
        )
