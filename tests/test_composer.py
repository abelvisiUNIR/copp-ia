"""Tests del composer: que no mienta sobre qué proveedor generó el borrador.

Antes, `LLM_PROVIDER=anthropic` sin credencial devolvía el `StubProvider` con un `warning`:
`POST /compose` respondía 201, el analista recibía un esqueleto con `TODO:` creyendo que lo
había generado el modelo, y el log registraba el proveedor *pedido*. Estos tests fijan que
el stub solo aparece cuando se lo pide explícitamente.
"""
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from teleflow.common.config import Settings
from teleflow.composer_service import providers
from teleflow.composer_service.main import _validate_source
from teleflow.composer_service.providers import (
    AnthropicProvider,
    LLMConfigurationError,
    OllamaProvider,
    OpenAIProvider,
    StubProvider,
    get_provider,
)

ROOT = Path(__file__).resolve().parent.parent


def _settings(provider, api_key=""):
    """Settings explícitas: los kwargs ganan sobre el `.env` que pueda existir en el repo."""
    return Settings(llm_provider=provider, llm_api_key=api_key)


# ------------------------------------------- el stub solo si se lo pide

@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_proveedor_real_sin_credencial_levanta(provider):
    with pytest.raises(LLMConfigurationError) as exc:
        get_provider(_settings(provider))

    mensaje = str(exc.value)
    assert "LLM_API_KEY" in mensaje
    # El error tiene que decir cómo salir, no solo qué falta.
    assert "stub" in mensaje


@pytest.mark.parametrize("provider", ["anthropic", "openai", "ollama"])
def test_ningun_proveedor_real_devuelve_el_stub(provider):
    """La regresión que importa: pedir un LLM real y recibir el esqueleto de mentira."""
    try:
        instancia = get_provider(_settings(provider, api_key="k"))
    except LLMConfigurationError:
        return  # falló explícitamente, que es el otro final aceptable
    assert not isinstance(instancia, StubProvider)
    assert instancia.name == provider


def test_stub_solo_cuando_se_lo_pide():
    instancia = get_provider(_settings("stub"))
    assert isinstance(instancia, StubProvider)
    assert instancia.name == "stub"


# ------------------------------------------- construcción de cada proveedor

def test_anthropic_con_credencial():
    assert isinstance(get_provider(_settings("anthropic", api_key="k")), AnthropicProvider)


def test_openai_con_credencial():
    assert isinstance(get_provider(_settings("openai", api_key="k")), OpenAIProvider)


def test_ollama_no_necesita_credencial():
    """Self-hosted: la credencial no aplica, así que su ausencia no puede ser un error."""
    assert isinstance(get_provider(_settings("ollama")), OllamaProvider)


@pytest.mark.parametrize("valor", ["  Anthropic ", "STUB", "OpenAI"])
def test_el_valor_se_normaliza(valor):
    """Un `LLM_PROVIDER` con mayúsculas o espacios no puede caer en 'desconocido'."""
    instancia = get_provider(_settings(valor, api_key="k"))
    assert instancia.name == valor.strip().lower()


@pytest.mark.parametrize("typo", ["antropic", "gpt", "claude", ""])
def test_proveedor_desconocido_levanta(typo):
    """Un typo antes devolvía el stub sin siquiera loguear un warning."""
    with pytest.raises(LLMConfigurationError) as exc:
        get_provider(_settings(typo, api_key="k"))
    assert "no es un proveedor conocido" in str(exc.value)


# ------------------------------------------- reintentos: solo lo transitorio

