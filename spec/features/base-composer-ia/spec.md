---
project: copp-ia
type: spec
status: implementada
feature: base-composer-ia
provenance: copp-ia@devyos@ffd585d
created: 2026-09-14
---

<!-- Linea base as-built: documenta lo que el codigo hace hoy. Nunca se sincroniza con Jira. -->
<!-- Lo escribe el subagente `analista-requisitos` (modo as-built). Ante conflicto, manda el codigo. -->


# Linea base — composer IA (borradores `.tflow` desde lenguaje natural, revision y aprobacion)

## Que resuelve

Un analista describe un proceso en lenguaje natural y necesita obtener un `.tflow` que una
persona pueda revisar, corregir y desplegar sin salir de la plataforma. El organismo, por su
parte, necesita elegir el proveedor LLM por configuracion (API comercial, modelo self-hosted o
ninguno) y saber siempre que proveedor genero cada borrador y si el borrador compila.

Lo resuelve hoy asi (comprobado leyendo el codigo en `copp-ia@devyos@ffd585d`):

- **Generacion de borradores**: `POST /compose` arma el prompt con la descripcion y, si viene,
  la version actual del flow, llama al proveedor, limpia fences de markdown y persiste un
  `FlowDraft` (`teleflow/composer_service/main.py:60-105`).
- **Proveedor configurable** detras de un ABC con un unico metodo `generate(prompt) -> str`
  (`teleflow/composer_service/providers.py:171-177`), con cuatro implementaciones
  `anthropic | openai | ollama | stub` (`providers.py:269-408`) elegidas por `LLM_PROVIDER`
  (`teleflow/common/config.py:36-39`, ADR-003).
- **Arranque que falla en vez de mentir**: el proveedor se construye en el `lifespan`
  (`teleflow/composer_service/main.py:37-47`) y `get_provider` levanta `LLMConfigurationError` ante un proveedor
  desconocido o sin credencial, sin caer nunca al `stub` en silencio (`providers.py:418-447`).
- **Errores del LLM clasificados** en tres familias con tres codigos HTTP distintos
  (`providers.py:151-168`, `teleflow/composer_service/main.py:71-83`) y reintentos solo de lo transitorio con backoff y
  full jitter (`providers.py:191-254`, `teleflow/common/retry.py:26-48`).
- **Validacion del borrador contra el parser-service** antes de guardarlo, sin condicionar el
  guardado, con tres estados: compila, no compila, no se pudo verificar (`teleflow/composer_service/main.py:108-135`).
- **Ciclo de vida PR-style**: `pending` → `approved` | `rejected`, con historial de acciones en
  `comments` (`teleflow/composer_service/main.py:163-217`). Aprobar despliega via el gateway (`teleflow/composer_service/main.py:172-179`).
- **Correccion humana en la revision**: `PATCH /drafts/{id}/source` reemplaza la fuente, la
  revalida en el servidor y conserva lo que escribio el modelo en `source_generado`
  (`teleflow/composer_service/main.py:226-276`).
- **Exposicion por el gateway** con scopes `compose:read`, `compose:write` y `flows:deploy`
  (`teleflow/gateway/main.py:773-816`).

## Objetivo

Que todo pedido en lenguaje natural termine en un borrador persistido que declara que proveedor
lo genero y si compila, o en un error HTTP que distingue pedido rechazado, instalacion mal
configurada y proveedor no disponible; y que ningun borrador llegue al registro sin pasar por una
aprobacion explicita sobre la fuente guardada.

## Alcance

**Entra:**

- `teleflow/composer_service/main.py` — `lifespan`, `POST /compose`, `_validate_source`,
  `GET /drafts`, `GET /drafts/{id}`, `POST /drafts/{id}/approve`, `POST /drafts/{id}/reject`,
  `PATCH /drafts/{id}/source`, `_draft_out`.
- `teleflow/composer_service/providers.py` — `DSL_SYSTEM_PROMPT`, las tres excepciones,
  `LLMProvider`, `_post_json`, `_texto_o_error`, los cuatro proveedores y `get_provider`.
- Configuracion de la capa IA en `teleflow/common/config.py:35-58` (`llm_*`, `compose_timeout`)
  y las URLs internas que usa el composer (`config.py:29`, `config.py:33`).
- Proxy del gateway hacia el composer: `teleflow/gateway/main.py:773-816`, con `_proxy`
  (`teleflow/gateway/main.py:409-433`).
- Tabla `flow_drafts`: `alembic/versions/0001_initial.py:114-126`,
  `alembic/versions/0003_draft_validation.py:17-27` (`provider`, `validation`),
  `alembic/versions/0007_fuente_generada_del_borrador.py:16-27` (`source_generado`); ORM en
  `teleflow/common/models.py:174-207`.

**No entra (y por que):**

- **Test unitario o e2e Python de aprobar y rechazar.** `tests/test_composer.py` no llama a
  `approve_draft` ni a `reject_draft` (el archivo cubre proveedores, `_validate_source`, `compose`
  y `edit_draft_source`), y una busqueda de `composer|borrador|drafts` en `tests/e2e/` no da
  coincidencias. Lo unico que ejercita esos endpoints son dos tests de Playwright
  (`review-ui/tests/revision.spec.js:71-101`) que requieren el stack. Quedan `(sin test)` en
  Python: el 409 sobre un borrador no `pending`, el 422 cuando el deploy falla y el contenido del
  comentario de aprobacion y rechazo. Motivo: no se escribio; queda como hueco.
