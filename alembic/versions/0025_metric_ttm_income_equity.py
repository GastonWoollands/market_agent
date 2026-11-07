"""Add metric_ttm.net_income and metric_ttm.equity (P/E, P/B, ROE for banks).

Revision ID: 0025_metric_ttm_income_equity
Revises: 0024_short_interest_revisions
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_metric_ttm_income_equity"
down_revision: str | None = "0024_short_interest_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("metric_ttm", sa.Column("net_income", sa.Numeric(20, 2), nullable=True))
    op.add_column("metric_ttm", sa.Column("equity", sa.Numeric(20, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("metric_ttm", "equity")
    op.drop_column("metric_ttm", "net_income")
