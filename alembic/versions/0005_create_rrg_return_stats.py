"""Create return_stats and rrg_point.

Revision ID: 0005_rrg_return_stats
Revises: 0004_odds_snapshot
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_rrg_return_stats"
down_revision: str | None = "0004_odds_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "return_stats",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("ret_1w", sa.Numeric(18, 6), nullable=True),
        sa.Column("ret_1m", sa.Numeric(18, 6), nullable=True),
        sa.Column("ret_3m", sa.Numeric(18, 6), nullable=True),
        sa.Column("ret_1y", sa.Numeric(18, 6), nullable=True),
        sa.Column("indexed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_return_stats_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_return_stats"),
    )
    op.create_table(
        "rrg_point",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("rs_ratio", sa.Numeric(18, 6), nullable=False),
        sa.Column("rs_momentum", sa.Numeric(18, 6), nullable=False),
        sa.Column("quadrant", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "quadrant IN ('leading', 'weakening', 'lagging', 'improving')",
            name="ck_rrg_point_quadrant",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_rrg_point_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_rrg_point"),
    )
    op.create_index("ix_rrg_point_as_of", "rrg_point", ["as_of"])


def downgrade() -> None:
    op.drop_index("ix_rrg_point_as_of", table_name="rrg_point")
    op.drop_table("rrg_point")
    op.drop_table("return_stats")
