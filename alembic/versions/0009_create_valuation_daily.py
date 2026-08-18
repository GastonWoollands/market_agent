"""Create valuation_daily.

Revision ID: 0009_valuation_daily
Revises: 0008_metric_ttm
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_valuation_daily"
down_revision: str | None = "0008_metric_ttm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "valuation_daily",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("ev", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("ebitda", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("ev_ebitda", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("pctile_5y", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("ebitda_growth_1y", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("multiple_change_1y", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("comparable", sa.Boolean(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_valuation_daily_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_valuation_daily"),
    )
    op.create_index("ix_valuation_daily_as_of", "valuation_daily", ["as_of"])


def downgrade() -> None:
    op.drop_index("ix_valuation_daily_as_of", table_name="valuation_daily")
    op.drop_table("valuation_daily")
