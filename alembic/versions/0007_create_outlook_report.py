"""Create outlook_report.

Revision ID: 0007_outlook_report
Revises: 0006_news_event_pack
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_outlook_report"
down_revision: str | None = "0006_news_event_pack"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outlook_report",
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("body_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pack_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("status IN ('ok', 'fallback')", name="ck_outlook_report_status"),
        sa.ForeignKeyConstraint(
            ["pack_id"],
            ["evidence_pack.id"],
            name="fk_outlook_report_pack_id_evidence_pack",
        ),
        sa.PrimaryKeyConstraint("as_of", name="pk_outlook_report"),
    )


def downgrade() -> None:
    op.drop_table("outlook_report")
