"""Bus de eventos de dominio — RabbitMQ topic exchange (ADR-004).

Sistemas externos se suscriben con routing keys tipo `nino.*` sin
acoplamiento directo. Si RabbitMQ no está disponible, los eventos se
loguean y el sistema sigue funcionando (degradación controlada en dev).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import aio_pika

from teleflow.common.logging import get_logger

log = get_logger(component="event-bus")


class EventBus:
    def __init__(self, url: str, exchange_name: str = "teleflow.domain.events"):
        self._url = url
        self._exchange_name = exchange_name
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
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
            log.info("event_bus_connected", exchange=self._exchange_name)

    async def publish(self, routing_key: str, message: dict[str, Any]) -> None:
        try:
            if self._exchange is None:
                await self.connect()
            assert self._exchange is not None
            await self._exchange.publish(
                aio_pika.Message(
                    body=json.dumps(message, default=str).encode("utf-8"),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=routing_key,
            )
            log.info("event_published", routing_key=routing_key)
        except Exception as exc:
            log.error("event_publish_failed", routing_key=routing_key, error=str(exc))

    async def consume(self, queue_name: str, callback) -> None:  # type: ignore[no-untyped-def]
        """Consume todos los eventos del exchange (binding '#')."""
        if self._channel is None:
            await self.connect()
        assert self._channel is not None and self._exchange is not None
        queue = await self._channel.declare_queue(queue_name, durable=True)
        await queue.bind(self._exchange, routing_key="#")
        async with queue.iterator() as it:
            async for message in it:
                async with message.process(ignore_processed=True):
                    try:
                        payload = json.loads(message.body.decode("utf-8"))
                        await callback(message.routing_key, payload)
                    except Exception as exc:
                        log.error("event_consume_error", error=str(exc))

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._exchange = None
