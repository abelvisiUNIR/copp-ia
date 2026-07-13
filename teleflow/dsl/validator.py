"""Validación semántica de un FlowFile.

El parser-service valida sintaxis (Lark) Y semántica (este módulo).
Errores bloquean el registro; warnings se reportan pero no bloquean
(p.ej. referencias a procesos definidos en otro archivo del dominio).
"""
from __future__ import annotations

from dataclasses import dataclass

from teleflow.dsl.ast_nodes import (
    EntityDef,
    FlowFile,
    Lifecycle,
    RelationDef,
    RuleDef,
)


@dataclass
class ValidationIssue:
    level: str  # error | warning
    message: str
    block: str = ""


class FlowValidationError(Exception):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__("; ".join(i.message for i in issues if i.level == "error"))


def validate_flow(flow: FlowFile) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for category, name in flow.duplicates:
        issues.append(ValidationIssue(
            "error",
            f"{category}.{name}: definido más de una vez en el mismo archivo",
            f"{category}.{name}",
        ))

    for entity in flow.entities.values():
        _check_lifecycle(entity.lifecycle, f"entity.{entity.name}", issues)
        _check_entity_events(entity, issues)
        _check_invariants(entity, issues)

    for rel in flow.relations.values():
        _check_relation(rel, flow, issues)

    known_events = _emitted_events(flow)
    for rule in flow.rules.values():
        triggers = [t for t in (rule.on_event, rule.on_state, rule.on_relation, rule.timer)
                    if t is not None]
        if len(triggers) != 1:
            issues.append(ValidationIssue(
                "error",
                f"rule.{rule.name}: debe tener exactamente un trigger "
                f"(on_event | on_state | on_timer | on_relation), tiene {len(triggers)}",
                f"rule.{rule.name}",
            ))
        _check_rule_trigger_refs(rule, flow, known_events, issues)
        if rule.execute is None:
            issues.append(ValidationIssue(
                "error", f"rule.{rule.name}: falta 'execute'", f"rule.{rule.name}"))
        elif rule.execute.kind == "process":
            target = rule.execute.target
            if flow.processes and target not in flow.processes:
                issues.append(ValidationIssue(
                    "warning",
                    f"rule.{rule.name}: process.{target} no está definido en este archivo "
                    "(puede estar en otro flow del dominio)",
                    f"rule.{rule.name}",
                ))

    for proc in flow.processes.values():
        stage_names = {s.name for s in proc.stages}
        if not proc.stages:
            issues.append(ValidationIssue(
                "error", f"process.{proc.name}: no tiene stages", f"process.{proc.name}"))
        for stage in proc.stages:
            for step_ref in stage.steps:
                step_name = step_ref.target
                if step_name not in flow.steps:
                    issues.append(ValidationIssue(
                        "error",
                        f"process.{proc.name}/stage.{stage.name}: step.{step_name} no definido",
                        f"process.{proc.name}",
                    ))
                elif stage.mode == "parallel" and flow.steps[step_name].type == "human_task":
                    issues.append(ValidationIssue(
                        "error",
                        f"process.{proc.name}/stage.{stage.name}: human_task "
                        f"'{step_name}' no permitido en stage parallel",
                        f"process.{proc.name}",
                    ))
            if stage.mode == "decision" and not stage.branches:
                issues.append(ValidationIssue(
                    "error",
                    f"process.{proc.name}/stage.{stage.name}: stage decision sin branches",
                    f"process.{proc.name}",
                ))
            for branch in stage.branches:
                # "stage.end" es un destino terminal válido: completa el proceso
                if branch.target.target != "end" \
                        and branch.target.target not in stage_names:
                    issues.append(ValidationIssue(
                        "error",
                        f"process.{proc.name}/stage.{stage.name}: branch apunta a stage "
                        f"inexistente '{branch.target.target}'",
                        f"process.{proc.name}",
                    ))

    for step in flow.steps.values():
        if step.type == "automated" and step.integration is not None:
            if step.integration.target not in flow.integrations:
                issues.append(ValidationIssue(
                    "warning",
                    f"step.{step.name}: integration.{step.integration.target} no definida "
                    "en este archivo",
                    f"step.{step.name}",
                ))
        if step.type == "human_task" and not step.signals:
            issues.append(ValidationIssue(
                "warning",
                f"step.{step.name}: human_task sin señales declaradas "
                "(se aceptará cualquier señal)",
                f"step.{step.name}",
            ))
        if step.type == "notification" and not step.channel:
            issues.append(ValidationIssue(
                "error", f"step.{step.name}: notification requiere 'channel'",
                f"step.{step.name}"))

    for view in flow.views.values():
        if view.entity is not None and flow.entities \
                and view.entity.target not in flow.entities:
            issues.append(ValidationIssue(
                "warning",
                f"view360.{view.name}: entity.{view.entity.target} no definida en este archivo",
                f"view360.{view.name}",
            ))
        for vr in view.relations:
            if flow.relations and vr.relation.target not in flow.relations:
                issues.append(ValidationIssue(
                    "warning",
                    f"view360.{view.name}: relation.{vr.relation.target} no definida",
                    f"view360.{view.name}",
                ))
        for alert in view.alerts:
            if flow.rules and alert.target not in flow.rules:
                issues.append(ValidationIssue(
                    "warning",
                    f"view360.{view.name}: rule.{alert.target} no definida",
                    f"view360.{view.name}",
                ))

    return issues


