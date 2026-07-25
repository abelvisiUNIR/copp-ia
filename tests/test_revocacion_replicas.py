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


class _RedisContador:
    """Contador compartido: modela el `INCR`/`EXPIRE` que ven todas las réplicas."""

    def __init__(self, claves: dict[str, int] | None = None):
        self.claves = claves if claves is not None else {}
        self.expiraciones: list[tuple[str, int]] = []
        self.falla = False

    async def incr(self, clave: str) -> int:
        if self.falla:
            raise ConnectionError("redis caído")
        self.claves[clave] = self.claves.get(clave, 0) + 1
        return self.claves[clave]

    async def expire(self, clave: str, segundos: int) -> bool:
        self.expiraciones.append((clave, segundos))
        return True


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


# ------------------------------------------------- rate limit compartido

def _settings_limite(rpm: int):
    from teleflow.common.config import Settings

    return Settings(rate_limit_rpm=rpm)


async def test_el_limite_se_cuenta_en_redis_y_no_por_proceso(gateway_limpio, monkeypatch):
    """El caso que motiva el chunk: con N réplicas el límite era N× el configurado."""
    redis = _RedisContador()
    monkeypatch.setitem(main.state, "redis", redis)
    settings = _settings_limite(3)

    resultados = [await main.permite_el_limite("tf_k", settings) for _ in range(5)]

    assert resultados == [True, True, True, False, False]
    assert len(redis.claves) == 1, "todo el minuto tiene que ir a la misma clave"


async def test_dos_replicas_comparten_el_contador(gateway_limpio, monkeypatch):
    """Dos procesos, un solo Redis: el cuarto request lo corta la réplica que lo reciba."""
    compartido: dict[str, int] = {}
    replica_a = _RedisContador(compartido)
    replica_b = _RedisContador(compartido)
    settings = _settings_limite(3)

    monkeypatch.setitem(main.state, "redis", replica_a)
    assert await main.permite_el_limite("tf_k", settings) is True
    assert await main.permite_el_limite("tf_k", settings) is True

    monkeypatch.setitem(main.state, "redis", replica_b)
    assert await main.permite_el_limite("tf_k", settings) is True
    assert await main.permite_el_limite("tf_k", settings) is False, (
        "la réplica B no vio lo que consumió la A: el límite volvió a ser por proceso")


async def test_la_clave_va_hasheada_y_expira_sola(gateway_limpio, monkeypatch):
    """Redis no es lugar para una credencial, ni siquiera en el nombre de una clave."""
    redis = _RedisContador()
    monkeypatch.setitem(main.state, "redis", redis)

    await main.permite_el_limite("tf_secreto_en_claro", _settings_limite(10))

    clave = next(iter(redis.claves))
    assert "tf_secreto_en_claro" not in clave
    assert auth.hash_key("tf_secreto_en_claro") in clave
    # La primera del minuto fija el TTL: las claves se limpian solas.
    assert redis.expiraciones == [(clave, 120)]


async def test_si_redis_falla_se_degrada_al_bucket_del_proceso(gateway_limpio, monkeypatch):
    """Un limitador caído no puede tumbar el producto — pero tampoco puede dejar de limitar
    en silencio: degrada a lo que había antes, y lo cuenta."""
    redis = _RedisContador()
    redis.falla = True
    monkeypatch.setitem(main.state, "redis", redis)
    monkeypatch.setattr(main, "_buckets", {})
    settings = _settings_limite(2)

    antes = _valor(main.RATE_LIMIT_DEGRADADO)
    resultados = [await main.permite_el_limite("tf_k", settings) for _ in range(4)]

    assert resultados[:2] == [True, True]
    assert resultados[3] is False, "sin Redis igual tiene que limitar, aunque sea por proceso"
    assert _valor(main.RATE_LIMIT_DEGRADADO) == antes + 4


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
