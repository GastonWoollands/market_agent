"""Create macro_series and macro_observation.

Revision ID: 0003_macro_series_observation
Revises: 0002_bar_daily_quote_latest
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_macro_series_observation"
down_revision: str | None = "0002_bar_daily_quote_latest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "macro_series",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("fred_id", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_macro_series"),
    )
    op.create_table(
        "macro_observation",
        sa.Column("series_id", sa.String(length=32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(18, 6), nullable=False),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["macro_series.id"],
            name="fk_macro_observation_series_id_macro_series",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("series_id", "date", name="pk_macro_observation"),
    )
    op.create_index("ix_macro_observation_date", "macro_observation", ["date"])


def downgrade() -> None:
    op.drop_index("ix_macro_observation_date", table_name="macro_observation")
    op.drop_table("macro_observation")
    op.drop_table("macro_series")
