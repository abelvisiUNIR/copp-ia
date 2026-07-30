"""Adapters de steps: REST (TMF APIs), AMQP, SMTP, SMS.

Las credenciales nunca viven en el .tflow: se referencian como ${env.VAR}
y se resuelven aquí, en tiempo de ejecución.

Si un step automated no declara integration, se ejecuta en modo "noop"
(eco del payload): útil para demos y para modelar pasos aún sin integrar.
"""
from __future__ import annotations

import asyncio
import os
import re
import smtplib
from email.message import EmailMessage
from typing import Any, Mapping

import httpx

from teleflow.common.logging import get_logger
from teleflow.common.retry import (
    RETRYABLE_STATUS,
    is_retryable_status,
    is_retryable_transport_error,
)
from teleflow.dsl.ast_nodes import IntegrationDef, StepDef
from teleflow.dsl.evaluator import evaluate

log = get_logger(component="adapters")

_ENV_RE = re.compile(r"\$\{env\.([A-Za-z_][A-Za-z0-9_]*)\}")
_CTX_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")


class StepExecutionError(Exception):
    """Fallo permanente: reintentar no lo va a arreglar (400, credencial mala, config)."""


class RetryableStepError(StepExecutionError):
    """Fallo transitorio: el mismo request más tarde puede salir bien (503, timeout, red)."""


# El criterio transitorio/permanente vive en `common.retry`: lo comparten estos adapters y
# el composer. Se re-exporta acá para no romper los imports existentes.
__all__ = ["RETRYABLE_STATUS", "is_retryable_status", "is_retryable_transport_error"]


def resolve_env(value: Any) -> Any:
    """Resuelve `${env.VAR}`, y **falla si la variable no está**.

    Antes una variable faltante se reemplazaba por cadena vacía. Eso deja pasar el deploy y el
    fallo aparece mucho después, en el peor lugar: con `base_url: "${env.LMS_URL}"` sin definir,
    el request sale a `/api/credentials` sin protocolo y el step muere con un
    `UnsupportedProtocol` que no nombra la variable. Medido: un expediente real quedó FAILED por
    esto, después de gastar 4 intentos.

    Peor todavía en las credenciales: un `Authorization: Bearer ${env.TOKEN}` sin TOKEN mandaba
    el header vacío y la integración devolvía 401 — o, si el otro lado es permisivo, salía bien
    sin autenticar.

    Es `StepExecutionError` y no `RetryableStepError` a propósito: falta configuración, y ningún
    reintento va a crearla.
    """
    if not isinstance(value, str):
        return value
    faltantes: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        nombre = match.group(1)
        # Vacía cuenta como faltante: `LMS_URL=` en el .env produce exactamente el mismo fallo
        # que no declararla, y esconderlo sería el mismo error con otra cara.
        resuelto = os.environ.get(nombre) or ""
        if not resuelto:
            faltantes.append(nombre)
        return resuelto

    salida = _ENV_RE.sub(_sub, value)
    if faltantes:
        nombres = ", ".join(dict.fromkeys(faltantes))
        raise StepExecutionError(
            f"config: falta(n) la(s) variable(s) de entorno {nombres} que el flow referencia "
            f"como ${{env.{faltantes[0]}}}. Definirla(s) en el entorno del executor."
        )
    return salida


def render_template(template: str, ctx: Mapping[str, Any]) -> str:
    """Reemplaza {payload.x} / {steps.y.z} con valores del contexto."""
    from teleflow.dsl.evaluator import resolve_ref

    def _sub(match: re.Match[str]) -> str:
        value = resolve_ref(tuple(match.group(1).split(".")), ctx)
        return "" if value is None else str(value)

    return _CTX_RE.sub(_sub, template)


def eval_payload(step: StepDef, ctx: Mapping[str, Any]) -> dict[str, Any]:
    return {key: evaluate(expr, ctx) for key, expr in step.payload.items()}


async def run_automated(step: StepDef, integration: IntegrationDef | None,
                        ctx: Mapping[str, Any]) -> dict[str, Any]:
    payload = eval_payload(step, ctx)
    if integration is None or integration.type == "mock":
        log.info("step_noop", step_name=step.name)
        return {"ok": True, "mode": "noop", "step": step.name, "payload": payload}

    itype = integration.type
    if itype == "rest":
        return await _run_rest(step, integration, payload, ctx)
    if itype == "amqp":
        return await _run_amqp(step, integration, payload)
    raise StepExecutionError(
        f"step.{step.name}: tipo de integración '{itype}' no soportado para automated"
    )


