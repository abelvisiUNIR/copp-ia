"""Bus de eventos de dominio — RabbitMQ topic exchange (ADR-004).

Sistemas externos se suscriben con routing keys tipo `nino.*` sin
acoplamiento directo. Si RabbitMQ no está disponible, los eventos se
loguean y el sistema sigue funcionando (degradación controlada en dev).

Resiliencia del consumo: un evento cuyo procesamiento falla se reintenta
`max_attempts` veces con backoff y, si sigue fallando, se manda a la DLQ
(`<queue>.dlq`, vía el dead-letter exchange `<exchange>.dlx`) en vez de
descartarse. Un evento con body ilegible es veneno: va directo a la DLQ.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

import aio_pika
from prometheus_client import Counter

from teleflow.common.logging import get_logger

log = get_logger(component="event-bus")

EVENTS_CONSUMED_TOTAL = Counter(
    "teleflow_events_consumed_total",
    "Eventos consumidos del bus por resultado",
    ["queue", "result"],  # ok | retried | dead_lettered
)
EVENTS_PUBLISHED_TOTAL = Counter(
    "teleflow_events_published_total",
    "Eventos publicados al bus por resultado",
    ["result"],  # ok | failed
)

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]

MAX_BACKOFF_SECONDS = 30.0

# Colas replicadas por consenso: sobreviven a que se caiga el nodo donde vivían. Una cola
# clásica vive en **un** nodo por más que el cluster tenga tres, así que sin esto la DLQ y los
# eventos de rules siguen teniendo un único punto de fallo aunque el broker esté en cluster.
#
# Esto no se puede resolver desde afuera: el tipo lo fija quien **declara** la cola, y eso es
# este código. Un RabbitMQ administrado en cluster no convierte una cola clásica en quorum.
#
# Los argumentos de una cola son **inmutables**: cambiar esto en una cola que ya existe hace
# fallar la declaración con PRECONDITION_FAILED. Por eso el nombre está versionado en
# `Settings.rules_queue` y esta migración es `v1` -> `v2`.
QUORUM: dict[str, Any] = {"x-queue-type": "quorum"}


class EventBus:
    def __init__(self, url: str, exchange_name: str = "teleflow.domain.events",
                 max_attempts: int = 3, retry_base_delay: float = 1.0):
        self._url = url
        self._exchange_name = exchange_name
        self._dlx_name = f"{exchange_name}.dlx"
        self._max_attempts = max(1, max_attempts)
        self._retry_base_delay = retry_base_delay
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._dlx: aio_pika.abc.AbstractExchange | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._lock:
            if self._exchange is not None:
                return
            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()
            self._exchange = await self._channel.declare_exchange(
                self._exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
            )
            self._dlx = await self._channel.declare_exchange(
                self._dlx_name, aio_pika.ExchangeType.TOPIC, durable=True
            )
            log.info("event_bus_connected", exchange=self._exchange_name,
                     dlx=self._dlx_name)

    async def publish(self, routing_key: str, message: dict[str, Any]) -> None:
        """Publica con reintentos. Si se agotan, loguea y sigue (no tumba el flujo)."""
        body = json.dumps(message, default=str).encode("utf-8")
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                if self._exchange is None:
                    await self.connect()
                assert self._exchange is not None
                await self._exchange.publish(
                    aio_pika.Message(
                        body=body,
                        content_type="application/json",
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=routing_key,
                )
                EVENTS_PUBLISHED_TOTAL.labels("ok").inc()
                log.info("event_published", routing_key=routing_key)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                log.warning("event_publish_attempt_failed", routing_key=routing_key,
                            attempt=attempt, max_attempts=self._max_attempts,
                            error=str(exc))
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._backoff(attempt))

        EVENTS_PUBLISHED_TOTAL.labels("failed").inc()
        log.error("event_publish_failed", routing_key=routing_key,
                  attempts=self._max_attempts, error=str(last_error))

    async def consume(self, queue_name: str, callback: EventCallback) -> None:
        """Consume todos los eventos del exchange (binding '#'), con DLQ."""
        if self._channel is None:
            await self.connect()
        assert self._channel is not None and self._exchange is not None
        assert self._dlx is not None

        queue = await self._channel.declare_queue(
            queue_name, durable=True,
            arguments={"x-dead-letter-exchange": self._dlx_name, **QUORUM},
        )
        await queue.bind(self._exchange, routing_key="#")

        # La DLQ también quorum: es donde terminan los eventos que ya fallaron, o sea justo lo
        # que no se puede volver a perder. Una DLQ clásica en un cluster vive en un nodo y se va
        # con él.
        dlq = await self._channel.declare_queue(
            f"{queue_name}.dlq", durable=True, arguments=dict(QUORUM),
        )
        await dlq.bind(self._dlx, routing_key="#")
        log.info("event_consumer_started", queue=queue_name, dlq=f"{queue_name}.dlq")

        async with queue.iterator() as it:
            async for message in it:
                await self.handle_message(queue_name, message, callback)

    async def handle_message(self, queue_name: str,
                             message: aio_pika.abc.AbstractIncomingMessage,
                             callback: EventCallback) -> None:
        """ACK si el callback funciona; reintenta con backoff; si no, a la DLQ.

        Público para poder testearlo sin broker.
        """
        routing_key = message.routing_key or ""
        try:
            payload = json.loads(message.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            # veneno: reintentar no lo va a arreglar
            await message.reject(requeue=False)
            EVENTS_CONSUMED_TOTAL.labels(queue_name, "dead_lettered").inc()
            log.error("event_dead_lettered", queue=queue_name,
                      routing_key=routing_key, reason="body ilegible", error=str(exc))
            return

        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                await callback(routing_key, payload)
                await message.ack()
                EVENTS_CONSUMED_TOTAL.labels(queue_name, "ok").inc()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                log.warning("event_handling_attempt_failed", queue=queue_name,
                            routing_key=routing_key, attempt=attempt,
                            max_attempts=self._max_attempts, error=str(exc))
                if attempt < self._max_attempts:
                    EVENTS_CONSUMED_TOTAL.labels(queue_name, "retried").inc()
                    await asyncio.sleep(self._backoff(attempt))

        await message.reject(requeue=False)  # -> DLX -> <queue>.dlq
        EVENTS_CONSUMED_TOTAL.labels(queue_name, "dead_lettered").inc()
        log.error("event_dead_lettered", queue=queue_name, routing_key=routing_key,
                  reason=f"agotó {self._max_attempts} intentos", error=str(last_error))

    def _backoff(self, attempt: int) -> float:
        return min(self._retry_base_delay * float(2 ** (attempt - 1)),
                   MAX_BACKOFF_SECONDS)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._exchange = None
            self._dlx = None
