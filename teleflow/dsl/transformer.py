"""Transformer Lark → dataclasses del AST."""
from __future__ import annotations

import json
from typing import Any

from lark import Token, Transformer

from teleflow.dsl.ast_nodes import (
    ActionDef,
    ActiveProcesses,
    BoolOp,
    Branch,
    CatalogDef,
    Cmp,
    EntityDef,
    EventDecl,
    FieldDef,
    FlowFile,
    Func,
    IntegrationDef,
    Lifecycle,
    Not,
    PartyDef,
    ProcessDef,
    ProductDef,
    Ref,
    RelationDef,
    RuleDef,
    StageDef,
    StepDef,
    TimerSpec,
    TransitionDef,
    View360Def,
    ViewRelation,
    When,
)


def _unquote(raw: str) -> str:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")


class TeleFlowTransformer(Transformer):
    # ------------------------------------------------------------ tokens
    def STRING(self, tok: Token) -> str:
        return _unquote(str(tok))

    def NAME(self, tok: Token) -> str:
        return str(tok)

    def NUMBER(self, tok: Token) -> int | float:
        s = str(tok)
        return float(s) if "." in s else int(s)

    def COMP_OP(self, tok: Token) -> str:
        return str(tok)

    # ------------------------------------------------------------- listas
    def string_list(self, c: list) -> list[str]:
        return list(c)

    def ref_list(self, c: list) -> list[Ref]:
        return list(c)

    # ---------------------------------------------------------- literales
    def lit_string(self, c: list) -> str:
        return c[0]

    def lit_number(self, c: list) -> int | float:
        return c[0]

    def lit_true(self, c: list) -> bool:
        return True

    def lit_false(self, c: list) -> bool:
        return False

    def lit_null(self, c: list) -> None:
        return None

    # -------------------------------------------------------- expresiones
    def ref(self, c: list) -> Ref:
        return Ref(parts=tuple(c))

    def func_call(self, c: list) -> Func:
        return Func(name=c[0], args=list(c[1:]))

    def list_lit(self, c: list) -> list:
        return list(c)

    def cmp(self, c: list) -> Cmp:
        return Cmp(op=c[1], left=c[0], right=c[2])

    def in_cmp(self, c: list) -> Cmp:
        return Cmp(op="in", left=c[0], right=c[1])

    def and_expr(self, c: list) -> BoolOp:
        return BoolOp(op="AND", operands=list(c))

    def or_expr(self, c: list) -> BoolOp:
        return BoolOp(op="OR", operands=list(c))

    def not_expr(self, c: list) -> Not:
        return Not(operand=c[0])

    def when_expr(self, c: list) -> When:
        return When(value=c[0], condition=c[1])

    # ---------------------------------------------------------- duraciones
    def u_seconds(self, c: list) -> int:
        return 1

    def u_minutes(self, c: list) -> int:
        return 60

    def u_hours(self, c: list) -> int:
        return 3600

    def u_days(self, c: list) -> int:
        return 86400

    def u_weeks(self, c: list) -> int:
        return 604800

    def duration(self, c: list) -> int:
        return int(c[0] * c[1])

    # ------------------------------------------------------------- campos
    def t_string(self, c: list) -> tuple:
        return ("string", None)

    def t_number(self, c: list) -> tuple:
        return ("number", None)

    def t_date(self, c: list) -> tuple:
        return ("date", None)

    def t_datetime(self, c: list) -> tuple:
        return ("datetime", None)

    def t_bool(self, c: list) -> tuple:
        return ("bool", None)

    def t_enum(self, c: list) -> tuple:
        return ("enum", c[0])

    def m_required(self, c: list) -> tuple:
        return ("required", True)

    def m_optional(self, c: list) -> tuple:
        return ("optional", True)

    def m_unique(self, c: list) -> tuple:
        return ("unique", True)

    def m_default(self, c: list) -> tuple:
        return ("default", c[0])

    def m_range(self, c: list) -> tuple:
        return ("range", (float(c[0]), float(c[1])))

    def field_def(self, c: list) -> FieldDef:
        name = c[0]
        ftype, enum_values = c[1]
        fd = FieldDef(name=name, type=ftype, enum_values=enum_values)
        for key, value in c[2:]:
            if key == "default":
                fd.default = value
                fd.has_default = True
            elif key == "range":
                fd.range = value
            else:
                setattr(fd, key, value)
        return fd

    def fields_block(self, c: list) -> tuple:
        return ("fields", list(c))

    # ----------------------------------------------------------- lifecycle
    def transition(self, c: list) -> TransitionDef:
        return TransitionDef(from_state=c[0], to_state=c[1], via=c[2])

    def transitions_block(self, c: list) -> list[TransitionDef]:
        return list(c)

    def lifecycle_block(self, c: list) -> tuple:
        return ("lifecycle", Lifecycle(initial=c[0], states=c[1], transitions=c[2]))

    # -------------------------------------------------------------- events
    def ev_transition(self, c: list) -> EventDecl:
        return EventDecl(kind="on_transition", trigger=c[0], emit=c[1])

    def ev_field_change(self, c: list) -> EventDecl:
        return EventDecl(kind="on_field_change", trigger=c[0], emit=c[1])

    def events_block(self, c: list) -> tuple:
        return ("events", list(c))

    def invariants_block(self, c: list) -> tuple:
        return ("invariants", list(c))

    def description(self, c: list) -> tuple:
        return ("description", c[0])

    # -------------------------------------------------------------- entity
    def entity_block(self, c: list) -> EntityDef:
        entity = EntityDef(name=c[0])
        for key, value in c[1:]:
            setattr(entity, key, value)
        return entity

    # ------------------------------------------------------------ relation
    def from_decl(self, c: list) -> tuple:
        return ("from_ref", c[0])

    def to_decl(self, c: list) -> tuple:
        return ("to_ref", c[0])

    def cardinality_decl(self, c: list) -> tuple:
        return ("cardinality", c[0])

    def constraint_decl(self, c: list) -> tuple:
        return ("constraint", c[0])

    def relation_block(self, c: list) -> RelationDef:
        rel = RelationDef(name=c[0])
        for key, value in c[1:]:
            setattr(rel, key, value)
        return rel

    # ---------------------------------------------------------------- rule
    def r_on_event(self, c: list) -> tuple:
        return ("on_event", c[0])

    def r_on_state(self, c: list) -> tuple:
        return ("on_state", c[0])

    def r_on_relation(self, c: list) -> tuple:
        return ("on_relation", c[0])

    def r_condition(self, c: list) -> tuple:
        return ("condition", c[0])

    def r_execute(self, c: list) -> tuple:
        return ("execute", c[0])

    def with_assign(self, c: list) -> tuple:
        return (c[0], c[1])

    def with_block(self, c: list) -> tuple:
        return ("with_map", dict(c))

    def on_timer_block(self, c: list) -> tuple:
        return ("timer", TimerSpec(after_seconds=c[0], since=c[1], condition=c[2]))

    def rule_block(self, c: list) -> RuleDef:
        rule = RuleDef(name=c[0])
        for key, value in c[1:]:
            setattr(rule, key, value)
        return rule

    # ------------------------------------------------------------- view360
    def view_entity_decl(self, c: list) -> tuple:
        return ("entity", c[0])

    def where_clause(self, c: list) -> tuple:
        return ("where", c[0])

    def include_clause(self, c: list) -> tuple:
        return ("include", c[0])

    def view_relation(self, c: list) -> ViewRelation:
        vr = ViewRelation(alias=c[0], relation=c[1])
        for key, value in c[2:]:
            setattr(vr, key, value)
        return vr

    def view_relations_block(self, c: list) -> tuple:
        return ("relations", list(c))

    def active_processes_block(self, c: list) -> tuple:
        return ("active_processes", ActiveProcesses(include=c[0], filter=c[1]))

    def tl_events(self, c: list) -> tuple:
        return ("events", c[0])

    def tl_limit(self, c: list) -> tuple:
        return ("limit", int(c[0]))

    def tl_order(self, c: list) -> tuple:
        return ("order", c[0])

    def event_timeline_block(self, c: list) -> tuple:
        from teleflow.dsl.ast_nodes import Timeline

        tl = Timeline()
        for key, value in c:
            setattr(tl, key, value)
        return ("timeline", tl)

    def alert_ref(self, c: list) -> Ref:
        return c[0]

    def alerts_block(self, c: list) -> tuple:
        return ("alerts", list(c))

    def view_block(self, c: list) -> View360Def:
        view = View360Def(name=c[0])
        for key, value in c[1:]:
            setattr(view, key, value)
        return view

    # -------------------------------------------------------------- process
    def input_block(self, c: list) -> tuple:
        return ("input", list(c))

    def sm_sequential(self, c: list) -> str:
        return "sequential"

    def sm_parallel(self, c: list) -> str:
        return "parallel"

    def sm_decision(self, c: list) -> str:
        return "decision"

    def steps_decl(self, c: list) -> list[Ref]:
        return c[0] if c else []

    def branch_when(self, c: list) -> Branch:
        return Branch(condition=c[0], target=c[1])

    def branch_else(self, c: list) -> Branch:
        return Branch(condition=None, target=c[0])

    def stage_block(self, c: list) -> tuple:
        stage = StageDef(name=c[0], mode=c[1], steps=c[2], branches=list(c[3:]))
        return ("stage", stage)

    def act_emit(self, c: list) -> ActionDef:
        return ActionDef(kind="emit", event=c[0])

    def act_transition(self, c: list) -> ActionDef:
        return ActionDef(kind="transition", target=c[0], via=c[1])

    def on_complete_block(self, c: list) -> tuple:
        return ("on_complete", list(c))

    def process_block(self, c: list) -> ProcessDef:
        proc = ProcessDef(name=c[0])
        for key, value in c[1:]:
            if key == "stage":
                proc.stages.append(value)
            else:
                setattr(proc, key, value)
        return proc

    # ----------------------------------------------------------------- step
    def st_automated(self, c: list) -> str:
        return "automated"

    def st_human_task(self, c: list) -> str:
        return "human_task"

    def st_decision(self, c: list) -> str:
        return "decision"

    def st_notification(self, c: list) -> str:
        return "notification"

    def s_type(self, c: list) -> tuple:
        return ("type", c[0])

    def s_integration(self, c: list) -> tuple:
        return ("integration", c[0])

    def s_method(self, c: list) -> tuple:
        return ("method", c[0])

    def s_path(self, c: list) -> tuple:
        return ("path", c[0])

    def s_retries(self, c: list) -> tuple:
        return ("retries", int(c[0]))

    def s_timeout(self, c: list) -> tuple:
        return ("timeout_seconds", c[0])

    def s_assignee(self, c: list) -> tuple:
        return ("assignee", c[0])

    def s_signals(self, c: list) -> tuple:
        return ("signals", c[0])

    def s_channel(self, c: list) -> tuple:
        return ("channel", c[0])

    def s_to(self, c: list) -> tuple:
        return ("to", c[0])

    def s_template(self, c: list) -> tuple:
        return ("template", c[0])

    def s_condition(self, c: list) -> tuple:
        return ("condition", c[0])

    def payload_block(self, c: list) -> tuple:
        return ("payload", dict(c))

    def step_block(self, c: list) -> StepDef:
        step = StepDef(name=c[0])
        for key, value in c[1:]:
            setattr(step, key, value)
        return step

    # ----------------------------------------------------------- integration
    def integ_kv(self, c: list) -> tuple:
        return (c[0], c[1])

    def integ_timeout(self, c: list) -> tuple:
        return ("timeout", c[0])

    def integration_block(self, c: list) -> IntegrationDef:
        return IntegrationDef(name=c[0], config=dict(c[1:]))

    # ------------------------------------------------------- catalog / party
    def p_instantiates(self, c: list) -> tuple:
        return ("instantiates", c[0])

    def p_price(self, c: list) -> tuple:
        return ("price", float(c[0]))

    def p_currency(self, c: list) -> tuple:
        return ("currency", c[0])

    def product_block(self, c: list) -> tuple:
        product = ProductDef(name=c[0])
        for key, value in c[1:]:
            setattr(product, key, value)
        return ("product", product)

    def catalog_block(self, c: list) -> CatalogDef:
        catalog = CatalogDef(name=c[0])
        for key, value in c[1:]:
            if key == "product":
                catalog.products.append(value)
            else:
                setattr(catalog, key, value)
        return catalog

    def pa_role(self, c: list) -> tuple:
        return ("role", c[0])

    def pa_entity(self, c: list) -> tuple:
        return ("entity", c[0])

    def party_block(self, c: list) -> PartyDef:
        party = PartyDef(name=c[0])
        for key, value in c[1:]:
            setattr(party, key, value)
        return party

    # ------------------------------------------------------------- documento
    def start(self, c: list) -> FlowFile:
        doc = FlowFile()
        for block in c:
            if isinstance(block, EntityDef):
                doc.entities[block.name] = block
            elif isinstance(block, RelationDef):
                doc.relations[block.name] = block
            elif isinstance(block, RuleDef):
                doc.rules[block.name] = block
            elif isinstance(block, View360Def):
                doc.views[block.name] = block
            elif isinstance(block, ProcessDef):
                doc.processes[block.name] = block
            elif isinstance(block, StepDef):
                doc.steps[block.name] = block
            elif isinstance(block, IntegrationDef):
                doc.integrations[block.name] = block
            elif isinstance(block, CatalogDef):
                doc.catalogs[block.name] = block
            elif isinstance(block, PartyDef):
                doc.parties[block.name] = block
        return doc
