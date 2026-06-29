"""Schema inicial TeleFlow (sección 9.4 del documento de arquitectura)

Revision ID: 0001
Revises:
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flow_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, index=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("ast", JSONB(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="registered"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", "version", name="uq_flow_name_version"),
    )

    op.create_table(
        "flow_latest",
        sa.Column("name", sa.String(200), primary_key=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "process_instances",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("flow_name", sa.String(200), nullable=False, index=True),
        sa.Column("flow_version", sa.String(50), nullable=False),
        sa.Column("correlation_id", sa.String(200), nullable=True, index=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("trigger_payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("context", JSONB(), nullable=False, server_default="{}"),
        sa.Column("current_step", sa.String(200), nullable=True),
        sa.Column("error", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "instance_transitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("instance_id", sa.Uuid(), sa.ForeignKey("process_instances.id"),
                  nullable=False, index=True),
        sa.Column("from_status", sa.String(30), nullable=False),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("step_name", sa.String(200), nullable=True),
        sa.Column("step_output", JSONB(), nullable=True),
        sa.Column("actor_id", sa.String(200), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "entity_state",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("estado", sa.String(50), nullable=False),
        sa.Column("campos", JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_entity_type_id"),
    )

    op.create_table(
        "entity_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("event_name", sa.String(200), nullable=False, index=True),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  index=True),
    )
    op.create_index("ix_entity_events_subject", "entity_events", ["entity_type", "entity_id"])

    op.create_table(
        "relation_state",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("relation_type", sa.String(100), nullable=False, index=True),
        sa.Column("from_id", sa.String(100), nullable=False, index=True),
        sa.Column("to_id", sa.String(100), nullable=False, index=True),
        sa.Column("estado", sa.String(50), nullable=False),
        sa.Column("campos", JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "signals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("instance_id", sa.Uuid(), sa.ForeignKey("process_instances.id"),
                  nullable=False, index=True),
        sa.Column("step_name", sa.String(200), nullable=False),
        sa.Column("signal", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=True),
        sa.Column("signal_data", JSONB(), nullable=False, server_default="{}"),
        sa.Column("signal_key", sa.String(200), nullable=True, unique=True),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "flow_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("base_source", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending",
                  index=True),
        sa.Column("comments", JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "rule_timer_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_name", sa.String(200), nullable=False),
        sa.Column("subject_key", sa.String(300), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("rule_name", "subject_key", name="uq_rule_subject"),
    )


def downgrade() -> None:
    for table in (
        "rule_timer_log",
        "flow_drafts",
        "signals",
        "relation_state",
        "entity_events",
        "entity_state",
        "instance_transitions",
        "process_instances",
        "flow_latest",
        "flow_definitions",
    ):
        op.drop_table(table)
