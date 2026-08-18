"""Create bar_daily and quote_latest.

Revision ID: 0002_bar_daily_quote_latest
Revises: 0001_instrument_universe_job_run
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_bar_daily_quote_latest"
down_revision: str | None = "0001_instrument_universe_job_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bar_daily",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("o", sa.Numeric(18, 6), nullable=False),
        sa.Column("h", sa.Numeric(18, 6), nullable=False),
        sa.Column("l", sa.Numeric(18, 6), nullable=False),
        sa.Column("c", sa.Numeric(18, 6), nullable=False),
        sa.Column("adj_c", sa.Numeric(18, 6), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_bar_daily_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "date", name="pk_bar_daily"),
    )
    op.create_index("ix_bar_daily_date", "bar_daily", ["date"])
    op.create_table(
        "quote_latest",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("change_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("market_state", sa.String(length=16), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_quote_latest_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", name="pk_quote_latest"),
    )


def downgrade() -> None:
    op.drop_table("quote_latest")
    op.drop_index("ix_bar_daily_date", table_name="bar_daily")
    op.drop_table("bar_daily")
