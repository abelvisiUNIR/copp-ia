---
project: copp-ia
date: 2026-07-25
status: accepted
provenance: copp-ia@devyos@5941771
tags: [adr, composer, llm, errores, fallas-silenciosas, calidad]
---

# ADR (wiki): el composer no miente — proveedor explícito, borrador validado, errores clasificados

> Provenance: `copp-ia@devyos@5941771`. Decisión tomada al abrir el work-stream
> `composer-llm-hardening`. **No** es un ADR del arquitecto (los suyos son ADR-001..005):
> es una decisión del equipo sobre el comportamiento del `composer-service`. Complementa
> [[2026-06-30-adr-003-llm-configurable]], que fijó la abstracción de proveedor y sigue vigente.

## Context
El roadmap listaba "composer: LLM real (hoy `stub`)" como pendiente, pero eso no describe el
código: `providers.py:47-119` ya implementa `AnthropicProvider`, `OpenAIProvider` y
`OllamaProvider` contra las APIs reales vía `httpx`. El `stub` es el cuarto caso, pensado para
probar el ciclo compose → review → deploy sin credenciales (`providers.py:122-126`).

Lo que falta no es integrar un proveedor, es que el servicio no engañe al usuario. Cuatro
huecos verificados:

1. **El fallback al stub es silencioso.** Con `LLM_PROVIDER=anthropic` y `llm_api_key` vacía,
   `get_provider` loguea un `warning` y devuelve `StubProvider()` (`providers.py:162-164`).
   `POST /compose` responde **201** y el analista recibe un esqueleto con `TODO:` creyendo que
   lo generó el modelo. Y el log **miente**: `main.py:74` registra
   `provider=settings.llm_provider`, o sea `"anthropic"`, cuando el que corrió fue el stub.
   La única traza que quedaría del incidente afirma lo contrario de lo que pasó.
2. **El borrador nunca se parsea.** `main.py:63-70` limpia fences de markdown y persiste el
   texto crudo. Un output que no compila queda `pending` y recién falla en `approve`
   (`main.py:120`), después de que un humano lo revisó línea por línea. El `parser-service`
   ya existe y `Settings.parser_url` ya está (`config.py:29`).
3. **Los errores del proveedor no se clasifican.** `raise_for_status()` → `except Exception`
   → 502 (`main.py:57-61`). Un `429` (rate limit, transitorio, con `retry-after`) se trata
   igual que un `400` de prompt inválido: ninguno se reintenta. El clasificador
   transitorio/permanente ya existe para los adapters del executor
   ([[2026-07-14-clasificacion-errores-integracion]]) y no se está usando acá.
4. **Sin techo de tokens ni tests.** `max_tokens` solo va en Anthropic (`providers.py:63`);
   OpenAI y Ollama no lo mandan. Cero tests del composer.

El punto 1 es el mismo patrón que ya nos mordió tres veces ([[fallas-silenciosas]]): un
`except`/`warning` que no corta, un dashboard que no llega, un `mypy` que no chequea nada. Es
la cuarta aparición, y la primera en la que el destinatario del engaño es un usuario final y
no un desarrollador.

## Decision

**1. El proveedor es explícito o el servicio no arranca.**
`get_provider` deja de tener fallback: si `LLM_PROVIDER` nombra un proveedor que requiere
credencial y no hay `llm_api_key`, levanta. La validación corre en el `lifespan`
(`main.py:31-36`), así que el contenedor **falla al arrancar** en vez de servir 201 mentirosos.
El `StubProvider` se usa **solo** con `LLM_PROVIDER=stub` — sigue siendo el default de
`Settings` (`config.py:36`), así que el ciclo sin credenciales no se rompe: lo que se rompe es
pedir un proveedor real y recibir el stub.

**2. La respuesta y el log dicen qué proveedor corrió de verdad.**
No `settings.llm_provider` (lo pedido) sino el nombre del proveedor instanciado (lo ejecutado).
Se expone también en el draft, para que la review-ui pueda mostrar "esto lo escribió el stub".

**3. El borrador se valida contra el parser antes de guardarse, pero se guarda igual.**
`POST /compose` llama al `parser-service` con el `source` generado. El resultado se persiste en
una columna nueva `validation` (JSON: `{parses: bool, issues: [...]}`, migración Alembic
`0003`) y viaja en la respuesta. Un borrador que no compila **se guarda igual, marcado**: la
generación se pagó y el texto sirve para editar a mano. Lo que no puede pasar es que llegue a
un revisor humano sin que nadie sepa que no compila.