def _emitted_events(flow: FlowFile) -> set[str]:
    """Universo de eventos que este archivo puede emitir (para validar triggers).

    Incluye los `emit` declarados en entities/relations, los eventos emitidos por
    procesos/steps en `on_complete`, y los eventos sintéticos que el executor genera
    por defecto (`<tipo>.transitioned`, `relation.<tipo>.created`).
    """
    events: set[str] = set()
    for entity in flow.entities.values():
        events.update(ev.emit for ev in entity.events)
        events.add(f"{entity.name}.transitioned")
    for rel in flow.relations.values():
        events.update(ev.emit for ev in rel.events)
        events.add(f"{rel.name}.transitioned")
        events.add(f"relation.{rel.name}.created")
    for proc in flow.processes.values():
        events.update(a.event for a in proc.on_complete
                      if a.kind == "emit" and a.event is not None)
    for step in flow.steps.values():
        events.update(a.event for a in step.on_complete
                      if a.kind == "emit" and a.event is not None)
    return events


def _check_rule_trigger_refs(rule: RuleDef, flow: FlowFile, known_events: set[str],
                             issues: list[ValidationIssue]) -> None:
    where = f"rule.{rule.name}"
    # on_event / on_timer.since referencian un nombre de evento de dominio.
    for label, value in (("on_event", rule.on_event),
                         ("on_timer.since", rule.timer.since if rule.timer else None)):
        if value is not None and known_events and value not in known_events:
            issues.append(ValidationIssue(
                "warning",
                f"{where}: {label} '{value}' no coincide con ningún evento emitido "
                "en este archivo (puede emitirse en otro flow del dominio)",
                where,
            ))
    # on_relation referencia una relación por nombre.
    if rule.on_relation is not None and flow.relations \
            and rule.on_relation not in flow.relations:
        issues.append(ValidationIssue(
            "warning",
            f"{where}: on_relation '{rule.on_relation}' no está definida en este archivo",
            where,
        ))
    # on_state tiene forma '<entidad|relación>.<ESTADO>' (ver executor rules.py).
    if rule.on_state is not None:
        if "." not in rule.on_state:
            issues.append(ValidationIssue(
                "warning",
                f"{where}: on_state '{rule.on_state}' debería tener forma "
                "'<entidad|relación>.<estado>'",
                where,
            ))
        else:
            subject, state = rule.on_state.rsplit(".", 1)
            lifecycle = None
            if subject in flow.entities:
                lifecycle = flow.entities[subject].lifecycle
            elif subject in flow.relations:
                lifecycle = flow.relations[subject].lifecycle
            if lifecycle is not None and state not in lifecycle.states:
                issues.append(ValidationIssue(
                    "warning",
                    f"{where}: on_state '{rule.on_state}' usa un estado no declarado "
                    f"en el lifecycle de '{subject}'",
                    where,
                ))


def _check_lifecycle(lc: Lifecycle | None, where: str,
                     issues: list[ValidationIssue]) -> None:
    if lc is None:
        return
    states = set(lc.states)
    if lc.initial not in states:
        issues.append(ValidationIssue(
            "error", f"{where}: estado inicial '{lc.initial}' no está en states", where))
    for t in lc.transitions:
        for st in (t.from_state, t.to_state):
            if st not in states:
                issues.append(ValidationIssue(
                    "error",
                    f"{where}: transición {t.from_state} -> {t.to_state} usa estado "
                    f"no declarado '{st}'",
                    where,
                ))


def _check_entity_events(entity: EntityDef, issues: list[ValidationIssue]) -> None:
    vias = {t.via for t in entity.lifecycle.transitions} if entity.lifecycle else set()
    field_names = {f.name for f in entity.fields}
    for ev in entity.events:
        if ev.kind == "on_transition" and ev.trigger not in vias:
            issues.append(ValidationIssue(
                "error",
                f"entity.{entity.name}: on_transition '{ev.trigger}' no corresponde a "
                "ninguna transición declarada",
                f"entity.{entity.name}",
            ))
        if ev.kind == "on_field_change" and ev.trigger not in field_names:
            issues.append(ValidationIssue(
                "error",
                f"entity.{entity.name}: on_field_change '{ev.trigger}' no es un campo",
                f"entity.{entity.name}",
            ))


def _check_invariants(entity: EntityDef, issues: list[ValidationIssue]) -> None:
    from teleflow.dsl.parser import TeleFlowSyntaxError, get_parser

    parser = get_parser()
    for inv in entity.invariants:
        try:
            parser.parse_expr(inv)
        except TeleFlowSyntaxError:
            issues.append(ValidationIssue(
                "error",
                f"entity.{entity.name}: invariante no parseable: \"{inv}\"",
                f"entity.{entity.name}",
            ))


def _check_relation(rel: RelationDef, flow: FlowFile,
                    issues: list[ValidationIssue]) -> None:
    where = f"relation.{rel.name}"
    for label, ref in (("from", rel.from_ref), ("to", rel.to_ref)):
        if ref is None:
            issues.append(ValidationIssue("error", f"{where}: falta '{label}'", where))
        elif ref.kind != "entity":
            issues.append(ValidationIssue(
                "error", f"{where}: '{label}' debe referenciar entity.<nombre>", where))
        elif flow.entities and ref.target not in flow.entities:
            issues.append(ValidationIssue(
                "warning",
                f"{where}: entity.{ref.target} no definida en este archivo", where))
    _check_lifecycle(rel.lifecycle, where, issues)
    vias = {t.via for t in rel.lifecycle.transitions} if rel.lifecycle else set()
    field_names = {f.name for f in rel.fields}
    for ev in rel.events:
        if ev.kind == "on_transition" and ev.trigger not in vias:
            issues.append(ValidationIssue(
                "error",
                f"{where}: on_transition '{ev.trigger}' sin transición declarada", where))
        if ev.kind == "on_field_change" and ev.trigger not in field_names:
            issues.append(ValidationIssue(
                "error", f"{where}: on_field_change '{ev.trigger}' no es un campo", where))
