"""Nodos del AST del DSL TeleFlow v2.

Dataclasses (no Pydantic): son estructuras internas, no modelos de API.
La serialización a JSON se hace en teleflow.dsl.serialize.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

# ----------------------------------------------------------- expresiones

ExprValue = Union[str, int, float, bool, None, "list[Any]", "Expr"]


@dataclass
class Expr:
    pass


@dataclass
class Ref(Expr):
    """Referencia con puntos: entity.nino, event.from_id, progreso."""

    parts: tuple[str, ...]

    @property
    def dotted(self) -> str:
        return ".".join(self.parts)

    @property
    def kind(self) -> str:
        return self.parts[0]

    @property
    def target(self) -> str:
        return self.parts[-1]


@dataclass
class Func(Expr):
    name: str
    args: list[ExprValue]


@dataclass
class Cmp(Expr):
    op: str  # == != >= <= > < in
    left: ExprValue
    right: ExprValue


@dataclass
class BoolOp(Expr):
    op: str  # AND | OR
    operands: list[ExprValue]


@dataclass
class Not(Expr):
    operand: ExprValue


@dataclass
class When(Expr):
    """`X WHEN Y` — el invariante X aplica solo cuando Y es verdadero."""

    value: ExprValue
    condition: ExprValue


# ------------------------------------------------------- bloques comunes


@dataclass
class FieldDef:
    name: str
    type: str  # string | number | date | datetime | bool | enum
    enum_values: list[str] | None = None
    required: bool = False
    optional: bool = False
    unique: bool = False
    default: Any = None
    has_default: bool = False
    range: tuple[float, float] | None = None


@dataclass
class TransitionDef:
    from_state: str
    to_state: str
    via: str


@dataclass
class Lifecycle:
    initial: str
    states: list[str]
    transitions: list[TransitionDef]


@dataclass
class EventDecl:
    kind: str  # on_transition | on_field_change
    trigger: str  # nombre de transición o de campo
    emit: str  # nombre del evento de dominio


# ----------------------------------------------------------------- entity


@dataclass
class EntityDef:
    name: str
    description: str = ""
    fields: list[FieldDef] = field(default_factory=list)
    lifecycle: Lifecycle | None = None
    events: list[EventDecl] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)

    def field_map(self) -> dict[str, FieldDef]:
        return {f.name: f for f in self.fields}


# --------------------------------------------------------------- relation


@dataclass
class RelationDef:
    name: str
    description: str = ""
    from_ref: Ref | None = None
    to_ref: Ref | None = None
    cardinality: str = "many_to_many"
    constraint: str | None = None
    lifecycle: Lifecycle | None = None
    fields: list[FieldDef] = field(default_factory=list)
    events: list[EventDecl] = field(default_factory=list)


# ------------------------------------------------------------------- rule


@dataclass
class TimerSpec:
    after_seconds: int
    since: str
    condition: ExprValue


@dataclass
class RuleDef:
    name: str
    on_event: str | None = None
    on_state: str | None = None
    on_relation: str | None = None
    timer: TimerSpec | None = None
    condition: ExprValue = None
    execute: Ref | None = None
    with_map: dict[str, ExprValue] = field(default_factory=dict)


# ---------------------------------------------------------------- view360


@dataclass
class ViewRelation:
    alias: str
    relation: Ref
    where: ExprValue = None
    include: list[Ref] = field(default_factory=list)


@dataclass
class ActiveProcesses:
    include: list[Ref] = field(default_factory=list)
    filter: ExprValue = None


@dataclass
class Timeline:
    events: str = "all"
    limit: int = 50
    order: str = "desc"


@dataclass
class View360Def:
    name: str
    entity: Ref | None = None
    relations: list[ViewRelation] = field(default_factory=list)
    active_processes: ActiveProcesses | None = None
    timeline: Timeline | None = None
    alerts: list[Ref] = field(default_factory=list)


# ---------------------------------------------------------------- process


@dataclass
class Branch:
    condition: ExprValue  # None == else
    target: Ref


@dataclass
class StageDef:
    name: str
    mode: str  # sequential | parallel | decision
    steps: list[Ref] = field(default_factory=list)
    branches: list[Branch] = field(default_factory=list)


@dataclass
class ActionDef:
    kind: str  # emit | transition
    event: str | None = None
    target: Ref | None = None
    via: str | None = None


@dataclass
class ProcessDef:
    name: str
    description: str = ""
    input: list[FieldDef] = field(default_factory=list)
    stages: list[StageDef] = field(default_factory=list)
    on_complete: list[ActionDef] = field(default_factory=list)


# ------------------------------------------------------------------- step


@dataclass
class StepDef:
    name: str
    description: str = ""
    type: str = "automated"  # automated | human_task | decision | notification
    integration: Ref | None = None
    method: str | None = None
    path: str | None = None
    payload: dict[str, ExprValue] = field(default_factory=dict)
    retries: int = 3
    timeout_seconds: int | None = None
    assignee: str | None = None
    signals: list[str] = field(default_factory=list)
    channel: str | None = None
    to: ExprValue = None
    template: str | None = None
    condition: ExprValue = None
    on_complete: list[ActionDef] = field(default_factory=list)


# ----------------------------------------------------------- integration


@dataclass
class IntegrationDef:
    name: str
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        return str(self.config.get("type", "rest"))


# ------------------------------------------------------ catalog / party


@dataclass
class ProductDef:
    name: str
    description: str = ""
    instantiates: Ref | None = None
    price: float | None = None
    currency: str | None = None


@dataclass
class CatalogDef:
    name: str
    description: str = ""
    products: list[ProductDef] = field(default_factory=list)


@dataclass
class PartyDef:
    name: str
    description: str = ""
    role: str | None = None
    entity: Ref | None = None


# ------------------------------------------------------------- documento


@dataclass
class FlowFile:
    """Un archivo .tflow completo: la declaración del dominio de negocio."""

    entities: dict[str, EntityDef] = field(default_factory=dict)
    relations: dict[str, RelationDef] = field(default_factory=dict)
    rules: dict[str, RuleDef] = field(default_factory=dict)
    views: dict[str, View360Def] = field(default_factory=dict)
    processes: dict[str, ProcessDef] = field(default_factory=dict)
    steps: dict[str, StepDef] = field(default_factory=dict)
    integrations: dict[str, IntegrationDef] = field(default_factory=dict)
    catalogs: dict[str, CatalogDef] = field(default_factory=dict)
    parties: dict[str, PartyDef] = field(default_factory=dict)

    def merge(self, other: "FlowFile") -> "FlowFile":
        """Combina dos archivos de dominio (último gana por nombre)."""
        merged = FlowFile(
            entities={**self.entities, **other.entities},
            relations={**self.relations, **other.relations},
            rules={**self.rules, **other.rules},
            views={**self.views, **other.views},
            processes={**self.processes, **other.processes},
            steps={**self.steps, **other.steps},
            integrations={**self.integrations, **other.integrations},
            catalogs={**self.catalogs, **other.catalogs},
            parties={**self.parties, **other.parties},
        )
        return merged
