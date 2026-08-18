"""Create opportunity_score and opportunity_memo.

Revision ID: 0010_opportunity
Revises: 0009_valuation_daily
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_opportunity"
down_revision: str | None = "0009_valuation_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "opportunity_score",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("total", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("cheap", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("quality", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("change", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("setup", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("insider", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("risk", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("trap", sa.Boolean(), nullable=False),
        sa.Column("fcf_margin", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("ret_3m", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_opportunity_score_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_opportunity_score"),
    )
    op.create_index("ix_opportunity_score_rank", "opportunity_score", ["as_of", "rank"])
    op.create_table(
        "opportunity_memo",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("why_scored", sa.Text(), nullable=False),
        sa.Column("what_10q_changed", sa.Text(), nullable=False),
        sa.Column("invalidation", sa.Text(), nullable=False),
        sa.Column("caveats", sa.Text(), nullable=False),
        sa.Column("pack", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.CheckConstraint("status IN ('ok', 'fallback')", name="ck_opportunity_memo_status"),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_opportunity_memo_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_opportunity_memo"),
    )


def downgrade() -> None:
    op.drop_table("opportunity_memo")
    op.drop_index("ix_opportunity_score_rank", table_name="opportunity_score")
    op.drop_table("opportunity_score")
