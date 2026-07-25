"""Modelos SQLAlchemy — schema de la sección 9.4 del documento de arquitectura."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, String

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class FlowDefinition(Base):
    __tablename__ = "flow_definitions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_flow_name_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    version: Mapped[str] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(Text)
    ast: Mapped[dict[str, Any]] = mapped_column(JSONType)
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="registered")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FlowLatest(Base):
    __tablename__ = "flow_latest"

    name: Mapped[str] = mapped_column(String(200), primary_key=True)
    version: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProcessInstance(Base):
    __tablename__ = "process_instances"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    flow_name: Mapped[str] = mapped_column(String(200), index=True)
    flow_version: Mapped[str] = mapped_column(String(50))
    correlation_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True, default="TRIGGERED")
    trigger_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    current_step: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InstanceTransition(Base):
    __tablename__ = "instance_transitions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("process_instances.id"), index=True
    )
    from_status: Mapped[str] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    step_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    step_output: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EntityState(Base):
    __tablename__ = "entity_state"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_entity_type_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[str] = mapped_column(String(100))
    estado: Mapped[str] = mapped_column(String(50))
    campos: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EntityEvent(Base):
    __tablename__ = "entity_events"
    __table_args__ = (Index("ix_entity_events_subject", "entity_type", "entity_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    event_name: Mapped[str] = mapped_column(String(200), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class RelationState(Base):
    __tablename__ = "relation_state"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    relation_type: Mapped[str] = mapped_column(String(100), index=True)
    from_id: Mapped[str] = mapped_column(String(100), index=True)
    to_id: Mapped[str] = mapped_column(String(100), index=True)
    estado: Mapped[str] = mapped_column(String(50))
    campos: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SignalRecord(Base):
    """Señales a human_tasks. signal_key único garantiza idempotencia (ADR-002)."""

    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("process_instances.id"), index=True
    )
    step_name: Mapped[str] = mapped_column(String(200))
    signal: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    signal_data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    signal_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FlowDraft(Base):
    """Borradores .tflow generados por IA, pendientes de revisión PR-style."""

    __tablename__ = "flow_drafts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text)
    base_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    comments: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    # Proveedor que **generó** este borrador (no el configurado al leerlo): un borrador del
    # `stub` es un esqueleto para editar a mano, y quien lo revisa tiene que saberlo.
    # Nullable por los borradores anteriores a la columna.
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Resultado de pasar `source` por el parser al componer: {parses, issues, checked_at}.
    # `parses: null` = no se pudo verificar (parser caído), que no es lo mismo que "compila".
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RuleTimerLog(Base):
    """Evita re-disparo de reglas on_timer sobre el mismo sujeto."""

    __tablename__ = "rule_timer_log"
    __table_args__ = (
        UniqueConstraint("rule_name", "subject_key", name="uq_rule_subject"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_name: Mapped[str] = mapped_column(String(200))
    subject_key: Mapped[str] = mapped_column(String(300))
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApiKey(Base):
    """Credencial de una integración: sus permisos y su identidad.

    Se guarda **solo el hash** (SHA-256): la key en claro se muestra una única vez, al
    crearla. SHA-256 y no bcrypt/argon2 a propósito: las keys son secretos aleatorios de
    alta entropía generados por el sistema, no contraseñas humanas — no hay nada que
    adivinar por fuerza bruta, y el hash se verifica en **cada request**.
    """

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True)  # identidad, para auditoría
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scopes: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuditLog(Base):
    """Quién hizo qué, cuándo y con qué resultado. Append-only.

    Registra las acciones de **escritura** y **todo intento denegado** (401/403), incluso de
    lectura: un intento fallido de desplegar es lo que una auditoría tiene que mostrar. Las
    lecturas que salen bien no se registran (ver el ADR de auditoría persistida).

    **No guarda el cuerpo del request.** Por ahí pasan datos personales, y esta es la tabla
    que más tiempo se conserva y más gente puede leer. Para el deploy —donde el cuerpo
    importa— se guarda el checksum en `details`.

    Nunca se actualiza ni se borra desde la API. La retención es política del organismo.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Identidad de la key. `actor_name` se conserva aunque la key se revoque después: la fila
    # de `api_keys` no se borra justamente para que esto siga significando algo.
    actor_name: Mapped[str] = mapped_column(String(200), index=True)
    # None = key de bootstrap (env), que no está en la tabla `api_keys`.
    actor_key_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    # Scope exigido por la ruta = qué clase de acción se intentó. Vacío en un 401, donde el
    # request nunca llegó a la ruta.
    scope: Mapped[str] = mapped_column(String(50), default="", index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    # Identificador del recurso tocado (nombre del flow, instance_id, entidad).
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    status_code: Mapped[int] = mapped_column(Integer)
    # Enriquecimiento opcional de la ruta (p.ej. el checksum del source en un deploy). Que
    # falte no invalida el registro: es detalle, no la traza.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
