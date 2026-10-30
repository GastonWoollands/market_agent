"""Add news_item.summary for vendor-supplied article summaries (Finnhub).

Revision ID: 0018_news_item_summary
Revises: 0017_odds_snapshot_slot
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_news_item_summary"
down_revision: str | None = "0017_odds_snapshot_slot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("news_item", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("news_item", "summary")
