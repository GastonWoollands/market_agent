"""Kalshi rows on odds_snapshot (source + slot) and CFTC TFF cot_position (Phase 1.13).

Revision ID: 0023_kalshi_cftc
Revises: 0022_options
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_kalshi_cftc"
down_revision: str | None = "0022_options"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "odds_snapshot",
        sa.Column("source", sa.String(16), nullable=False, server_default="polymarket"),
    )
    op.drop_constraint("pk_odds_snapshot", "odds_snapshot", type_="primary")
    op.drop_constraint("uq_odds_snapshot_slug", "odds_snapshot", type_="unique")
    op.create_primary_key("pk_odds_snapshot", "odds_snapshot", ["source", "slot"])
    op.create_unique_constraint("uq_odds_snapshot_source_slug", "odds_snapshot", ["source", "slug"])

    op.create_table(
        "cot_position",
        sa.Column("contract_code", sa.String(16), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("open_interest", sa.BigInteger(), nullable=False),
        sa.Column("dealer_long", sa.BigInteger(), nullable=False),
        sa.Column("dealer_short", sa.BigInteger(), nullable=False),
        sa.Column("asset_mgr_long", sa.BigInteger(), nullable=False),
        sa.Column("asset_mgr_short", sa.BigInteger(), nullable=False),
        sa.Column("lev_money_long", sa.BigInteger(), nullable=False),
        sa.Column("lev_money_short", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("contract_code", "report_date", name="pk_cot_position"),
    )


def downgrade() -> None:
    op.drop_table("cot_position")
    op.execute("DELETE FROM odds_snapshot WHERE source <> 'polymarket'")
    op.drop_constraint("uq_odds_snapshot_source_slug", "odds_snapshot", type_="unique")
    op.drop_constraint("pk_odds_snapshot", "odds_snapshot", type_="primary")
    op.create_primary_key("pk_odds_snapshot", "odds_snapshot", ["slot"])
    op.create_unique_constraint("uq_odds_snapshot_slug", "odds_snapshot", ["slug"])
    op.drop_column("odds_snapshot", "source")
