"""Add score_exclusion and opportunity_score.ret_12_1 (sector-neutral 12-1 ranking).

Revision ID: 0026_score_exclusion
Revises: 0025_metric_ttm_income_equity
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0026_score_exclusion"
down_revision: str | None = "0025_metric_ttm_income_equity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("opportunity_score", sa.Column("ret_12_1", sa.Numeric(18, 6), nullable=True))
    op.create_table(
        "score_exclusion",
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instrument.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("as_of", sa.Date(), primary_key=True),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("score_exclusion")
    op.drop_column("opportunity_score", "ret_12_1")
