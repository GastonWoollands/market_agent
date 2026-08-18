from collections.abc import Iterator
from contextlib import contextmanager
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


def begin_job(job_name: str) -> int:
    now = datetime.now(UTC)
    with session_scope() as session:
        row = JobRun(
            job_name=job_name,
            started_at=now,
            finished_at=None,
            status="running",
            rows_written=0,
        )
        session.add(row)
        session.flush()
        return int(row.id)


def finish_job(
    run_id: int,
    *,
    status: str,
    rows_written: int,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        row = session.get(JobRun, run_id)
        if row is None:
            return
        row.status = status
        row.finished_at = now
        row.rows_written = rows_written
        row.error = error
        row.extra = extra


class JobTracker:
    def __init__(self, job_name: str) -> None:
        self.job_name = job_name
        self.run_id = begin_job(job_name)
        self.rows = 0
        self.extra: dict[str, Any] | None = None
        self.closed = False

    def succeed(self, rows: int | None = None, extra: dict[str, Any] | None = None) -> None:
        if self.closed:
            return
        finish_job(
            self.run_id,
            status="ok",
            rows_written=self.rows if rows is None else rows,
            extra=extra if extra is not None else self.extra,
        )
        self.closed = True

    def fail(
        self,
        error: str,
        rows: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self.closed:
            return
        finish_job(
            self.run_id,
            status="error",
            rows_written=self.rows if rows is None else rows,
            error=error,
            extra=extra if extra is not None else self.extra,
        )
        self.closed = True


@contextmanager
def tracked_job(job_name: str) -> Iterator[JobTracker]:
    run = JobTracker(job_name)
    try:
        yield run
    except Exception as exc:
        run.fail(str(exc))
        raise
    else:
        if not run.closed:
            run.succeed()
