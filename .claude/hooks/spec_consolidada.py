#!/usr/bin/env python3
"""Detector de specs consolidadas pendientes de sincronizar con Jira.

Se engancha al evento PostToolUse de Claude Code (matcher Edit|Write, ver
.claude/settings.json). Cuando alguien termina de editar el tasks.md de una feature
y lo marca `status: consolidada`, este script avisa cuantas tareas todavia no tienen
card en Jira para que el agente proponga el dry-run de la skill `sync-jira`.

No toca la red, no llama a Jira y no escribe nada: solo observa y avisa. Sale 0
siempre — un hook que rompe la sesion por un aviso es peor que no tener el aviso.

Contrato del evento (https://code.claude.com/docs/en/hooks):
  stdin  -> {"tool_name": ..., "tool_input": {"file_path": ...}, "cwd": ...}
  stdout -> {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                    "additionalContext": "..."}}
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import PurePosixPath
from typing import Any

# Una tarea ya sincronizada lleva su clave de Jira en la propia linea. Esa marca es la
# clave de idempotencia de todo el sistema: sin ella se recrearian cards en cada corrida.
CLAVE_JIRA = re.compile(r"\[[A-Z][A-Z0-9_]+-\d+\]")
ITEM_LISTA = re.compile(r"^\s*[-*]\s+\[[ xX~]\]\s+(?P<texto>.+?)\s*$")

ESTADO_ESPERADO = "consolidada"


def leer_evento() -> dict[str, Any]:
    """Lee el JSON del evento. Un stdin ilegible no es un error del usuario: se ignora."""
    try:
        datos = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def es_tasks_de_feature(ruta: str) -> bool:
    """True si la ruta es spec/features/<algo>/tasks.md, con separadores de Windows o POSIX."""
    if not ruta:
        return False
    partes = PurePosixPath(ruta.replace("\\", "/")).parts
    if len(partes) < 4 or partes[-1] != "tasks.md":
        return False
    return partes[-4] == "spec" and partes[-3] == "features"


def frontmatter(texto: str) -> dict[str, str]:
    """Parsea el frontmatter YAML plano (clave: valor).

    A mano y no con PyYAML a proposito: PyYAML es dependencia de dev del proyecto, no de
    runtime, y un hook no puede asumir que el venv del repo esta activo.
    """
    lineas = texto.splitlines()
    if not lineas or lineas[0].strip() != "---":
        return {}
    campos: dict[str, str] = {}
    for linea in lineas[1:]:
        if linea.strip() == "---":
            break
        clave, sep, valor = linea.partition(":")
        if sep and not clave.startswith((" ", "\t", "#")):
            campos[clave.strip()] = valor.strip()
    return campos


def cuerpo(texto: str) -> str:
    """El markdown que sigue al frontmatter."""
    partes = texto.split("---", 2)
    return partes[2] if texto.lstrip().startswith("---") and len(partes) == 3 else texto


def tareas_sin_card(texto: str) -> list[str]:
    """Items de lista que todavia no llevan una clave de Jira."""
    pendientes: list[str] = []
    for linea in cuerpo(texto).splitlines():
        item = ITEM_LISTA.match(linea)
        if item and not CLAVE_JIRA.search(item.group("texto")):
            pendientes.append(item.group("texto"))
    return pendientes


def aviso(ruta: str, campos: dict[str, str], pendientes: list[str]) -> str:
    cuantas = len(pendientes)
    plural = "tarea" if cuantas == 1 else "tareas"
    destino = campos.get("jira_project") or "(jira_project sin definir en el frontmatter)"
    muestra = "\n".join(f"  - {t}" for t in pendientes[:5])
    if cuantas > 5:
        muestra += f"\n  - ... y {cuantas - 5} mas"
    return (
        f"`{ruta}` quedo marcado `status: {ESTADO_ESPERADO}` y tiene {cuantas} {plural} "
        f"sin card en Jira (proyecto destino: {destino}):\n{muestra}\n\n"
        "Corresponde invocar la skill `sync-jira` EN MODO DRY-RUN: mostrar el listado exacto "
        "de cards que se crearian y esperar el OK explicito del usuario antes de crear nada. "
        "No crear issues sin esa confirmacion."
    )


def main() -> int:
    evento = leer_evento()
    entrada = evento.get("tool_input")
    ruta = entrada.get("file_path", "") if isinstance(entrada, dict) else ""
    if not isinstance(ruta, str) or not es_tasks_de_feature(ruta):
        return 0

    try:
        with open(ruta, encoding="utf-8") as archivo:
            texto = archivo.read()
    except OSError:
        # El archivo se movio o se borro entre la edicion y el hook. No es asunto nuestro.
        return 0

    campos = frontmatter(texto)
    if campos.get("status") != ESTADO_ESPERADO:
        return 0

    pendientes = tareas_sin_card(texto)
    if not pendientes:
        return 0

    salida = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": aviso(ruta, campos, pendientes),
        }
    }
    json.dump(salida, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
