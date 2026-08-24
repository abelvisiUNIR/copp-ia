"""Façade del parser TeleFlow DSL v2 (Lark · LALR — ADR-001)."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from importlib import resources
from typing import NoReturn

from lark import Lark
from lark.exceptions import (
    UnexpectedCharacters,
    UnexpectedEOF,
    UnexpectedInput,
    UnexpectedToken,
)
from lark.lexer import PatternStr

from teleflow.dsl.ast_nodes import Expr, ExprValue, FlowFile
from teleflow.dsl.transformer import TeleFlowTransformer


class TeleFlowSyntaxError(Exception):
    def __init__(
        self,
        message: str,
        line: int | None = None,
        column: int | None = None,
        expected: list[str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        # Nombres de terminales que el parser habría aceptado (útil para tests/tooling).
        self.expected = expected if expected is not None else []


def _load_grammar() -> str:
    return (resources.files("teleflow.dsl") / "teleflow.lark").read_text(encoding="utf-8")


# Terminales definidos por regex (no por literal): etiqueta amigable en castellano.
_FRIENDLY_REGEX_TERMINALS = {
    "NAME": "un identificador",
    "STRING": "un texto entre comillas",
    "NUMBER": "un número",
    "COMP_OP": "un operador de comparación (==, !=, >=, <=, >, <)",
    "COMMENT": "un comentario",
}


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
            self._raise_syntax_error(exc, source, "Error de sintaxis")
        result = self._transformer.transform(tree)
        assert isinstance(result, FlowFile)
        return result

    def parse_expr(self, source: str) -> ExprValue:
        try:
            tree = self._lark.parse(source, start="expr")
        except UnexpectedInput as exc:
            self._raise_syntax_error(exc, source, "Expresión inválida")
        result: ExprValue = self._transformer.transform(tree)
        return result  # puede ser Expr o un literal Python

    # --- reporte de errores -------------------------------------------------

    def _describe_terminal(self, name: str) -> str:
        """Nombre de terminal Lark → descripción legible (su literal o etiqueta)."""
        if name in ("$END", "$end"):
            return "fin de archivo"
        friendly = _FRIENDLY_REGEX_TERMINALS.get(name)
        if friendly is not None:
            return friendly
        try:
            pattern = self._lark.get_terminal(name).pattern
        except (KeyError, ValueError):
            return name
        if isinstance(pattern, PatternStr) and pattern.value:
            return f"'{pattern.value}'"
        return name

    def _format_expected(
        self, expected: Iterable[str] | None
    ) -> tuple[str, list[str]]:
        """(pista legible, nombres de terminal ordenados) a partir del set de Lark."""
        names = sorted({str(t) for t in (expected or [])})
        described = sorted({self._describe_terminal(n) for n in names})
        if not described:
            return "", names
        if len(described) == 1:
            return f"se esperaba {described[0]}", names
        shown = described[:8]
        tail = ", …" if len(described) > 8 else ""
        return "se esperaba uno de: " + ", ".join(shown) + tail, names

    def _raise_syntax_error(
        self, exc: UnexpectedInput, source: str, what: str
    ) -> NoReturn:
        line = getattr(exc, "line", None)
        column = getattr(exc, "column", None)
        try:
            ctx = exc.get_context(source)
        except Exception:
            ctx = ""

        if isinstance(exc, UnexpectedToken):
            hint, expected = self._format_expected(exc.accepts or exc.expected)
            tok = exc.token
            if tok is None or tok.type == "$END" or str(tok) == "":
                head = (
                    f"{what}: fin de archivo inesperado "
                    f"en línea {line}, columna {column}"
                )
            else:
                head = (
                    f"{what}: token inesperado '{tok}' "
                    f"en línea {line}, columna {column}"
                )
        elif isinstance(exc, UnexpectedCharacters):
            hint, expected = self._format_expected(getattr(exc, "allowed", None))
            head = (
                f"{what}: carácter inesperado '{exc.char}' "
                f"en línea {line}, columna {column}"
            )
        elif isinstance(exc, UnexpectedEOF):
            hint, expected = self._format_expected(getattr(exc, "expected", None))
            head = (
                f"{what}: fin de archivo inesperado "
                f"en línea {line}, columna {column}"
            )
        else:
            hint, expected = "", []
            head = f"{what} en línea {line}, columna {column}"

        message = head if not hint else f"{head}; {hint}"
        if ctx:
            message += f"\n{ctx}"
        raise TeleFlowSyntaxError(
            message, line=line, column=column, expected=expected
        ) from exc


_default_parser: TeleFlowParser | None = None


def get_parser() -> TeleFlowParser:
    global _default_parser
    if _default_parser is None:
        _default_parser = TeleFlowParser()
    return _default_parser


def checksum(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()