class _RespuestaHTTP:
    """Respuesta con status arbitrario, para probar la clasificación."""

    def __init__(self, status_code, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload


class _ClienteSecuencia:
    """Devuelve (o levanta) un elemento por llamada, y cuenta los intentos."""

    def __init__(self, secuencia):
        self.secuencia = list(secuencia)
        self.llamadas = 0

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        item = self.secuencia[min(self.llamadas, len(self.secuencia) - 1)]
        self.llamadas += 1
        if isinstance(item, Exception):
            raise item
        return item


def _proveedor_responde(monkeypatch, secuencia):
    import httpx

    cliente = _ClienteSecuencia(secuencia)
    monkeypatch.setattr(httpx, "AsyncClient", cliente)
    return cliente


def _settings_llm(**kwargs):
    # base/max delay en 0: los tests prueban la decisión de reintentar, no el reloj.
    base: dict[str, Any] = dict(llm_provider="anthropic", llm_api_key="k",
                                llm_retry_attempts=3, llm_retry_base_delay=0.0,
                                llm_retry_max_delay=0.0)
    base.update(kwargs)
    return Settings(**base)


async def test_un_503_se_reintenta_y_puede_salir_bien(monkeypatch):
    ok = _RespuestaHTTP(200, {"stop_reason": "end_turn",
                              "content": [{"type": "text", "text": "process \"x\" {}"}]})
    cliente = _proveedor_responde(monkeypatch, [_RespuestaHTTP(503, text="upstream caido"), ok])

    texto = await providers.AnthropicProvider(_settings_llm()).generate("dale")

    assert texto == "process \"x\" {}"
    assert cliente.llamadas == 2  # reintentó una vez


async def test_un_400_falla_al_primer_intento(monkeypatch):
    """Lo permanente no gasta la ventana de reintentos: reintentar no lo va a arreglar."""
    cliente = _proveedor_responde(monkeypatch, [_RespuestaHTTP(400, text="prompt invalido")])

    with pytest.raises(providers.LLMRequestRejected):
        await providers.AnthropicProvider(_settings_llm()).generate("dale")

    assert cliente.llamadas == 1


async def test_un_429_se_reintenta(monkeypatch):
    """408 y 429 son transitorios pese a ser 4xx (mismo criterio que los adapters)."""
    ok = _RespuestaHTTP(200, {"stop_reason": "end_turn",
                              "content": [{"type": "text", "text": "ok"}]})
    cliente = _proveedor_responde(
        monkeypatch, [_RespuestaHTTP(429, text="slow down", headers={"retry-after": "0"}), ok])

    assert await providers.AnthropicProvider(_settings_llm()).generate("dale") == "ok"
    assert cliente.llamadas == 2


async def test_transitorio_persistente_agota_intentos(monkeypatch):
    cliente = _proveedor_responde(monkeypatch, [_RespuestaHTTP(503, text="caido")])

    with pytest.raises(providers.LLMTransientError):
        await providers.AnthropicProvider(_settings_llm()).generate("dale")

    assert cliente.llamadas == 3  # llm_retry_attempts


@pytest.mark.parametrize("status", [401, 403, 404])
async def test_credencial_o_modelo_mal_es_config_nuestra(monkeypatch, status):
    """No es culpa del pedido: es la instalación. Se distingue para no devolver 422."""
    _proveedor_responde(monkeypatch, [_RespuestaHTTP(status, text="nope")])

    with pytest.raises(LLMConfigurationError):
        await providers.AnthropicProvider(_settings_llm()).generate("dale")


# ------------------------------------------- respuestas que llegan con 200 y no sirven

async def test_refusal_no_revienta_con_indexerror(monkeypatch):
    """Un rechazo por políticas llega 200 y sin texto: antes era un IndexError opaco."""
    _proveedor_responde(monkeypatch, [_RespuestaHTTP(200, {"stop_reason": "refusal",
                                                          "content": []})])

    with pytest.raises(providers.LLMRequestRejected) as exc:
        await providers.AnthropicProvider(_settings_llm()).generate("dale")
    # El tipo de excepción no alcanza: el guard genérico de "sin texto" también lo atraparía.
    # Lo que se fija acá es que el mensaje diga *qué pasó* y qué puede hacer el analista.
    assert "declinó" in str(exc.value)
    assert "Reformulá" in str(exc.value)


async def test_respuesta_truncada_no_se_guarda_como_borrador(monkeypatch):
    """Cortada por max_tokens = no es un borrador, y el arreglo está en la config."""
    _proveedor_responde(monkeypatch, [_RespuestaHTTP(200, {
        "stop_reason": "max_tokens",
        "content": [{"type": "text", "text": "process \"a_medio_"}]})])

    with pytest.raises(LLMConfigurationError) as exc:
        await providers.AnthropicProvider(_settings_llm()).generate("dale")
    assert "LLM_MAX_TOKENS" in str(exc.value)


async def test_openai_truncado_tambien_se_detecta(monkeypatch):
    _proveedor_responde(monkeypatch, [_RespuestaHTTP(200, {
        "choices": [{"finish_reason": "length", "message": {"content": "process \"a"}}]})])

    with pytest.raises(LLMConfigurationError):
        await providers.OpenAIProvider(_settings_llm(llm_provider="openai")).generate("dale")


async def test_max_tokens_viaja_en_el_payload(monkeypatch):
    """El techo dejó de estar hardcodeado, y OpenAI/Ollama antes no lo mandaban."""
    capturado: dict[str, Any] = {}

    class _Captura(_ClienteSecuencia):
        async def post(self, url, headers=None, json=None):
            capturado.update(json or {})
            return await super().post(url, headers=headers, json=json)

    import httpx

    ok = _RespuestaHTTP(200, {"choices": [{"finish_reason": "stop",
                                           "message": {"content": "ok"}}]})
    monkeypatch.setattr(httpx, "AsyncClient", _Captura([ok]))

    await providers.OpenAIProvider(
        _settings_llm(llm_provider="openai", llm_max_tokens=1234)).generate("dale")

    assert capturado["max_tokens"] == 1234


# ------------------------------------------- validación del borrador contra el parser

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Reemplaza a `httpx.AsyncClient`: devuelve un payload fijo o levanta."""

    def __init__(self, resultado):
        self._resultado = resultado

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        if isinstance(self._resultado, Exception):
            raise self._resultado
        return _FakeResponse(self._resultado)


def _parser_responde(monkeypatch, resultado):
    """`resultado` es el payload que devuelve el parser, o la excepción que levanta."""
    import httpx

    # `main` hace `import httpx` y usa `httpx.AsyncClient`, así que alcanza con el módulo.
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient(resultado))


async def test_borrador_que_compila_queda_marcado_ok(monkeypatch):
    _parser_responde(monkeypatch, {"valid": True, "issues": []})
    validation = await _validate_source("process \"x\" {}", "x")

    assert validation["parses"] is True
    assert validation["issues"] == []
    assert validation["checked_at"]


async def test_borrador_que_no_compila_se_marca_pero_no_levanta(monkeypatch):
    """No se rechaza: la generación ya se pagó y suele estar a dos líneas de compilar."""
    issues = [{"level": "error", "message": "falta '}'", "block": "syntax"}]
    _parser_responde(monkeypatch, {"valid": False, "issues": issues})
    validation = await _validate_source("process \"x\" {", "x")

    assert validation["parses"] is False
    assert validation["issues"] == issues


async def test_parser_caido_no_se_confunde_con_compila(monkeypatch):
    """`parses: None` es "no se pudo verificar", que no es lo mismo que "compila"."""
    import httpx

    _parser_responde(monkeypatch, httpx.ConnectError("parser caído"))
    validation = await _validate_source("process \"x\" {}", "x")

    assert validation["parses"] is None  # ni True ni False
    assert "error" in validation


async def test_un_bug_nuestro_no_se_disfraza_de_parser_caido(monkeypatch):
    """Solo transporte y respuesta ilegible se absorben; el resto tiene que propagarse."""
    _parser_responde(monkeypatch, RuntimeError("bug nuestro"))

    with pytest.raises(RuntimeError):
        await _validate_source("process \"x\" {}", "x")


class _FakeSession:
    """Lo mínimo que usa `compose`: acumular y confirmar."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


async def test_compose_guarda_el_borrador_marcado(monkeypatch):
    """Que `_validate_source` funcione no sirve si `compose` no la llama.

    Verifica el camino completo: el borrador que se persiste lleva el proveedor que lo
    generó y el resultado del parser, y ambos viajan en la respuesta.
    """
    from teleflow.common.config import get_settings
    from teleflow.composer_service.main import ComposeRequest, compose

    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    _parser_responde(monkeypatch, {"valid": False, "issues": [{"level": "error",
                                                              "message": "falta '}'",
                                                              "block": "syntax"}]})
    session = _FakeSession()
    try:
        salida = await compose(
            ComposeRequest(name="alta_socio", description="alta de socio"),
            session=cast(AsyncSession, session),
        )
    finally:
        get_settings.cache_clear()

    draft = session.added[0]
    assert draft.provider == "stub"
    assert draft.validation["parses"] is False
    assert salida["provider"] == "stub"
    assert salida["validation"]["issues"][0]["message"] == "falta '}'"


# ------------------------------------------- el cableado, no solo la función

def test_el_servicio_no_arranca_sin_credencial(monkeypatch):
    """Que `get_provider` levante no sirve si nadie lo llama al arrancar.

    Verifica el camino completo: `lifespan` construye el proveedor, así que el contenedor
    falla en el `up` y no sirviendo 201 mentirosos.
    """
    from fastapi.testclient import TestClient

    from teleflow.common.config import get_settings
    from teleflow.composer_service.main import app

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(LLMConfigurationError):
            with TestClient(app):
                pass  # pragma: no cover — el startup no debería llegar acá
    finally:
        get_settings.cache_clear()


# ------------------------------------------- guard del .env.example

def test_env_example_arranca_sin_credenciales():
    """Un clon nuevo del repo tiene que poder levantar el stack sin conseguir una API key.

    Con `LLM_PROVIDER` real y `LLM_API_KEY` vacía, `composer-service` ya no arranca — así que
    esa combinación en el ejemplo dejaría el stack roto de fábrica.
    """
    lineas = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    valores = dict(
        linea.split("=", 1) for linea in lineas
        if "=" in linea and not linea.strip().startswith("#")
    )
    provider = valores.get("LLM_PROVIDER", "").strip()
    api_key = valores.get("LLM_API_KEY", "").strip()

    if not api_key:
        assert provider in ("stub", ""), (
            f".env.example trae LLM_PROVIDER={provider!r} sin LLM_API_KEY: "
            f"composer-service no arrancaría en un clon nuevo."
        )


# ------------------------------------------- corregir el borrador a mano
#
# El revisor veía el error con línea y columna y no tenía dónde corregirlo: tenía que salir a
# una terminal a cambiar una línea. Estos tests fijan las tres garantías del endpoint, que son
# la razón por la que no alcanza con que la interfaz escriba la columna.


class _SesionConBorrador:
    """Lo mínimo que usa `edit_draft_source`: recuperar por id y confirmar."""

    def __init__(self, draft):
        self.draft = draft
        self.commits = 0

    async def get(self, _modelo, _pk):
        return self.draft

    async def commit(self):
        self.commits += 1


def _borrador(source="process \"x\" {}", status="pending", source_generado=None):
    from teleflow.common.models import FlowDraft

    return FlowDraft(id=uuid.uuid4(), name="licencias", description="pedido original",
                     source=source, status=status, comments=[],
                     provider="ollama", validation={"parses": False, "issues": []},
                     source_generado=source_generado)


async def _editar(session, monkeypatch, source, **kwargs):
    from teleflow.composer_service.main import EditRequest, edit_draft_source

    return await edit_draft_source(
        session.draft.id,
        EditRequest(source=source, **kwargs),
        session=cast(AsyncSession, session),
    )


async def test_editar_revalida_contra_el_parser(monkeypatch):
    """La corrección no se cree a sí misma: el veredicto lo vuelve a dar el parser.

    Es lo que impide que el badge quede afirmando algo viejo sobre código nuevo — el modo de
    falla más peligroso de toda la pantalla.
    """
    session = _SesionConBorrador(_borrador())
    _parser_responde(monkeypatch, {"valid": True, "issues": []})

    salida = await _editar(session, monkeypatch, "process \"y\" { }")

    assert session.draft.source == "process \"y\" { }"
    assert session.draft.validation["parses"] is True
    assert salida["validation"]["parses"] is True
    assert session.commits == 1


async def test_editar_guarda_lo_que_habia_escrito_el_modelo(monkeypatch):
    session = _SesionConBorrador(_borrador(source="lo que generó el modelo"))
    _parser_responde(monkeypatch, {"valid": True, "issues": []})

    salida = await _editar(session, monkeypatch, "lo que corrigió la persona")

    assert session.draft.source_generado == "lo que generó el modelo"
    assert session.draft.source == "lo que corrigió la persona"
    assert salida["editado"] is True


async def test_la_segunda_edicion_no_pisa_el_original(monkeypatch):
    """Sin esto, corregir dos veces borraría al modelo del historial: la primera corrección
    humana pasaría a figurar como lo que escribió la máquina."""
    session = _SesionConBorrador(
        _borrador(source="primera corrección", source_generado="original del modelo"))
    _parser_responde(monkeypatch, {"valid": True, "issues": []})

    await _editar(session, monkeypatch, "segunda corrección")

    assert session.draft.source_generado == "original del modelo"


async def test_editar_deja_rastro_con_actor(monkeypatch):
    session = _SesionConBorrador(_borrador())
    _parser_responde(monkeypatch, {"valid": True, "issues": []})

    await _editar(session, monkeypatch, "otra cosa",
                  actor_id="yosdey", comment="type: wait no existe")

    ultimo = session.draft.comments[-1]
    assert ultimo == {"actor": "yosdey", "action": "edit",
                      "comment": "type: wait no existe"}


async def test_editar_un_borrador_ya_aprobado_es_conflicto(monkeypatch):
    """Un borrador aprobado ya se desplegó como versión inmutable. Editarlo haría que el
    registro y el borrador contaran historias distintas del mismo flow."""
    from fastapi import HTTPException

    session = _SesionConBorrador(_borrador(status="approved"))
    _parser_responde(monkeypatch, {"valid": True, "issues": []})

    with pytest.raises(HTTPException) as exc:
        await _editar(session, monkeypatch, "algo nuevo")

    assert exc.value.status_code == 409
    assert session.commits == 0


async def test_editar_con_la_misma_fuente_no_marca_el_borrador(monkeypatch):
    """Guardar una edición que no cambió nada dejaría en el historial una corrección falsa y
    marcaría como editado un borrador intacto."""
    session = _SesionConBorrador(_borrador(source="  process \"x\" {}  ".strip()))
    _parser_responde(monkeypatch, {"valid": True, "issues": []})

    salida = await _editar(session, monkeypatch, "  process \"x\" {}  ")

    assert session.draft.source_generado is None
    assert session.draft.comments == []
    assert salida["editado"] is False
    assert session.commits == 0


async def test_editar_con_fuente_vacia_es_422(monkeypatch):
    from fastapi import HTTPException

    session = _SesionConBorrador(_borrador())

    with pytest.raises(HTTPException) as exc:
        await _editar(session, monkeypatch, "   ")

    assert exc.value.status_code == 422
    assert session.commits == 0


async def test_editar_algo_que_no_compila_guarda_igual_y_lo_dice(monkeypatch):
    """La corrección se guarda aunque siga rota: arreglar un error suele destapar el
    siguiente, y perder lo avanzado en cada intento haría inusable el ciclo."""
    session = _SesionConBorrador(_borrador())
    _parser_responde(monkeypatch, {"valid": False, "issues": [
        {"level": "error", "message": "estado no declarado 'EN_LICENCIA'", "block": "entity"},
    ]})

    salida = await _editar(session, monkeypatch, "process \"y\" { }")

    assert session.draft.source == "process \"y\" { }"
    assert salida["validation"]["parses"] is False
    assert "EN_LICENCIA" in salida["validation"]["issues"][0]["message"]
