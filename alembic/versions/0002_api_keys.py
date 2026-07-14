"""API keys con scopes e identidad (Fase D — seguridad)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # nombre = identidad de la integración (para auditoría: quién disparó qué)
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        # solo el hash: la key en claro se muestra una única vez, al crearla
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("scopes", JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true(),
                  index=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
