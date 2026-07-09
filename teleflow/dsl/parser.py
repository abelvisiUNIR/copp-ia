"""Façade del parser TeleFlow DSL v2 (Lark · LALR — ADR-001)."""
from __future__ import annotations

import hashlib
from importlib import resources

from lark import Lark, UnexpectedInput

from teleflow.dsl.ast_nodes import Expr, ExprValue, FlowFile
from teleflow.dsl.transformer import TeleFlowTransformer


class TeleFlowSyntaxError(Exception):
    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


def _load_grammar() -> str:
    return (resources.files("teleflow.dsl") / "teleflow.lark").read_text(encoding="utf-8")


class TeleFlowParser:
    """Parser singleton-friendly. Crear una vez, usar muchas."""

    def __init__(self) -> None:
        grammar = _load_grammar()
        self._lark = Lark(
            grammar,
            parser="lalr",
            start=["start", "expr"],
            maybe_placeholders=False,
            propagate_positions=True,
        )
        self._transformer = TeleFlowTransformer()

    def parse(self, source: str) -> FlowFile:
        try:
            tree = self._lark.parse(source, start="start")
        except UnexpectedInput as exc:
            line = getattr(exc, "line", None)
            column = getattr(exc, "column", None)
            ctx = ""
            try:
                ctx = exc.get_context(source)
            except Exception:
                pass
            raise TeleFlowSyntaxError(
                f"Error de sintaxis en línea {line}, columna {column}:\n{ctx}",
                line=line,
                column=column,
            ) from exc
        result = self._transformer.transform(tree)
        assert isinstance(result, FlowFile)
        return result

    def parse_expr(self, source: str) -> ExprValue:
        try:
            tree = self._lark.parse(source, start="expr")
        except UnexpectedInput as exc:
            raise TeleFlowSyntaxError(
                f"Expresión inválida: {source!r}",
                line=getattr(exc, "line", None),
                column=getattr(exc, "column", None),
            ) from exc
        result: ExprValue = self._transformer.transform(tree)
        return result  # puede ser Expr o un literal Python


_default_parser: TeleFlowParser | None = None


def get_parser() -> TeleFlowParser:
    global _default_parser
    if _default_parser is None:
        _default_parser = TeleFlowParser()
    return _default_parser


def checksum(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()
