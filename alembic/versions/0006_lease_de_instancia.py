"""Propiedad de una instancia en vuelo: dueño + vencimiento del lease

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable las dos: una instancia sin dueño es una instancia que nadie está ejecutando, y
    # eso incluye a todas las que ya existen y a todas las que terminaron.
    #
    # `driven_by` identifica al proceso que la está ejecutando (hostname del pod + pid). No es
    # una FK a nada: no hay tabla de réplicas, y no debería haberla — el dueño se valida por el
    # vencimiento, no por existir.
    op.add_column(
        "process_instances",
        sa.Column("driven_by", sa.String(200), nullable=True),
    )
    op.add_column(
        "process_instances",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # El índice es para la consulta de `_recover()`: "en vuelo y sin dueño vivo". Sin él, cada
    # arranque hace un scan de la tabla entera de instancias.
    op.create_index(
        "ix_process_instances_lease",
        "process_instances",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_process_instances_lease", table_name="process_instances")
    op.drop_column("process_instances", "lease_expires_at")
    op.drop_column("process_instances", "driven_by")
