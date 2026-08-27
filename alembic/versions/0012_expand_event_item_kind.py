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


def upgrade() -> None:
    op.drop_constraint("ck_event_item_kind", "event_item", type_="check")
    op.create_check_constraint("ck_event_item_kind", "event_item", NEW_KINDS)


def downgrade() -> None:
    op.drop_constraint("ck_event_item_kind", "event_item", type_="check")
    op.create_check_constraint("ck_event_item_kind", "event_item", OLD_KINDS)
