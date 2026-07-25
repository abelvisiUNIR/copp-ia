"""Revocación de keys entre réplicas del gateway.

`seguridad-api-keys` construyó la revocación para que el corte fuera **inmediato**, sin
esperar los 30 s del TTL. Con más de una réplica esa promesa era falsa: el `DELETE` purgaba el
cache del proceso que lo atendió y los demás seguían aceptando la credencial hasta que venciera
su propio TTL. Para una key filtrada, esos segundos son justo lo que la revocación evita.

`helm/teleflow/values.yaml:28` ya declara `replicas: 2`, así que no era hipotético.
"""
from typing import Any

import pytest

from teleflow.gateway import auth, main


class _RedisFalso:
    """Un bus en memoria: lo publicado se entrega a los suscriptores registrados."""

    def __init__(self, bus: list[tuple[str, str]] | None = None):
        self.bus = bus if bus is not None else []
        self.publicados: list[tuple[str, str]] = []
        self.falla_al_publicar = False

    async def publish(self, canal: str, dato: str) -> None:
        if self.falla_al_publicar:
            raise ConnectionError("redis caído")
        self.publicados.append((canal, dato))
        self.bus.append((canal, dato))


def _identidad(nombre: str) -> auth.Identidad:
    return auth.Identidad(name=nombre, scopes=frozenset({auth.FLOWS_READ}))


@pytest.fixture
def gateway_limpio(monkeypatch):
    """Cache y estado del proceso aislados por test."""
    monkeypatch.setattr(main, "_cache_keys", {})
    monkeypatch.setitem(main.state, "redis", None)
    return main


# ------------------------------------------------- el caso que importa

async def test_revocar_anuncia_a_las_demas_replicas(gateway_limpio, monkeypatch):
    """Sin este anuncio, la otra réplica sigue aceptando la key hasta que venza su TTL."""
    redis = _RedisFalso()
    monkeypatch.setitem(main.state, "redis", redis)
    hash_key = auth.hash_key("tf_secreto")

    await main.anunciar_revocacion(hash_key)

    assert redis.publicados == [(main.CANAL_REVOCACIONES, hash_key)]


async def test_la_replica_que_escucha_purga_su_cache(gateway_limpio):
    """La otra mitad: recibir el anuncio tiene que sacar la key del cache local."""
    hash_key = auth.hash_key("tf_secreto")
    main._cache_keys[hash_key] = (_identidad("integracion-ceibal"), 1e12)  # vigente

    main.purgar_cache(hash_key)

    assert hash_key not in main._cache_keys


async def test_revocar_purga_local_aunque_no_haya_redis(gateway_limpio):
    """Sin Redis el gateway no se rompe: queda la purga local y el TTL como techo."""
    hash_key = auth.hash_key("tf_secreto")
    main._cache_keys[hash_key] = (_identidad("integracion-ceibal"), 1e12)

    await main.anunciar_revocacion(hash_key)  # state["redis"] es None

    assert hash_key not in main._cache_keys


# ------------------------------------------------- que la degradación se vea

async def test_si_el_anuncio_falla_no_rompe_pero_se_cuenta(gateway_limpio, monkeypatch):
    """Que el anuncio falle no puede ser invisible: la ventana vuelve a ser el TTL entero."""
    redis = _RedisFalso()
    redis.falla_al_publicar = True
    monkeypatch.setitem(main.state, "redis", redis)
    hash_key = auth.hash_key("tf_secreto")
    main._cache_keys[hash_key] = (_identidad("integracion-ceibal"), 1e12)

    antes = _valor(main.REVOCACIONES_NO_PUBLICADAS)
    await main.anunciar_revocacion(hash_key)  # no levanta

    assert hash_key not in main._cache_keys, "la purga local tiene que pasar igual"
    assert _valor(main.REVOCACIONES_NO_PUBLICADAS) == antes + 1


def _valor(contador: Any) -> float:
    return float(contador._value.get())


# ------------------------------------------------- las dos réplicas juntas

async def test_dos_replicas_comparten_la_revocacion(gateway_limpio, monkeypatch):
    """El escenario completo: la réplica A revoca y la réplica B deja de aceptar la key.

    Se simulan dos caches (uno por proceso) y el bus entre ellos.
    """
    hash_key = auth.hash_key("tf_filtrada")
    cache_a: dict[str, Any] = {hash_key: (_identidad("filtrada"), 1e12)}
    cache_b: dict[str, Any] = {hash_key: (_identidad("filtrada"), 1e12)}
    redis = _RedisFalso()
    monkeypatch.setitem(main.state, "redis", redis)

    # Réplica A atiende el DELETE
    monkeypatch.setattr(main, "_cache_keys", cache_a)
    await main.anunciar_revocacion(hash_key)
    assert hash_key not in cache_a

    # La key sigue viva en B hasta que llega el anuncio
    assert hash_key in cache_b, "precondición: B todavía la tenía cacheada"

    # Réplica B recibe el mensaje del bus y aplica la purga
    monkeypatch.setattr(main, "_cache_keys", cache_b)
    canal, dato = redis.bus[-1]
    assert canal == main.CANAL_REVOCACIONES
    main.purgar_cache(dato)

    assert hash_key not in cache_b, "B siguió aceptando una credencial revocada"