- **Identidad real de quien aprueba, rechaza o corrige.** `actor_id` es texto libre del body con
  default `""` (`teleflow/composer_service/main.py:159`, `teleflow/composer_service/main.py:199`, `teleflow/composer_service/main.py:222`) y se copia tal cual a `comments`
  (`teleflow/composer_service/main.py:188-191`, `teleflow/composer_service/main.py:212-214`, `teleflow/composer_service/main.py:270-272`). El gateway conoce la identidad de la
  key (`teleflow/gateway/main.py:227`) pero `_proxy` arma los headers desde cero y no la reenvia
  (`teleflow/gateway/main.py:412-418`). La UI manda `'dev'` fijo al rechazar (`review-ui/src/App.jsx:177`)
  y el CLI `cli` por default al aprobar (`teleflow/cli.py:220`). Ademas, el deploy que dispara la
  aprobacion viaja con la key de bootstrap del servicio (`teleflow/composer_service/main.py:176`, `config.py:18`), asi que en
  `audit_log` la fila de `POST /flows/{name}` queda a nombre de `bootstrap (env)`
  (`teleflow/gateway/main.py:352-354`, `teleflow/gateway/auth.py:53`); la unica fila con la key del revisor
  es la de `POST /drafts/{id}/approve` (`teleflow/gateway/main.py:204-207`). Motivo: no se decidio como
  propagar la identidad entre servicios.
- **Scope de la aprobacion.** Corregir la fuente exige `flows:deploy`
  (`teleflow/gateway/main.py:803-804`) con el argumento de que "aprobar despliega `draft.source`"
  (`teleflow/gateway/main.py:808-811`), pero aprobar, que es lo que despliega, pasa por la ruta
  `POST /drafts/{rest:path}` con `compose:write` (`teleflow/gateway/main.py:795-798`,
  `auth.py:38` "generar/aprobar borradores"). Una key con `compose:write` y sin `flows:deploy`
  despliega a traves del composer, que usa la key de bootstrap con scopes `*` por default
  (`config.py:23`). Consecuencia inversa `(inferencia)`: si el operador restringe
  `TELEFLOW_API_KEY_SCOPES` sin `flows:deploy`, toda aprobacion termina en 422 (el gateway da 403
  y `teleflow/composer_service/main.py:180-185` lo convierte). Sin test. El analisis de seguridad va en `seguridad.md`.
- **Limites de tamaño.** `ComposeRequest.description` y `base_source` son `str` sin `max_length`
  (`teleflow/composer_service/main.py:54-57`), igual que `EditRequest.source` (`teleflow/composer_service/main.py:220-223`); las columnas son `Text`
  (`models.py:181-183`). El unico freno por delante es el rate limit del gateway por key
  (`config.py:93`). Que un pedido enorme se traduzca en costo de tokens o en un 4xx del proveedor
  mapeado a 422 es `(inferencia)`. Motivo: no se decidio un limite.
- **Validacion del `name` del borrador.** `ComposeRequest.name` es `str` libre (`teleflow/composer_service/main.py:55`), la
  columna es `String(200)` (`models.py:180`) y se interpola sin escapar en la URL del deploy
  (`teleflow/composer_service/main.py:175`). Que un nombre con `/`, `?` o `..` apunte a otra ruta del gateway con la key de
  bootstrap es `(inferencia)`, no verificado. Sin test.
- **Mitigacion de prompt injection.** La descripcion va literal como mensaje de usuario
  (`teleflow/composer_service/main.py:65`, `providers.py:286`, `providers.py:322`, `providers.py:357`) y `base_source` se
  concatena al prompt tal como llega en el body (`teleflow/composer_service/main.py:66-68`): el servidor no comprueba que
  coincida con la version registrada. La unica defensa es texto del system prompt
  (`providers.py:145-146`). La salida solo se valida contra el parser, que no juzga intencion: el
  ADR de correccion registra un borrador que compilo y hacia lo inverso de lo pedido
  (`wiki/Knowledge/decisions/2026-08-27-correccion-del-borrador-en-la-revision.md:31-34`).
  Combinado con `${env.*}` en integraciones (`wiki/Knowledge/backlog-hardening.md:147-165`) y con
  la aprobacion por `compose:write`, un borrador inducido puede terminar desplegado
  `(inferencia)`. Motivo: no hay decision tomada.
- **Tool-use y conversacion.** `LLMProvider.generate(prompt) -> str` es de un solo turno, sin
  historial, sin herramientas y con system prompt fijo (`providers.py:171-177`,
  `providers.py:20-148`); el unico consumidor es `compose` (`teleflow/composer_service/main.py:72`). La direccion de producto
  vigente es un asistente conversacional con `@capacidades` (`AGENTS.md:15-17`), cuya carpeta
  `spec/features/asistente-conversacional/` no existe en este commit (busqueda en
  `spec/features/`). Motivo: la interfaz se diseño para generar un archivo, no para conversar.
- **Reproducibilidad de la generacion.** Ningun payload fija `temperature`
  (`providers.py:282-287`, `providers.py:317-324`, `providers.py:351-359`); el ADR de correccion
  observo flows distintos para la misma descripcion (`2026-08-27-correccion-del-borrador-en-la-revision.md:38-39`).
