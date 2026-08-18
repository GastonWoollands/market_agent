"""Create bar_intraday for tape and watchlist 5m bars.

Revision ID: 0011_bar_intraday
Revises: 0010_opportunity
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_bar_intraday"
down_revision: str | None = "0010_opportunity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bar_intraday",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("o", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("h", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("l", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("c", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_bar_intraday_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "ts", "interval", name="pk_bar_intraday"),
    )
    op.create_index("ix_bar_intraday_ts", "bar_intraday", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_bar_intraday_ts", table_name="bar_intraday")
    op.drop_table("bar_intraday")
