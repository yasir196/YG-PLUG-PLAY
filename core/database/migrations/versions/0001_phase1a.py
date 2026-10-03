"""Phase 1a core tables.

Revision ID: 0001_phase1a
Revises:
"""

from __future__ import annotations

from alembic import op

from core.database.models import Base

revision = "0001_phase1a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