- **Concurrencia sobre un mismo borrador.** `approve`, `reject` y `edit` leen con
  `session.get` sin bloqueo (`teleflow/composer_service/main.py:166`, `teleflow/composer_service/main.py:206`, `teleflow/composer_service/main.py:250`) y confirman al final.
  `(inferencia)`: dos aprobaciones simultaneas con versiones distintas registran dos versiones
  desde un borrador; una edicion que confirma entre el deploy (`teleflow/composer_service/main.py:173-179`) y el commit de la
  aprobacion (`teleflow/composer_service/main.py:192`) deja un borrador `approved` cuya `source` no es la desplegada, justo lo
  que el docstring de la edicion dice evitar (`teleflow/composer_service/main.py:247-248`). El chart corre replicas
  (`AGENTS.md:112`). Sin test.
- **Fallos de transporte en la aprobacion.** El `POST` al gateway no esta dentro de un `try`
  (`teleflow/composer_service/main.py:173-179`) y `response.json()` se llama sobre el cuerpo de error sin proteger
  (`teleflow/composer_service/main.py:184`): gateway caido o cuerpo no JSON salen como excepcion no manejada. Tambien un
  `200` no JSON del proveedor levanta dentro de `_post_json` sin clasificar (`providers.py:226`).
  Si el deploy responde 201 y el `commit` falla, el flow queda registrado y el borrador `pending`
  `(inferencia)`. Sin test.
- **Fecha en el historial.** Las entradas de `comments` no llevan timestamp
  (`teleflow/composer_service/main.py:188-191`, `teleflow/composer_service/main.py:212-214`, `teleflow/composer_service/main.py:270-272`); la tabla tiene `updated_at`
  (`models.py:205-207`) pero `_draft_out` no lo expone (`teleflow/composer_service/main.py:279-301`).
- **Paginacion, borrado y reapertura de borradores.** El listado corta en 100 sin cursor
  (`teleflow/composer_service/main.py:144`), `status` se filtra con cualquier string (`teleflow/composer_service/main.py:142-143`), no hay ruta para
  borrar ni para volver un borrador a `pending` (`teleflow/composer_service/main.py:60-276`).
- **Metricas propias del composer.** Ni `main.py` ni `providers.py` definen contadores (busqueda
  de `prometheus|Counter|Histogram` en `teleflow/composer_service/`): solo existen las metricas HTTP
  genericas (`teleflow/common/observability.py:33-44`). `/ready` verifica la base, no el proveedor
  ni el parser (`teleflow/composer_service/main.py:51`, `observability.py:50-60`). Los reintentos y los rechazos del LLM solo
  quedan en logs (`providers.py:250-251`, `teleflow/composer_service/main.py:74-82`).
- **CLI completo.** `tflow` expone `compose`, `drafts` y `approve` (`cli.py:209-221`); no hay
  `reject` ni edicion, y `compose` no envia `base_source` (`cli.py:121-123`).
- **La pantalla de revision.** `review-ui/` es otro modulo; aca solo se usa como evidencia
  `(indirecto)` de que aprobar despliega y rechazar no.

## Criterios de aceptacion

Cada criterio nombra el test que lo comprueba. `(sin test)` = el codigo lo hace y ningun test lo
prueba. `(indirecto)` = lo prueba un test de otro modulo; los de `review-ui/tests/revision.spec.js`
son Playwright y requieren el stack levantado.

### Arranque y seleccion de proveedor

- [ ] Dado `LLM_PROVIDER` en `anthropic` u `openai` con `LLM_API_KEY` vacia, cuando se llama a
  `get_provider`, entonces levanta `LLMConfigurationError` y el mensaje contiene `LLM_API_KEY` y
  `stub` — `tests/test_composer.py::test_proveedor_real_sin_credencial_levanta`
- [ ] Dado `LLM_PROVIDER=anthropic` y `LLM_API_KEY` vacia, cuando arranca la app del composer,
  entonces el `lifespan` levanta `LLMConfigurationError` y el servicio no queda sirviendo —
  `tests/test_composer.py::test_el_servicio_no_arranca_sin_credencial`
- [ ] Dado `LLM_PROVIDER` en `anthropic`, `openai` u `ollama` con key `k`, cuando se llama a
  `get_provider`, entonces nunca devuelve `StubProvider` y `name` es el proveedor pedido —
  `tests/test_composer.py::test_ningun_proveedor_real_devuelve_el_stub`
- [ ] Dado cada valor de `LLM_PROVIDER`, cuando se llama a `get_provider`, entonces construye:
  - `stub` → `StubProvider` con `name == "stub"` — `tests/test_composer.py::test_stub_solo_cuando_se_lo_pide`
  - `anthropic` con key → `AnthropicProvider` — `tests/test_composer.py::test_anthropic_con_credencial`
  - `openai` con key → `OpenAIProvider` — `tests/test_composer.py::test_openai_con_credencial`
  - `ollama` sin key → `OllamaProvider` — `tests/test_composer.py::test_ollama_no_necesita_credencial`
- [ ] Dado `LLM_PROVIDER` igual a `"  Anthropic "`, `"STUB"` u `"OpenAI"`, cuando se llama a
  `get_provider`, entonces `name` es el valor sin espacios y en minusculas —
  `tests/test_composer.py::test_el_valor_se_normaliza`
