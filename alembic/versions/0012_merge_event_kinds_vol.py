"""Merge event-kind 0012 with the options-branch vol 0012 id.

Revision ID: 0012_merge_kinds_vol
Revises: 0012_event_kinds, 0012_vol_snapshot_yield
Create Date: 2026-08-29
"""

from collections.abc import Sequence

revision: str = "0012_merge_kinds_vol"
down_revision: tuple[str, str] = ("0012_event_kinds", "0012_vol_snapshot_yield")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    return


def downgrade() -> None:
    return
