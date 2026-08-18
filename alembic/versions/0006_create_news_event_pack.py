"""Create news_item, event_item, evidence_pack.

Revision ID: 0006_news_event_pack
Revises: 0005_rrg_return_stats
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_news_event_pack"
down_revision: str | None = "0005_rrg_return_stats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "news_item",
        sa.Column("guid", sa.String(length=512), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("guid", name="pk_news_item"),
    )
    op.create_index("ix_news_item_category", "news_item", ["category"])
    op.create_index("ix_news_item_published_at", "news_item", ["published_at"])
    op.create_table(
        "event_item",
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "kind IN ('fomc', 'cpi', 'earnings', 'election', 'other')",
            name="ck_event_item_kind",
        ),
        sa.PrimaryKeyConstraint("slug", name="pk_event_item"),
    )
    op.create_index("ix_event_item_date", "event_item", ["date"])
    op.create_table(
        "evidence_pack",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("pack", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_pack"),
        sa.UniqueConstraint("as_of", name="uq_evidence_pack_as_of"),
    )


def downgrade() -> None:
    op.drop_table("evidence_pack")
    op.drop_index("ix_event_item_date", table_name="event_item")
    op.drop_table("event_item")
    op.drop_index("ix_news_item_published_at", table_name="news_item")
    op.drop_index("ix_news_item_category", table_name="news_item")
    op.drop_table("news_item")