- [ ] Dado `LLM_PROVIDER` igual a `antropic`, `gpt`, `claude` o vacio, cuando se llama a
  `get_provider`, entonces levanta `LLMConfigurationError` con `no es un proveedor conocido` —
  `tests/test_composer.py::test_proveedor_desconocido_levanta`
- [ ] Dado `.env.example`, cuando `LLM_API_KEY` esta vacia, entonces `LLM_PROVIDER` es `stub` o
  vacio — `tests/test_composer.py::test_env_example_arranca_sin_credenciales`
- [ ] Dado un proveedor sin `LLM_MODEL` ni `LLM_BASE_URL`, cuando se construye, entonces usa
  `claude-fable-5` en `https://api.anthropic.com`, `gpt-4o` en `https://api.openai.com` o
  `llama3.1` en `http://ollama:11434` (`providers.py:275-276`, `providers.py:310-311`,
  `providers.py:344-345`) — `(sin test)`
- [ ] Dada una instalacion sin `LLM_PROVIDER` configurado, cuando arranca el composer, entonces
  usa `stub` (`config.py:36`) — `(sin test)`

### Llamada al proveedor: clasificacion y reintentos

- [ ] Dada una respuesta del proveedor, cuando se genera con `llm_retry_attempts=3`, entonces se
  clasifica asi:
  - `503` y despues `200` → devuelve el texto con 2 llamadas —
    `tests/test_composer.py::test_un_503_se_reintenta_y_puede_salir_bien`
  - `429` con `retry-after` y despues `200` → devuelve el texto con 2 llamadas —
    `tests/test_composer.py::test_un_429_se_reintenta`
  - `503` persistente → `LLMTransientError` despues de 3 llamadas —
    `tests/test_composer.py::test_transitorio_persistente_agota_intentos`
  - `400` → `LLMRequestRejected` con 1 llamada — `tests/test_composer.py::test_un_400_falla_al_primer_intento`
  - `401`, `403` o `404` → `LLMConfigurationError` —
    `tests/test_composer.py::test_credencial_o_modelo_mal_es_config_nuestra`
  - `408` → se reintenta (`teleflow/common/retry.py:12`, `providers.py:240-243`) — `(sin test)`
    en el composer; el mismo criterio esta probado para los adapters en
    `tests/test_adapters.py::test_rest_status_transitorio_es_retryable` `(indirecto)`
  - error de red (conexion rechazada, DNS, TLS, timeout de conexion) → se reintenta
    (`providers.py:222-223`) — `(sin test)`
  - `200` cuyo JSON no es un objeto → `LLMRequestRejected` (`providers.py:227-229`) — `(sin test)`
- [ ] Dado un timeout de lectura contra el proveedor con `timeout=600`, cuando se llama a
  `_post_json`, entonces levanta `LLMTransientError` en el primer intento sin reintentar, y el
  mensaje contiene `600` y `self-hosted` —
  `tests/test_composer.py::test_un_timeout_de_lectura_falla_en_el_primer_intento`
- [ ] Dado un fallo transitorio con `retry-after`, cuando se espera antes del siguiente intento,
  entonces la espera es ese valor topeado a `llm_retry_max_delay`; sin `retry-after`, es full
  jitter sobre `llm_retry_base_delay * 2^intento` con el mismo tope (`providers.py:243-249`,
  `retry.py:41-48`) — `(sin test)`: el test del 429 usa `retry-after: 0` y tope 0, asi que no
  distingue una espera de otra
- [ ] Dado `llm_retry_attempts` menor que 1, cuando se llama al proveedor, entonces se hace
  exactamente 1 intento (`providers.py:200`) — `(sin test)`

### Respuestas 200 que no sirven como borrador

- [ ] Dada una respuesta de Anthropic con `stop_reason: refusal` y `content` vacio, cuando se
  genera, entonces levanta `LLMRequestRejected` con `declinó` y `Reformulá` en el mensaje —
  `tests/test_composer.py::test_refusal_no_revienta_con_indexerror`
- [ ] Dada una respuesta truncada, cuando se genera, entonces levanta `LLMConfigurationError`:
  - Anthropic con `stop_reason: max_tokens`, mensaje con `LLM_MAX_TOKENS` —
    `tests/test_composer.py::test_respuesta_truncada_no_se_guarda_como_borrador`
  - OpenAI con `finish_reason: length` — `tests/test_composer.py::test_openai_truncado_tambien_se_detecta`
  - Ollama con `done_reason: length` (`providers.py:369-372`) — `(sin test)`
- [ ] Dada una respuesta sin texto o solo con espacios, cuando se genera, entonces levanta
  `LLMRequestRejected` con `el modelo no devolvió texto` (`providers.py:263-265`) — `(sin test)`
- [ ] Dada una respuesta de OpenAI sin `choices`, cuando se genera, entonces levanta
  `LLMRequestRejected` (`providers.py:328-330`) — `(sin test)`
- [ ] Dada `llm_max_tokens=1234`, cuando se genera con OpenAI, entonces el payload lleva
  `max_tokens == 1234` — `tests/test_composer.py::test_max_tokens_viaja_en_el_payload`; en Anthropic
  viaja como `max_tokens` (`providers.py:284`) y en Ollama como `options.num_predict`
  (`providers.py:354`) — `(sin test)` para esos dos