**4. Los errores del proveedor se clasifican con el criterio que ya existe.**
Transitorio (5xx, 408, 429, timeouts/red de httpx) → reintento con backoff y full jitter,
mismo esquema que `_run_step`. Permanente (4xx salvo 408/429, credencial inválida, prompt
rechazado) → falla al primer intento. El 502 se reserva para lo transitorio agotado; lo
permanente por configuración nuestra sale como 500 y lo permanente por pedido del analista
como 422.

**5. `max_tokens` en los tres proveedores**, con el valor en `Settings` (`llm_max_tokens`) en
vez de hardcodeado.

## Rationale
- **Un warning no es protección.** Ya lo aprendimos en [[limpieza-dx-openapi]] con el
  `UserWarning` de FastAPI que publicaba un contrato roto igual. Acá es peor: el warning va al
  log del servicio y el engaño va al analista, que no lee ese log. La única señal que llega a
  quien tiene que enterarse es el 201.
- **Fallar al arrancar y no al componer.** Un `.env` mal configurado es un error de despliegue,
  y los errores de despliegue tienen que aparecer en el despliegue. Fallar por request
  significa descubrirlo cuando alguien pidió un flow, con el pedido perdido.
- **Validar al componer cuesta un request y ahorra una revisión humana.** El parser ya sabe
  responder eso; el orden actual (generar → humano revisa → deploy falla) pone el chequeo más
  barato después del más caro.
- **Guardar el borrador inválido en vez de rechazarlo.** Un 422 sin persistir tira el output
  de un LLM que ya se pagó y que suele estar a dos líneas de compilar. Marcarlo cumple el
  objetivo (que nadie lo revise creyendo que está bien) sin perder el trabajo.
- **Reusar el clasificador y no escribir otro.** El criterio transitorio/permanente ya está
  decidido y verificado en vivo para los adapters; un segundo criterio para el composer sería
  la misma decisión tomada dos veces, con dos lugares donde puede divergir.

## Consequences
- **Un `.env` con `LLM_PROVIDER=anthropic` sin key deja de levantar el `composer-service`.**
  Es un cambio de comportamiento visible en `docker compose up` para cualquiera que tuviera esa
  combinación: antes arrancaba y componía basura. La salida hay que hacerla explícita en el
  mensaje de error (qué variable falta) y en el `.env.example`.
- **`.env.example` hoy trae `LLM_PROVIDER=anthropic`** (`.env.example:22`) sin key: con esta
  decisión, un clon nuevo del repo no levantaría el composer. Hay que cambiarlo a `stub`, que
  es el default de `Settings` y el único valor que funciona sin credenciales.
- **Migración Alembic `0003`** — segunda desde el schema inicial. Nada más la usa; una columna
  JSON nullable no toca datos existentes.
- **El composer pasa a depender del `parser-service` en tiempo de compose.** Si el parser está
  caído, la decisión es guardar el borrador con `validation: {parses: null}` y no bloquear la
  generación — la degradación tiene que ser visible, no silenciosa (si no, repetimos el
  problema que este ADR arregla, un nivel más abajo).
- **Los tests del composer mockean el proveedor**, no llaman a ninguna API real: ni en local ni
  en CI se gasta un token.

## Alternatives
- **Dejar el fallback y subir el `warning` a `error`** — descartada: cambia el nivel del log,
  no el 201. El analista sigue recibiendo el esqueleto sin enterarse.
- **Fallback al stub pero devolviendo 503** — descartada a medias: es honesto, pero elige el
  peor momento para enterarse (cuando alguien ya escribió el pedido) y deja el servicio
  arriba en un estado en el que nada de lo que hace sirve.
- **Rechazar con 422 el borrador que no compila** — descartada: tira output ya pagado y empuja
  al analista a reintentar el mismo prompt en vez de editar dos líneas.
- **Agregar el `validation` a `comments` (JSON ya existente) para evitar la migración** —
  descartada: `comments` es la traza de la revisión humana (`main.py:128-131`); meterle un
  registro de máquina mezcla dos cosas que la UI muestra distinto.
- **Validar el borrador importando el parser como librería en vez de llamar al servicio** —
  descartada: contradice la convención del repo (los cambios del DSL pasan por
  `parser-service`) y duplicaría la versión de la gramática efectiva en dos procesos.

## Sources
`teleflow/composer_service/providers.py:47-164` · `teleflow/composer_service/main.py:48-75,120`
· `teleflow/common/config.py:29,36-39` · `teleflow/common/models.py:154-171` ·
`.env.example:21-22` · [[2026-06-30-adr-003-llm-configurable]] ·
[[2026-07-14-clasificacion-errores-integracion]] · [[fallas-silenciosas]] ·
work-stream `composer-llm-hardening` · [[roadmap]]
