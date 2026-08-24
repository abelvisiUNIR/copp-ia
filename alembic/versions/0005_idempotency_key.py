"""Idempotencia de /execute: una clave = una instancia

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: la clave es opcional, y las instancias que ya existen no tienen ninguna.
    # El UNIQUE es la garantía real (el chequeo previo deja una ventana entre el SELECT y el
    # INSERT); en Postgres varios NULL no colisionan entre sí.
    op.add_column(
        "process_instances",
        sa.Column("idempotency_key", sa.String(200), nullable=True),
    )
    op.create_unique_constraint(
        "uq_process_instances_idempotency_key", "process_instances", ["idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_process_instances_idempotency_key", "process_instances", type_="unique"
    )
    op.drop_column("process_instances", "idempotency_key")
