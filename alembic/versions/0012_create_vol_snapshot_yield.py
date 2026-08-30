"""Bridge the options-branch 0012 id so this tree has one head.

Revision ID: 0012_vol_snapshot_yield
Revises: 0011_bar_intraday
Create Date: 2026-08-20

The options branch created `vol_snapshot` / `instrument_yield` under this
revision id, then that file left the tree. This branch does not own those
tables. Upgrade is a no-op so `alembic upgrade head` can merge into
`0012_event_kinds` and apply policy calendar migrations.
"""

from collections.abc import Sequence

revision: str = "0012_vol_snapshot_yield"
down_revision: str | None = "0011_bar_intraday"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    return


def downgrade() -> None:
    return
