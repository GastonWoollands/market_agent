"""Create instrument, universe, universe_member, and job_run.

Revision ID: 0001_instrument_universe_job_run
Revises:
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_instrument_universe_job_run"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrument",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("yahoo_symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("cik", sa.String(length=10), nullable=True),
        sa.Column("figi", sa.String(length=12), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_instrument"),
        sa.UniqueConstraint("ticker", name="uq_instrument_ticker"),
    )
    op.create_table(
        "universe",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_universe"),
        sa.UniqueConstraint("name", name="uq_universe_name"),
    )
    op.create_table(
        "universe_member",
        sa.Column("universe_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["universe_id"],
            ["universe.id"],
            name="fk_universe_member_universe_id_universe",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_universe_member_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("universe_id", "instrument_id", name="pk_universe_member"),
    )
    op.create_table(
        "job_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rows_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("status IN ('running', 'ok', 'error')", name="ck_job_run_status"),
        sa.PrimaryKeyConstraint("id", name="pk_job_run"),
    )
    op.create_index("ix_job_run_job_name", "job_run", ["job_name"])


def downgrade() -> None:
    op.drop_index("ix_job_run_job_name", table_name="job_run")
    op.drop_table("job_run")
    op.drop_table("universe_member")
    op.drop_table("universe")
    op.drop_table("instrument")
