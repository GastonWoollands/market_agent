"""Expand event_item.kind for policy calendar (speech, minutes, Beige Book, ISM, Treasury).

Revision ID: 0013_event_kinds_policy
Revises: 0012_merge_kinds_vol
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_event_kinds_policy"
down_revision: str | None = "0012_merge_kinds_vol"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_KINDS = (
    "kind IN ('fomc', 'cpi', 'pce', 'nfp', 'gdp', 'jolts', 'earnings', "
    "'election', 'central_bank', 'speech', 'minutes', 'beige_book', "
    "'ism', 'treasury', 'other')"
)
OLD_KINDS = (
    "kind IN ('fomc', 'cpi', 'pce', 'nfp', 'gdp', 'jolts', 'earnings', "
    "'election', 'central_bank', 'other')"
)


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
