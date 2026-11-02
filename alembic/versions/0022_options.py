"""Add option_chain_snapshot, option_stats and options_market_stats (Phase 1.12).

Revision ID: 0022_options
Revises: 0021_credit_implied
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_options"
down_revision: str | None = "0021_credit_implied"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "option_chain_snapshot",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(1), nullable=False),
        sa.Column("strike", sa.Numeric(14, 4), nullable=False),
        sa.Column("bid", sa.Numeric(14, 4), nullable=True),
        sa.Column("ask", sa.Numeric(14, 4), nullable=True),
        sa.Column("last", sa.Numeric(14, 4), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("vendor_iv", sa.Numeric(12, 6), nullable=True),
        sa.Column("iv", sa.Numeric(12, 6), nullable=True),
        sa.Column("last_trade_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('C', 'P')", name="ck_option_chain_snapshot_kind"),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_option_chain_snapshot_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "instrument_id", "as_of", "expiry", "kind", "strike", name="pk_option_chain_snapshot"
        ),
    )
    op.create_table(
        "option_stats",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("spot", sa.Numeric(18, 4), nullable=False),
        sa.Column("quote_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_free", sa.Numeric(10, 6), nullable=False),
        sa.Column("atm_iv_30d", sa.Numeric(12, 6), nullable=True),
        sa.Column("atm_iv_90d", sa.Numeric(12, 6), nullable=True),
        sa.Column("term_slope", sa.Numeric(12, 6), nullable=True),
        sa.Column("skew_30d", sa.Numeric(12, 6), nullable=True),
        sa.Column("rv_1y", sa.Numeric(12, 6), nullable=True),
        sa.Column("iv_rv", sa.Numeric(12, 6), nullable=True),
        sa.Column("call_volume", sa.BigInteger(), nullable=False),
        sa.Column("put_volume", sa.BigInteger(), nullable=False),
        sa.Column("call_oi", sa.BigInteger(), nullable=False),
        sa.Column("put_oi", sa.BigInteger(), nullable=False),
        sa.Column("pc_volume", sa.Numeric(12, 4), nullable=True),
        sa.Column("pc_oi", sa.Numeric(12, 4), nullable=True),
        sa.Column("earnings_date", sa.Date(), nullable=True),
        sa.Column("earnings_estimate", sa.Boolean(), nullable=True),
        sa.Column("move_expiry", sa.Date(), nullable=True),
        sa.Column("expected_move", sa.Numeric(12, 6), nullable=True),
        sa.Column("expiries", sa.Integer(), nullable=False),
        sa.Column("contracts", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_option_stats_instrument_id_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "as_of", name="pk_option_stats"),
    )
    op.create_table(
        "options_market_stats",
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("product", sa.String(16), nullable=False),
        sa.Column("pc_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("call_volume", sa.BigInteger(), nullable=False),
        sa.Column("put_volume", sa.BigInteger(), nullable=False),
        sa.Column("call_oi", sa.BigInteger(), nullable=False),
        sa.Column("put_oi", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("as_of", "product", name="pk_options_market_stats"),
    )


def downgrade() -> None:
    op.drop_table("options_market_stats")
    op.drop_table("option_stats")
    op.drop_table("option_chain_snapshot")
