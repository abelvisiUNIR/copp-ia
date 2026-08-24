"""Auditoría persistida: quién hizo qué, cuándo y con qué resultado

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False, index=True),
        # La identidad sobrevive a la revocación de la key: la fila de `api_keys` no se borra
        # justamente para que esto siga significando algo. Sin FK a propósito — la auditoría
        # no puede quedar atada al ciclo de vida de la credencial.
        sa.Column("actor_name", sa.String(200), nullable=False, index=True),
        sa.Column("actor_key_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("scope", sa.String(50), nullable=False, server_default="", index=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(200), nullable=True, index=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("details", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