### `POST /compose`

- [ ] Dado `LLM_PROVIDER=stub` y un parser que responde `valid: false` con un issue, cuando se
  compone `alta_socio`, entonces se persiste un borrador con `provider == "stub"` y
  `validation.parses == false`, y la respuesta trae `provider: "stub"` y el mensaje del issue —
  `tests/test_composer.py::test_compose_guarda_el_borrador_marcado`
- [ ] Dado un pedido que el proveedor resuelve, cuando se hace `POST /compose`, entonces responde
  `201` con `status: "pending"`, `editado: false` y `source_generado: null` (`teleflow/composer_service/main.py:60`,
  `models.py:193`, `teleflow/composer_service/main.py:294`, `teleflow/composer_service/main.py:300`) — `(sin test)` por HTTP; el camino por la API esta
  ejercitado `(indirecto)` en `review-ui/tests/revision.spec.js`, que exige `201` al crear cada
  borrador (`revision.spec.js:14-21`)
- [ ] Dado un fallo del proveedor, cuando se hace `POST /compose`, entonces no se persiste nada y
  responde (`teleflow/composer_service/main.py:71-83`) — `(sin test)` en los tres casos; se prueba la excepcion, no el codigo HTTP:
  - `LLMRequestRejected` → `422` con `El proveedor rechazó el pedido`
  - `LLMConfigurationError` → `500` con `Composer mal configurado`
  - `LLMTransientError` → `502` con `Proveedor LLM no disponible`
- [ ] Dado un `base_source`, cuando se compone, entonces el prompt es la descripcion seguida de
  `Versión actual del flow (modificala según el pedido):` y la fuente (`teleflow/composer_service/main.py:65-68`) —
  `(sin test)`
- [ ] Dado un texto generado que empieza con tres backticks, cuando se compone, entonces se
  eliminan todas las lineas que empiezan con tres backticks (`teleflow/composer_service/main.py:86-89`) — `(sin test)`
- [ ] Dado `LLM_PROVIDER=stub`, cuando se compone, entonces el borrador es un esqueleto con el
  pedido comentado linea por linea con `// `, `process "proceso_borrador"` y `step "paso_inicial"`
  (`providers.py:385-408`), compila y la pantalla lo muestra como generado por el stub —
  `(indirecto)` `review-ui/tests/revision.spec.js` "el borrador muestra su estado de validación y
  quién lo generó"

### Validacion del borrador contra el parser

- [ ] Dado un parser que responde `valid: true`, cuando se valida, entonces `parses` es `true`,
  `issues` es `[]` y `checked_at` no es vacio —
  `tests/test_composer.py::test_borrador_que_compila_queda_marcado_ok`
- [ ] Dado un parser que responde `valid: false` con issues, cuando se valida, entonces no
  levanta, `parses` es `false` e `issues` son los del parser —
  `tests/test_composer.py::test_borrador_que_no_compila_se_marca_pero_no_levanta`
- [ ] Dado un parser inalcanzable (`httpx.ConnectError`), cuando se valida, entonces `parses` es
  `None` (ni `true` ni `false`) y la validacion trae `error` —
  `tests/test_composer.py::test_parser_caido_no_se_confunde_con_compila`
- [ ] Dado un error que no es de transporte ni de lectura de la respuesta (`RuntimeError`), cuando
  se valida, entonces la excepcion se propaga —
  `tests/test_composer.py::test_un_bug_nuestro_no_se_disfraza_de_parser_caido`
- [ ] Dado un parser que responde un status 4xx/5xx o un cuerpo que no es JSON, cuando se valida,
  entonces `parses` es `None` (`teleflow/composer_service/main.py:123-129`) — `(sin test)`

### Consulta de borradores

- [ ] Dados borradores guardados, cuando se hace `GET /drafts`, entonces devuelve como maximo 100
  ordenados por `created_at` descendente, filtrables por `?status=`, con `provider`, `validation` y
  `editado` y sin `source`, `base_source` ni `source_generado` (`teleflow/composer_service/main.py:138-145`,
  `teleflow/composer_service/main.py:279-301`) — `(sin test)`; que `editado` aparece en el listado despues de corregir esta
  `(indirecto)` en `review-ui/tests/revision.spec.js` "un borrador corregido queda marcado en la lista"
- [ ] Dado un id que no existe, cuando se hace `GET /drafts/{id}`, entonces responde `404` con
  `Borrador no encontrado`; con un id que no es UUID, `422` (`teleflow/composer_service/main.py:148-154`) — `(sin test)`

### Aprobacion

- [ ] Dado un borrador recien compuesto, cuando se aprueba desde la pantalla con version `1.0.0`,
  entonces el flow aparece en `GET /api/flows` — `(indirecto)`
  `review-ui/tests/revision.spec.js` "aprobar despliega ese borrador"
- [ ] Dado un borrador `pending` y un deploy que responde `< 400`, cuando se hace
  `POST /drafts/{id}/approve` con `version`, `actor_id` y `comment`, entonces se hace
  `POST {gateway_url}/flows/{name}` con `X-TeleFlow-API-Key` igual a `TELEFLOW_API_KEY` y body
  `source` = `draft.source`, `version` y `description: "Aprobado desde draft <id>"`; el borrador
  queda `approved`, se agrega a `comments` `{actor, action: "approve", comment, version}` y la
  respuesta incluye `deploy` con el cuerpo del gateway (`teleflow/composer_service/main.py:172-195`) — `(sin test)`
