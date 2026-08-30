"""Create regime_snapshot table.

Revision ID: 0015_create_regime_snapshot
Revises: 0014_policy_item
Create Date: 2026-08-30 15:30:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_create_regime_snapshot"
down_revision = "0014_policy_item"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regime_snapshot",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("growth_regime", sa.String(20), nullable=False),
        sa.Column("inflation_regime", sa.String(20), nullable=False),
        sa.Column("policy_regime", sa.String(20), nullable=False),
        sa.Column("volatility_regime", sa.String(20), nullable=False),
        sa.Column("growth_confidence", sa.NUMERIC(4, 3), nullable=False),
        sa.Column("inflation_confidence", sa.NUMERIC(4, 3), nullable=False),
        sa.Column("policy_confidence", sa.NUMERIC(4, 3), nullable=False),
        sa.Column("volatility_confidence", sa.NUMERIC(4, 3), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_regime_snapshot"),
        sa.UniqueConstraint("as_of", name="uq_regime_snapshot_as_of"),
    )
    op.create_index("ix_regime_snapshot_as_of", "regime_snapshot", ["as_of"])


def downgrade() -> None:
    op.drop_index("ix_regime_snapshot_as_of", table_name="regime_snapshot")
    op.drop_table("regime_snapshot")
