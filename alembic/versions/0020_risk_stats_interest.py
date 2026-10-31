"""Add risk_stats and metric_ttm.ebit / metric_ttm.interest_expense.

Revision ID: 0020_risk_stats_interest
Revises: 0019_metric_ttm_cfo_capex
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_risk_stats_interest"
down_revision: str | None = "0019_metric_ttm_cfo_capex"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("metric_ttm", sa.Column("ebit", sa.Numeric(20, 2), nullable=True))
    op.add_column("metric_ttm", sa.Column("interest_expense", sa.Numeric(20, 2), nullable=True))
    op.create_table(
        "risk_stats",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("vol_3m", sa.Numeric(12, 6), nullable=True),
        sa.Column("vol_1y", sa.Numeric(12, 6), nullable=True),
        sa.Column("downside_vol_1y", sa.Numeric(12, 6), nullable=True),
        sa.Column("beta_spy", sa.Numeric(12, 6), nullable=True),
        sa.Column("beta_qqq", sa.Numeric(12, 6), nullable=True),
        sa.Column("corr_spy", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_drawdown_1y", sa.Numeric(12, 6), nullable=True),
        sa.Column("drawdown", sa.Numeric(12, 6), nullable=True),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_risk_stats_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_risk_stats"),
    )


def downgrade() -> None:
    op.drop_table("risk_stats")
    op.drop_column("metric_ttm", "interest_expense")
    op.drop_column("metric_ttm", "ebit")