- [ ] Dado un borrador `pending` y un deploy que responde `>= 400`, cuando se aprueba, entonces
  responde `422` con `message: "El deploy falló — el borrador sigue pending"` y `upstream` con el
  cuerpo del gateway, y el borrador sigue `pending` sin entrada nueva en `comments`
  (`teleflow/composer_service/main.py:180-185`) — `(sin test)`
- [ ] Dado un borrador `approved` o `rejected`, cuando se aprueba, entonces responde `409` con
  `Borrador ya <estado>` y no se llama al gateway; con un id inexistente, `404`
  (`teleflow/composer_service/main.py:166-170`) — `(sin test)`
- [ ] Dado un borrador con cambios en el editor sin guardar, cuando se pulsa aprobar y se cancela
  el aviso de `sin guardar`, entonces el flow no aparece en `GET /api/flows` — `(indirecto)`
  `review-ui/tests/revision.spec.js` "aprobar con cambios sin guardar avisa que se despliega lo
  guardado"; del lado del servidor, lo desplegado es siempre `draft.source` (`teleflow/composer_service/main.py:177`)

### Rechazo

- [ ] Dado un borrador recien compuesto, cuando se rechaza desde la pantalla con un comentario,
  entonces el flow no aparece en `GET /api/flows` — `(indirecto)`
  `review-ui/tests/revision.spec.js` "rechazar no despliega nada"
- [ ] Dado un borrador `pending`, cuando se hace `POST /drafts/{id}/reject`, entonces queda
  `rejected` y se agrega a `comments` `{actor, action: "reject", comment}`; sobre uno que no es
  `pending` responde `409` y sobre uno inexistente `404` (`teleflow/composer_service/main.py:203-217`) — `(sin test)`

### Correccion de la fuente

- [ ] Dado un borrador `pending` y un parser que responde `valid: true`, cuando se edita con una
  fuente distinta, entonces `source` queda con la fuente nueva, `validation.parses` es `true` en el
  borrador y en la respuesta, y hay exactamente 1 commit —
  `tests/test_composer.py::test_editar_revalida_contra_el_parser`
- [ ] Dado un borrador nunca editado, cuando se edita, entonces `source_generado` guarda la fuente
  anterior y la respuesta trae `editado: true` —
  `tests/test_composer.py::test_editar_guarda_lo_que_habia_escrito_el_modelo`
- [ ] Dado un borrador con `source_generado` ya guardado, cuando se edita otra vez, entonces
  `source_generado` no cambia — `tests/test_composer.py::test_la_segunda_edicion_no_pisa_el_original`
- [ ] Dada una edicion con `actor_id: "yosdey"` y un comentario, cuando se guarda, entonces la
  ultima entrada de `comments` es exactamente `{actor: "yosdey", action: "edit", comment: <el comentario>}`
  — `tests/test_composer.py::test_editar_deja_rastro_con_actor`
- [ ] Dado un borrador `approved`, cuando se edita, entonces responde `409` y no hay commit —
  `tests/test_composer.py::test_editar_un_borrador_ya_aprobado_es_conflicto`; con `rejected` pasa
  por la misma rama (`teleflow/composer_service/main.py:253-254`) — `(sin test)`
- [ ] Dada una fuente que, sin espacios de los bordes, es igual a la guardada, cuando se edita,
  entonces no hay commit, `comments` no cambia, `source_generado` sigue `null` y `editado` es
  `false` — `tests/test_composer.py::test_editar_con_la_misma_fuente_no_marca_el_borrador`
- [ ] Dada una fuente vacia o solo con espacios, cuando se edita, entonces responde `422` y no hay
  commit — `tests/test_composer.py::test_editar_con_fuente_vacia_es_422`
- [ ] Dada una fuente que no compila, cuando se edita, entonces se guarda igual, la respuesta trae
  `validation.parses == false` y los issues del parser —
  `tests/test_composer.py::test_editar_algo_que_no_compila_guarda_igual_y_lo_dice`
- [ ] Dado un borrador que compila, cuando se lo rompe desde el editor y se guarda, entonces el
  badge pasa a `no compila`, y al restaurar la fuente y guardar vuelve a `compila` — `(indirecto)`
  `review-ui/tests/revision.spec.js` "guardar revalida contra el parser, en los dos sentidos"
- [ ] Dado un id inexistente, cuando se edita, entonces responde `404` (`teleflow/composer_service/main.py:250-252`); con el
  parser caido, la edicion se guarda con `validation.parses == None` (`teleflow/composer_service/main.py:269`,
  `teleflow/composer_service/main.py:125-129`) — `(sin test)`

### Exposicion por el gateway

- [ ] Dada una key, cuando llama a las rutas del composer por el gateway, entonces el scope
  exigido es (`teleflow/gateway/main.py:775-816`) — `(sin test)` por ruta; con scopes `*`, `GET /drafts` no
  da `403` — `tests/test_gateway_scopes.py::test_sin_config_la_key_global_conserva_todos_los_permisos`:
  - `POST /compose` → `compose:write`
  - `GET /drafts` y `GET /drafts/{...}` → `compose:read`
  - `POST /drafts/{...}` (incluye `approve` y `reject`) → `compose:write`
  - `PATCH /drafts/{id}/source` → `flows:deploy`
