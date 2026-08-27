"""Borradores: guardar la fuente original del modelo al corregirlos a mano

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `source` sigue siendo la versión vigente, la que se despliega al aprobar. Esta columna
    # guarda lo que había antes de la primera corrección humana, para que la revisión pueda
    # mostrar el diff entre lo que escribió el modelo y lo que cambió una persona.
    #
    # Nullable y sin backfill a propósito: null significa "nadie lo editó", que es información,
    # no un dato faltante. Copiar `source` acá para todos los borradores existentes diría que
    # fueron revisados a mano, y no lo fueron.
    op.add_column(
        "flow_drafts",
        sa.Column("source_generado", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("flow_drafts", "source_generado")
