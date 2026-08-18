"""Create metric_ttm and index instrument.cik.

Revision ID: 0008_metric_ttm
Revises: 0007_outlook_report
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_metric_ttm"
down_revision: str | None = "0007_outlook_report"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_instrument_cik", "instrument", ["cik"])
    op.create_table(
        "metric_ttm",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("revenue", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("ebitda", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("fcf", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("net_debt", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("shares", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_metric_ttm_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_metric_ttm"),
    )


def downgrade() -> None:
    op.drop_table("metric_ttm")
    op.drop_index("ix_instrument_cik", table_name="instrument")
