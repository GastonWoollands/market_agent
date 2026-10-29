"""Add odds_snapshot.slot as the catalog identity.

Revision ID: 0017_odds_snapshot_slot
Revises: 0016_metric_fy_quant
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_odds_snapshot_slot"
down_revision: str | None = "0016_metric_fy_quant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SLOT_FROM_SLUG = """
UPDATE odds_snapshot SET slot = CASE slug
  WHEN 'fed-decision-in-september-762' THEN 'front_fomc'
  WHEN 'fed-decision-in-october-20260617190323537' THEN 'next_fomc'
  WHEN 'how-many-fed-rate-cuts-in-2026' THEN 'cuts_year'
  WHEN 'core-cpi-yoy-august-2026-1786474662954' THEN 'core_cpi_yoy'
  WHEN 'us-recession-by-end-of-2026' THEN 'recession'
  ELSE NULL
END
"""


def upgrade() -> None:
    op.add_column("odds_snapshot", sa.Column("slot", sa.String(length=64), nullable=True))
    op.execute(sa.text(_SLOT_FROM_SLUG))
    # Unmapped rows are stale catalog entries; the next ingest re-resolves every slot.
    op.execute(sa.text("DELETE FROM odds_snapshot WHERE slot IS NULL"))
    op.alter_column("odds_snapshot", "slot", existing_type=sa.String(length=64), nullable=False)
    op.drop_constraint("pk_odds_snapshot", "odds_snapshot", type_="primary")
    op.create_primary_key("pk_odds_snapshot", "odds_snapshot", ["slot"])
    op.create_unique_constraint("uq_odds_snapshot_slug", "odds_snapshot", ["slug"])


def downgrade() -> None:
    op.drop_constraint("uq_odds_snapshot_slug", "odds_snapshot", type_="unique")
    op.drop_constraint("pk_odds_snapshot", "odds_snapshot", type_="primary")
    op.create_primary_key("pk_odds_snapshot", "odds_snapshot", ["slug"])
    op.drop_column("odds_snapshot", "slot")
