"""Create metric_fy and quant_score.

Revision ID: 0016_metric_fy_quant
Revises: 0015_create_regime_snapshot
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016_metric_fy_quant"
down_revision: str | None = "0015_create_regime_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metric_fy",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("net_income", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("cfo", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("gross_profit", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("ebit", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("total_assets", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("current_assets", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("current_liabilities", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("long_term_debt", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("total_liabilities", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("retained_earnings", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("equity", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("shares", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_metric_fy_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_metric_fy"),
    )
    op.create_index("ix_metric_fy_fiscal_year", "metric_fy", ["fiscal_year"])
    op.create_table(
        "quant_score",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("fy_as_of", sa.Date(), nullable=True),
        sa.Column("f_score", sa.Integer(), nullable=True),
        sa.Column("z_score", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("z_inapplicable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("market_cap", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("revenue_growth_yoy", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("fcf_yield", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("debt_to_equity", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("is_gem_candidate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("f_tests", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("z_components", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "f_score IS NULL OR (f_score >= 0 AND f_score <= 9)",
            name="ck_quant_score_f_score",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_quant_score_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_quant_score"),
    )
    op.create_index("ix_quant_score_gem", "quant_score", ["as_of", "is_gem_candidate"])


def downgrade() -> None:
    op.drop_index("ix_quant_score_gem", table_name="quant_score")
    op.drop_table("quant_score")
    op.drop_index("ix_metric_fy_fiscal_year", table_name="metric_fy")
    op.drop_table("metric_fy")