- [ ] Dada una accion con `compose:write` o `flows:deploy`, cuando termina, entonces queda en
  `audit_log` porque ambos scopes son de escritura (`auth.py:155-158`,
  `teleflow/gateway/main.py:199-207`) — `(indirecto)`
  `tests/test_auditoria.py::test_todo_scope_esta_clasificado`,
  `tests/test_auditoria.py::test_toda_ruta_con_scope_de_escritura_pasa_por_el_marcador`
- [ ] Dado `POST /compose`, cuando el gateway lo proxea, entonces espera `compose_timeout`
  (660 s por default) en vez del timeout general del cliente (`teleflow/gateway/main.py:780-781`,
  `config.py:58`), y la cadena timeout del proveedor < gateway < `proxy_read_timeout` de nginx
  crece hacia afuera — `tests/test_composer.py::test_la_cadena_de_timeouts_es_estrictamente_creciente`
  (ver "Discrepancias": el test lee el timeout de Anthropic, 120 s, no el de Ollama, 600 s)
- [ ] Dado el composer caido, cuando se llama a cualquier ruta del composer por el gateway,
  entonces responde `502` con `Servicio no disponible` (`teleflow/gateway/main.py:430-431`) — `(sin test)`
- [ ] Dado el contrato OpenAPI del gateway, cuando se genera, entonces las rutas del composer
  llevan tag `composer` y `operation_id` explicitos y unicos (`componer_draft`, `listar_drafts`,
  `obtener_draft`, `operar_draft`, `editar_draft`) — `(indirecto)`
  `tests/test_openapi_contract.py::test_toda_ruta_esta_agrupada_en_una_familia_conocida`,
  `tests/test_openapi_contract.py::test_los_operation_id_son_unicos`

## Impacto en lo existente

Esta carpeta no cambia codigo. Lo que depende del modulo, y por lo tanto se rompe si cambia:

- **Contrato de borrador.** `_draft_out` (`teleflow/composer_service/main.py:279-301`) lo consumen la pantalla de revision
  (`review-ui/src/api.js:27-40`, `review-ui/src/App.jsx:89`, `App.jsx:154-158`,
  `App.jsx:278-281`) y el CLI (`teleflow/cli.py:126-128`). Renombrar `validation.parses`,
  `editado` o `source_generado` rompe la pantalla.
- **Registro de flows.** La aprobacion es un cliente mas de `POST /flows/{name}`
  (`teleflow/gateway/main.py:604-652`): hereda la validacion del parser (`422` si no valida) y la
  inmutabilidad de versiones del registry (`teleflow/registry_service/main.py:85-86`,
  `teleflow/registry_service/main.py:109-117`), que llegan al revisor envueltas en el `422` de
  `teleflow/composer_service/main.py:180-185`.
- **Lenguaje `.tflow`.** `DSL_SYSTEM_PROMPT` (`providers.py:20-148`) es una segunda descripcion
  de la gramatica, en texto, que no se contrasta con `teleflow/dsl/teleflow.lark` (ADR-001). Un
  cambio del lenguaje no lo actualiza solo `(inferencia)`: los borradores empiezan a no compilar y
  la unica señal es `validation.parses == false`. Ver `spec/features/base-lenguaje-tflow/spec.md`.
- **Parser-service.** El composer depende de `POST /parse` en tiempo de composicion y de edicion
  (`teleflow/composer_service/main.py:118-122`); caido, degrada a `parses: None` sin bloquear.
- **Esquema.** `flow_drafts` recibio columnas nullable sin backfill en `0003` y `0007`; una
  columna nueva sigue ese patron (`0007_fuente_generada_del_borrador.py:21-23`). Pods viejos
  durante un upgrade no leen `source_generado` `(inferencia)`.
- **Configuracion.** `LLM_PROVIDER` real sin `LLM_API_KEY` impide arrancar el contenedor
  (`providers.py:434-439`); el default `stub` en `config.py:36`, `docker-compose.yml:15` y
  `helm/teleflow/values.yaml:27` es lo que permite levantar un clon nuevo.

## Fuentes

- `teleflow/composer_service/main.py:37-47` — `lifespan`: construye el proveedor al arrancar.
- `teleflow/composer_service/main.py:60-105` — `POST /compose`; `:71-83` mapeo de errores.
- `teleflow/composer_service/main.py:108-135` — `_validate_source` y el estado `parses: None`.
- `teleflow/composer_service/main.py:163-217` — aprobar y rechazar.
- `teleflow/composer_service/main.py:226-276` — `PATCH /drafts/{id}/source` y sus tres garantias.
- `teleflow/composer_service/providers.py:151-168` — `LLMConfigurationError`,
  `LLMRequestRejected`, `LLMTransientError`.
