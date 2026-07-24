"""Tests del bus de eventos: reintentos, DLQ y publish resiliente.

Sin broker: se usa un mensaje falso que registra ack/reject, como haría aio_pika.
`retry_base_delay=0` para que el backoff no duerma de verdad.
"""
import pytest

from teleflow.executor_service.events import EventBus


class FakeMessage:
    """Mínimo de aio_pika.abc.AbstractIncomingMessage que usa handle_message."""

    def __init__(self, body: bytes, routing_key: str = "nino.inscrito"):
        self.body = body
        self.routing_key = routing_key
        self.acked = False
        self.rejected_requeue = None  # None = nunca rechazado

    async def ack(self):
        self.acked = True

    async def reject(self, requeue: bool = True):
        self.rejected_requeue = requeue


def make_bus(max_attempts: int = 3) -> EventBus:
    return EventBus("amqp://fake", "teleflow.domain.events",
                    max_attempts=max_attempts, retry_base_delay=0)


# ------------------------------------------------------------ consumo con DLQ

async def test_handle_message_ok_ackea():
    bus = make_bus()
    message = FakeMessage(b'{"event": "nino.inscrito"}')
    recibidos = []

    async def callback(routing_key, payload):
        recibidos.append((routing_key, payload))

    await bus.handle_message("q", message, callback)

    assert recibidos == [("nino.inscrito", {"event": "nino.inscrito"})]
    assert message.acked is True
    assert message.rejected_requeue is None


async def test_handle_message_falla_transitoria_se_recupera():
    """Falla el 1er intento y anda el 2do: se ACKea, no va a la DLQ."""
    bus = make_bus(max_attempts=3)
    message = FakeMessage(b'{"event": "nino.inscrito"}')
    intentos = []

    async def callback(routing_key, payload):
        intentos.append(1)
        if len(intentos) == 1:
            raise RuntimeError("DB caída un segundo")

    await bus.handle_message("q", message, callback)

    assert len(intentos) == 2
    assert message.acked is True
    assert message.rejected_requeue is None


async def test_handle_message_falla_siempre_va_a_la_dlq():
    """Agotados los intentos: reject(requeue=False) -> DLX -> <queue>.dlq. Nunca ACK."""
    bus = make_bus(max_attempts=3)
    message = FakeMessage(b'{"event": "nino.inscrito"}')
    intentos = []

    async def callback(routing_key, payload):
        intentos.append(1)
        raise RuntimeError("rule rota")

    await bus.handle_message("q", message, callback)

    assert len(intentos) == 3                    # reintentó max_attempts veces
    assert message.acked is False                # el evento NO se descarta en silencio
    assert message.rejected_requeue is False     # requeue=False = va a la DLQ


async def test_handle_message_body_ilegible_va_directo_a_la_dlq():
    """Veneno: reintentar no lo arregla, se manda a la DLQ sin llamar al callback."""
    bus = make_bus()
    message = FakeMessage(b"esto no es json")
    llamadas = []

    async def callback(routing_key, payload):
        llamadas.append(1)

    await bus.handle_message("q", message, callback)

    assert llamadas == []
    assert message.acked is False
    assert message.rejected_requeue is False


async def test_handle_message_cancelled_no_se_traga():
    """CancelledError (shutdown) se propaga: el mensaje queda sin ACK y se redelivera."""
    bus = make_bus()
    message = FakeMessage(b"{}")

    async def callback(routing_key, payload):
        raise __import__("asyncio").CancelledError()

    import asyncio

    with pytest.raises(asyncio.CancelledError):
        await bus.handle_message("q", message, callback)

    assert message.acked is False
    assert message.rejected_requeue is None


# ------------------------------------------------------------------- publish

class FakeExchange:
    def __init__(self, fallos: int):
        self.fallos = fallos
        self.publicados = []

    async def publish(self, message, routing_key):
        if self.fallos > 0:
            self.fallos -= 1
            raise RuntimeError("broker no disponible")
        self.publicados.append(routing_key)


async def test_publish_reintenta_y_sale_bien():
    bus = make_bus(max_attempts=3)
    exchange = FakeExchange(fallos=2)
    bus._exchange = exchange

    await bus.publish("nino.inscrito", {"event": "nino.inscrito"})

    assert exchange.publicados == ["nino.inscrito"]


async def test_publish_agotado_no_tumba_el_flujo():
    """Degradación controlada (ADR-004): si el broker no vuelve, se loguea y sigue."""
    bus = make_bus(max_attempts=3)
    exchange = FakeExchange(fallos=99)
    bus._exchange = exchange

    await bus.publish("nino.inscrito", {"event": "nino.inscrito"})  # no levanta

    assert exchange.publicados == []
    assert exchange.fallos == 96      # consumió exactamente 3 intentos


# ------------------------------------------------------------------- backoff

def test_backoff_exponencial_con_tope():
    bus = EventBus("amqp://fake", max_attempts=10, retry_base_delay=1.0)
    assert bus._backoff(1) == 1.0
    assert bus._backoff(2) == 2.0
    assert bus._backoff(3) == 4.0
    assert bus._backoff(10) == 30.0   # tope MAX_BACKOFF_SECONDS
