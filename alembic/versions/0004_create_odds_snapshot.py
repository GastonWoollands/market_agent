"""Create odds_snapshot.

Revision ID: 0004_odds_snapshot
Revises: 0003_macro_series_observation
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_odds_snapshot"
down_revision: str | None = "0003_macro_series_observation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "odds_snapshot",
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("implied_yes", sa.Numeric(18, 6), nullable=False),
        sa.Column("liquidity", sa.Numeric(18, 6), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("slug", name="pk_odds_snapshot"),
    )


def downgrade() -> None:
    op.drop_table("odds_snapshot")