async def _run_rest(step: StepDef, integration: IntegrationDef,
                    payload: dict[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:
    base_url = resolve_env(str(integration.config.get("base_url", "")))
    path = render_template(resolve_env(step.path or "/"), ctx)
    method = (step.method or "POST").upper()
    headers: dict[str, str] = {}
    auth_header = integration.config.get("auth_header")
    if auth_header:
        headers["Authorization"] = resolve_env(str(auth_header))
    api_key_header = integration.config.get("api_key_header")
    if api_key_header:
        headers[str(api_key_header)] = resolve_env(
            str(integration.config.get("api_key", "")))
    timeout = float(step.timeout_seconds or integration.config.get("timeout", 30))

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.request(
                method, path, json=payload if method not in ("GET", "DELETE") else None,
                params=payload if method == "GET" else None, headers=headers,
            )
    except httpx.HTTPError as exc:
        # `httpx.HTTPError` es la clase base: cubre lo transitorio (timeout, DNS, conexión
        # rechazada, TLS) **y** lo que nunca va a andar (URL sin protocolo, URL inválida). Antes
        # todo caía como transitorio y un error de config gastaba los reintentos completos.
        mensaje = f"step.{step.name}: {method} {base_url}{path} → {type(exc).__name__}: {exc}"
        if is_retryable_transport_error(exc):
            raise RetryableStepError(mensaje) from exc
        raise StepExecutionError(mensaje) from exc

    if response.status_code >= 400:
        message = (f"step.{step.name}: {method} {base_url}{path} → "
                   f"{response.status_code}: {response.text[:500]}")
        if is_retryable_status(response.status_code):
            raise RetryableStepError(message)
        raise StepExecutionError(message)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    return {"ok": True, "status_code": response.status_code, "body": body}


async def _run_amqp(step: StepDef, integration: IntegrationDef,
                    payload: dict[str, Any]) -> dict[str, Any]:
    import json

    import aio_pika

    url = resolve_env(str(integration.config.get("url", "")) or
                      os.environ.get("RABBITMQ_URL", ""))
    routing_key = str(integration.config.get("routing_key", step.name))
    exchange_name = str(integration.config.get("exchange", ""))
    try:
        connection = await aio_pika.connect_robust(url)
    except (aio_pika.exceptions.AMQPError, OSError) as exc:  # broker caído / red
        raise RetryableStepError(
            f"step.{step.name}: no se pudo conectar a AMQP: {exc}") from exc
    try:
        channel = await connection.channel()
        message = aio_pika.Message(
            body=json.dumps(payload, default=str).encode("utf-8"),
            content_type="application/json",
        )
        if exchange_name:
            exchange = await channel.declare_exchange(
                exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
            await exchange.publish(message, routing_key=routing_key)
        else:
            await channel.default_exchange.publish(message, routing_key=routing_key)
    except (aio_pika.exceptions.AMQPError, OSError) as exc:
        raise RetryableStepError(
            f"step.{step.name}: publish AMQP falló: {exc}") from exc
    finally:
        await connection.close()
    return {"ok": True, "routing_key": routing_key}


async def run_notification(step: StepDef, integration: IntegrationDef | None,
                           ctx: Mapping[str, Any]) -> dict[str, Any]:
    channel = (step.channel or "email").lower()
    recipient = evaluate(step.to, ctx) if step.to is not None else None
    body = render_template(step.template or "", ctx)

    if integration is None:
        # Sin integración configurada: log estructurado (modo dev/demo)
        log.info("notification_logged", step_name=step.name, channel=channel,
                 to=recipient, body=body[:200])
        return {"ok": True, "mode": "logged", "channel": channel,
                "to": recipient, "body": body}

    if channel == "email" and integration.type == "smtp":
        return await _send_email(step, integration, str(recipient or ""), body)
    if channel == "sms":
        return await _send_sms(step, integration, str(recipient or ""), body)
    if integration.type == "rest":
        return await _run_rest(step, integration, {"to": recipient, "body": body}, ctx)
    raise StepExecutionError(
        f"step.{step.name}: canal '{channel}' incompatible con integración "
        f"'{integration.type}'"
    )


async def _send_email(step: StepDef, integration: IntegrationDef,
                      recipient: str, body: str) -> dict[str, Any]:
    host = resolve_env(str(integration.config.get("host", "localhost")))
    port = int(integration.config.get("port", 25))
    sender = resolve_env(str(integration.config.get("from_address", "teleflow@localhost")))
    username = resolve_env(str(integration.config.get("username", "")))
    password = resolve_env(str(integration.config.get("password", "")))
    subject = resolve_env(str(integration.config.get("subject", f"TeleFlow: {step.name}")))

    def _send() -> None:
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if username:
                smtp.starttls()
                smtp.login(username, password)
            smtp.send_message(msg)

    try:
        await asyncio.to_thread(_send)
    except smtplib.SMTPResponseException as exc:
        # 4xx SMTP = transitorio (mailbox lleno, greylisting); 5xx = permanente
        message = f"step.{step.name}: SMTP {exc.smtp_code}: {exc.smtp_error!r}"
        if 400 <= exc.smtp_code < 500:
            raise RetryableStepError(message) from exc
        raise StepExecutionError(message) from exc
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError) as exc:
        raise RetryableStepError(
            f"step.{step.name}: SMTP no disponible: {exc}") from exc
    return {"ok": True, "channel": "email", "to": recipient}


async def _send_sms(step: StepDef, integration: IntegrationDef,
                    recipient: str, body: str) -> dict[str, Any]:
    base_url = resolve_env(str(integration.config.get("base_url", "")))
    token = resolve_env(str(integration.config.get("token", "")))
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                base_url, json={"to": recipient, "message": body}, headers=headers
            )
    except httpx.HTTPError as exc:
        mensaje = f"step.{step.name}: SMS gateway → {type(exc).__name__}: {exc}"
        if is_retryable_transport_error(exc):
            raise RetryableStepError(mensaje) from exc
        raise StepExecutionError(mensaje) from exc

    if response.status_code >= 400:
        message = f"step.{step.name}: SMS gateway → {response.status_code}"
        if is_retryable_status(response.status_code):
            raise RetryableStepError(message)
        raise StepExecutionError(message)
    return {"ok": True, "channel": "sms", "to": recipient}
