"""Add stock_split (Yahoo split events) so SEC share counts match split-adjusted closes.

Revision ID: 0027_stock_split
Revises: 0026_score_exclusion
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_stock_split"
down_revision: str | None = "0026_score_exclusion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_split",
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instrument.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("ratio", sa.Numeric(18, 8), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("stock_split")
