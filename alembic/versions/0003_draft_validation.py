"""Borradores: proveedor que los generó y validación contra el parser (Fase D — composer)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ambas nullable: los borradores anteriores a esta migración no tienen cómo saberlo,
    # y "no sé" es un estado distinto de "compila" o "lo generó el stub".
    op.add_column(
        "flow_drafts",
        sa.Column("provider", sa.String(30), nullable=True),
    )
    op.add_column(
        "flow_drafts",
        sa.Column("validation", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("flow_drafts", "validation")
    op.drop_column("flow_drafts", "provider")
