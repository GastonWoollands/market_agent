"""Add metric_ttm.cfo and metric_ttm.capex (TTM components of FCF).

Revision ID: 0019_metric_ttm_cfo_capex
Revises: 0018_news_item_summary
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_metric_ttm_cfo_capex"
down_revision: str | None = "0018_news_item_summary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("metric_ttm", sa.Column("cfo", sa.Numeric(20, 2), nullable=True))
    op.add_column("metric_ttm", sa.Column("capex", sa.Numeric(20, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("metric_ttm", "capex")
    op.drop_column("metric_ttm", "cfo")
