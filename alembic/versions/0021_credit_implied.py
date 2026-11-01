"""Add credit_implied, credit_anchor and balance-sheet liabilities on metric_ttm.

Revision ID: 0021_credit_implied
Revises: 0020_risk_stats_interest
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_credit_implied"
down_revision: str | None = "0020_risk_stats_interest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("current_liabilities", "total_liabilities", "deferred_revenue_current"):
        op.add_column("metric_ttm", sa.Column(column, sa.Numeric(20, 2), nullable=True))
    op.create_table(
        "credit_implied",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("statement_as_of", sa.Date(), nullable=False),
        sa.Column("market_cap", sa.Numeric(20, 2), nullable=False),
        sa.Column("default_point", sa.Numeric(20, 2), nullable=False),
        sa.Column("vol_equity", sa.Numeric(12, 6), nullable=False),
        sa.Column("asset_value", sa.Numeric(20, 2), nullable=False),
        sa.Column("vol_asset", sa.Numeric(12, 6), nullable=False),
        sa.Column("risk_free", sa.Numeric(10, 6), nullable=False),
        sa.Column("dd", sa.Numeric(12, 4), nullable=False),
        sa.Column("bucket", sa.String(4), nullable=False),
        sa.Column("position", sa.String(8), nullable=False),
        sa.Column("bucket_oas_bp", sa.Numeric(10, 1), nullable=True),
        sa.Column("calibration_version", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_credit_implied_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_credit_implied"),
    )
    op.create_table(
        "credit_anchor",
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("bucket", sa.String(4), nullable=False),
        sa.Column("median_dd", sa.Numeric(12, 4), nullable=False),
        sa.Column("names", sa.Integer(), nullable=False),
        sa.Column("oas_bp", sa.Numeric(10, 1), nullable=True),
        sa.Column("calibration_version", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("as_of", "bucket", name="pk_credit_anchor"),
    )


def downgrade() -> None:
    op.drop_table("credit_anchor")
    op.drop_table("credit_implied")
    for column in ("deferred_revenue_current", "total_liabilities", "current_liabilities"):
        op.drop_column("metric_ttm", column)
