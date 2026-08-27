"""parser-service :8001 — source .tflow → AST JSON validado.

Valida sintaxis (Lark LALR) y semántica. Nunca ejecuta nada.
"""
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from teleflow.common.logging import setup_logging
from teleflow.common.observability import setup_observability
from teleflow.dsl.parser import TeleFlowSyntaxError, checksum, get_parser
from teleflow.dsl.serialize import to_jsonable
from teleflow.dsl.validator import validate_flow

log = setup_logging("parser-service")

app = FastAPI(title="TeleFlow parser-service", version="1.0.0")
setup_observability(app, "parser-service")


class ParseRequest(BaseModel):
    source: str
    name: str | None = None


class IssueOut(BaseModel):
    level: str
    message: str
    block: str = ""
    # Dónde está el error, como **dato** y no solo embebido en el texto del mensaje.
    #
    # `TeleFlowSyntaxError` ya los traía; se aplastaban a string acá, en la frontera del
    # servicio, y del otro lado nadie podía llevar al revisor hasta la línea sin volver a
    # parsear la frase en castellano. Decir "línea 43, columna 62" y no poder ir ahí es la
    # peor forma de tener la información.
    #
    # Solo los errores de sintaxis los tienen: los del validador hablan de un bloque entero
    # (`process.x/stage.y`), no de una posición en el archivo.
    line: int | None = None
    column: int | None = None


class ParseResponse(BaseModel):
    valid: bool
    checksum: str
    ast: dict[str, Any] | None = None
    issues: list[IssueOut] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


@app.post("/parse", response_model=ParseResponse)
async def parse(req: ParseRequest) -> ParseResponse:
    parser = get_parser()
    csum = checksum(req.source)
    try:
        flow = parser.parse(req.source)
    except TeleFlowSyntaxError as exc:
        log.warning("parse_syntax_error", flow_name=req.name, error=exc.message)
        return ParseResponse(
            valid=False,
            checksum=csum,
            issues=[IssueOut(level="error", message=exc.message, block="syntax",
                             line=exc.line, column=exc.column)],
        )

    issues = validate_flow(flow)
    has_errors = any(i.level == "error" for i in issues)
    summary = {
        "entities": sorted(flow.entities),
        "relations": sorted(flow.relations),
        "rules": sorted(flow.rules),
        "views": sorted(flow.views),
        "processes": sorted(flow.processes),
        "steps": sorted(flow.steps),
        "integrations": sorted(flow.integrations),
    }
    log.info("parse_ok", flow_name=req.name, valid=not has_errors,
             issues=len(issues), **{k: len(v) for k, v in summary.items()})
    return ParseResponse(
        valid=not has_errors,
        checksum=csum,
        ast=to_jsonable(flow),
        issues=[IssueOut(level=i.level, message=i.message, block=i.block) for i in issues],
        summary=summary,
    )