- `teleflow/composer_service/providers.py:191-254` — `_post_json`: reintentos y clasificacion.
- `teleflow/composer_service/providers.py:418-447` — `get_provider` sin fallback al stub.
- `teleflow/common/config.py:35-58` — `llm_*` y `compose_timeout`.
- `teleflow/common/retry.py:12`, `:26-28`, `:41-48` — criterio transitorio y full jitter compartidos.
- `teleflow/common/models.py:174-207` — `FlowDraft`.
- `teleflow/gateway/main.py:773-816` — rutas del composer y scopes.
- `teleflow/gateway/auth.py:30`, `:37-38`, `:53`, `:155-158` — scopes y nombre de la key de bootstrap.
- `alembic/versions/0001_initial.py:114-126`, `0003_draft_validation.py:17-27`,
  `0007_fuente_generada_del_borrador.py:16-27` — esquema de `flow_drafts`.
- `tests/test_composer.py` — 36 funciones de test (varias parametrizadas) sobre proveedores,
  validacion, compose y edicion.
- `review-ui/tests/revision.spec.js:71-101`, `:103-117`, `:238-327` — aprobar, rechazar, stub y
  correccion por la pantalla.
- [[2026-06-30-adr-003-llm-configurable]] — proveedor por variable de entorno.
- [[2026-07-25-composer-llm-fallos-explicitos]] — proveedor explicito, borrador validado, errores clasificados.
- [[2026-08-27-correccion-del-borrador-en-la-revision]] — edicion en la revision y `source_generado`.

## Discrepancias doc ↔ codigo

Detectadas al escribir esta linea base (comprobadas, sin corregir):

- **ADR-003 describe el fallback que se retiro.** Dice que `get_provider()` cae a Stub si falta
  `LLM_API_KEY` y cita `providers.py:154-164`, y que `.env.example` trae `anthropic`
  (`wiki/Knowledge/decisions/2026-06-30-adr-003-llm-configurable.md:29-31`). Hoy `get_provider`
  levanta (`providers.py:434-439`), esas lineas son las excepciones, y `.env.example:26` trae
  `LLM_PROVIDER=stub`. El ADR de fallos explicitos lo reemplazo en ese punto y ADR-003 no se marco.
- **El ADR de correccion dice que lo editado se valida via `POST /parse`**
  (`2026-08-27-correccion-del-borrador-en-la-revision.md:68-70`). El codigo lo hace con
  `PATCH /drafts/{id}/source`, que llama a `_validate_source` contra el parser-service
  (`teleflow/composer_service/main.py:269`, `review-ui/src/api.js:39-40`), como dicen las propias notas de implementacion
  del ADR (`:120-123`). El `POST /parse` del gateway no participa.
- **El mismo ADR dice que ningun formulario envia `base_source`**
  (`2026-08-27-correccion-del-borrador-en-la-revision.md:59-63`). El formulario de la pantalla hoy
  lo envia: si existe un flow registrado con ese nombre, manda su fuente `latest`
  (`review-ui/src/App.jsx:466-468`, `review-ui/src/api.js:41-47`). El CLI sigue sin exponerlo
  (`cli.py:121-123`).
- **`test_la_cadena_de_timeouts_es_estrictamente_creciente` no mide el timeout que dice.** La
  regex toma el primer `timeout=<n>,` de `providers.py` (`tests/test_composer.py:630-636`), que es
  el de Anthropic, 120 s (`providers.py:288`), mientras el comentario de la configuracion dice que
  el que importa es el de Ollama, 600 s (`config.py:54-57`, `providers.py:366`). Si el de Ollama
  subiera por encima de 660 s, el test seguiria pasando. Tampoco contempla los reintentos: con
  Ollama, un 5xx despues de una generacion larga se reintenta hasta 3 veces de 600 s
  (`providers.py:240-252`), que supera los 660 s del gateway `(inferencia)`.
- **`LLM_MAX_TOKENS` y `LLM_RETRY_*` de `.env.example` no llegan al contenedor.** Estan en
  `.env.example:32-37`, pero el bloque `x-python-env` de `docker-compose.yml:3-26` no los
  reenvia, el `Dockerfile` no copia `.env` (`Dockerfile:7-10`) y `helm/teleflow/values.yaml` solo
  declara `LLM_PROVIDER` (busqueda de `LLM` en `helm/teleflow/`). En el stack corren siempre los
  defaults de `config.py:43-48`. `COMPOSE_TIMEOUT` tampoco se reenvia (misma busqueda).
- **El docstring del modulo esta incompleto.** `teleflow/composer_service/main.py:3-9` lista cinco rutas y omite
  `PATCH /drafts/{id}/source`; describe `GET /drafts/{id}` como "detalle con diff base", pero la
  respuesta solo trae `base_source` y el diff lo calcula la pantalla (`teleflow/composer_service/main.py:296-300`,
  `review-ui/src/App.jsx:278-281`).
- **El proveedor del `lifespan` se descarta.** `teleflow/composer_service/main.py:43` lo construye para validar la
  configuracion y `compose` construye otro por request (`teleflow/composer_service/main.py:64`). No es un error de
  comportamiento con `Settings` cacheadas (`config.py:96-98`), pero el comentario de `teleflow/composer_service/main.py:40-42`
  sugiere que el proveedor vive desde el arranque.
- **El ADR de fallos explicitos define `validation` como `{parses: bool, issues}`**
  (`2026-07-25-composer-llm-fallos-explicitos.md:64`); el codigo agrega `checked_at` siempre y
  `error` cuando `parses` es `None` (`teleflow/composer_service/main.py:129-135`), como ya anticipaba el mismo ADR en
  `:107-110`.
