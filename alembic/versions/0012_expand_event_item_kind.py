"""Expand event_item.kind for macro calendar.

Revision ID: 0012_event_kinds
Revises: 0011_bar_intraday
Create Date: 2026-08-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_event_kinds"
down_revision: str | None = "0011_bar_intraday"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_KINDS = (
    "kind IN ('fomc', 'cpi', 'pce', 'nfp', 'gdp', 'jolts', 'earnings', "
    "'election', 'central_bank', 'other')"
)
OLD_KINDS = "kind IN ('fomc', 'cpi', 'earnings', 'election', 'other')"


def _replace_kind_check(sql: str) -> None:
    op.execute("ALTER TABLE event_item DROP CONSTRAINT IF EXISTS ck_event_item_kind")
    op.execute(
        "ALTER TABLE event_item DROP CONSTRAINT IF EXISTS ck_event_item_ck_event_item_kind"
    )
    op.execute(f"ALTER TABLE event_item ADD CONSTRAINT ck_event_item_kind CHECK ({sql})")


def upgrade() -> None:
    _replace_kind_check(NEW_KINDS)


def downgrade() -> None:
    _replace_kind_check(OLD_KINDS)
