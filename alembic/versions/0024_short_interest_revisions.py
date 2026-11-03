"""Add short_interest (FINRA) and eps_revision (Yahoo earningsTrend) (Phase 1.14).

Revision ID: 0024_short_interest_revisions
Revises: 0023_kalshi_cftc
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_short_interest_revisions"
down_revision: str | None = "0023_kalshi_cftc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "short_interest",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("short_shares", sa.BigInteger(), nullable=False),
        sa.Column("prev_short_shares", sa.BigInteger(), nullable=True),
        sa.Column("avg_daily_volume", sa.BigInteger(), nullable=True),
        sa.Column("days_to_cover", sa.Numeric(12, 2), nullable=True),
        sa.Column("change_pct", sa.Numeric(14, 4), nullable=True),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_short_interest_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "settlement_date", name="pk_short_interest"),
    )
    op.create_table(
        "eps_revision",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("period", sa.String(8), nullable=False),
        sa.Column("eps_current", sa.Numeric(18, 6), nullable=True),
        sa.Column("eps_7d", sa.Numeric(18, 6), nullable=True),
        sa.Column("eps_30d", sa.Numeric(18, 6), nullable=True),
        sa.Column("eps_60d", sa.Numeric(18, 6), nullable=True),
        sa.Column("eps_90d", sa.Numeric(18, 6), nullable=True),
        sa.Column("up_7d", sa.Integer(), nullable=True),
        sa.Column("up_30d", sa.Integer(), nullable=True),
        sa.Column("down_7d", sa.Integer(), nullable=True),
        sa.Column("down_30d", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_eps_revision_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", "period", name="pk_eps_revision"),
    )


def downgrade() -> None:
    op.drop_table("eps_revision")
    op.drop_table("short_interest")
