"""Create policy_item for official Fed Board RSS.

Revision ID: 0014_policy_item
Revises: 0013_event_kinds_policy
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_policy_item"
down_revision: str | None = "0013_event_kinds_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_item",
        sa.Column("guid", sa.String(length=512), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("speaker", sa.String(length=128)),
        sa.Column("excerpt", sa.Text()),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "kind IN ('speech', 'statement', 'minutes', 'testimony')",
            name="ck_policy_item_kind",
        ),
        sa.PrimaryKeyConstraint("guid", name="pk_policy_item"),
    )
    op.create_index("ix_policy_item_published_at", "policy_item", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_policy_item_published_at", table_name="policy_item")
    op.drop_table("policy_item")
