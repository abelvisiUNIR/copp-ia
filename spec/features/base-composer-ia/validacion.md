---
project: copp-ia
type: validacion
status: implementada
feature: base-composer-ia
provenance: copp-ia@devyos@4c44b4c
validated: 2026-09-14
---

# Validacion contra la spec — Linea base del composer IA

<!--
  status: borrador | implementada (linea base as-built)
  Lo escribe el subagente `validador-spec`. No escribe tests: un criterio sin test vuelve al
  implementador. Un criterio NO CUMPLE nunca se "arregla" editando la spec para que calce.
-->

Modo **as-built**: el objetivo es medir cobertura, no aprobar. Provenance obtenida con
`git rev-parse --abbrev-ref HEAD` (`devyos`) y `git rev-parse --short HEAD` (`4c44b4c`). La spec
se escribio en `ffd585d`; `git log --oneline ffd585d..HEAD -- teleflow tests review-ui alembic
.env.example docker-compose.yml` no devuelve commits, asi que el codigo y los tests validados son
los mismos que leyo la spec. El working tree tiene cambios sin commitear solo en `.claude/agents/`
y en tres carpetas `spec/features/base-*` sin trackear (`git status --short`); ningun archivo de
`teleflow/`, `tests/` ni `review-ui/` modificado.

`plan.md` todavia no existe en esta carpeta al momento de validar: los tests del modulo se tomaron
de la indicacion de quien invoco al validador (`tests/test_composer.py`, mas los indirectos que
cita `spec.md`).

**Resumen: 53 criterios — 21 CUMPLE, 0 NO CUMPLE, 32 SIN TEST.**

## Gates ejecutados

| Comando | Resultado | Fecha | Commit |
|---|---|---|---|
| `mypy .` | **1 error**, 82 archivos: `tests/test_doc_contract.py:26: error: Library stubs not installed for "yaml" [import-untyped]`. Falta `types-PyYAML` en `.venv` (sin salida a PyPI desde este entorno). Ajeno al modulo y no es un error de tipos del codigo. | 2026-09-14 | `4c44b4c` |
| `mypy teleflow/composer_service` (modulo) | `Success: no issues found in 3 source files` | 2026-09-14 | `4c44b4c` |
| `pytest -m "not e2e" -q` | **no ejecutada en esta validacion** (la suite completa tarda ~23 min con el repo en Google Drive). Estado conocido del entorno, **reportado por quien invoco al validador, no verificado aca**: 10 errores en `tests/test_lease_de_instancia.py` por `aiosqlite` no instalado, ajenos a este modulo. | 2026-09-14 | `4c44b4c` |
| `pytest -p no:cacheprovider -v tests/test_composer.py` + indirectos citados (`tests/test_gateway_scopes.py::test_sin_config_la_key_global_conserva_todos_los_permisos`, `tests/test_auditoria.py::test_todo_scope_esta_clasificado`, `tests/test_auditoria.py::test_toda_ruta_con_scope_de_escritura_pasa_por_el_marcador`, `tests/test_openapi_contract.py::test_toda_ruta_esta_agrupada_en_una_familia_conocida`, `tests/test_openapi_contract.py::test_los_operation_id_son_unicos`, `tests/test_adapters.py::test_rest_status_transitorio_es_retryable`) | **54 passed**, 1 warning (`StarletteDeprecationWarning` de `.venv/Lib/site-packages/fastapi/testclient.py:1`, ajeno), 70.49 s. De esos, 44 items son de `tests/test_composer.py` (34 funciones, varias parametrizadas), todos `PASSED`. | 2026-09-14 | `4c44b4c` |
| `pytest -p no:cacheprovider -q tests/test_openapi_contract.py::test_los_operation_id_no_son_los_autogenerados` | **1 passed**, 5.68 s (corrido para precisar la cobertura parcial del criterio 53) | 2026-09-14 | `4c44b4c` |
| `pytest -m e2e -q` | **no ejecutado** — stack no levantado: `curl -sf http://localhost:8000/health` salio con codigo 7 (conexion rechazada). | 2026-09-14 | `4c44b4c` |
| `review-ui/tests/revision.spec.js` (Playwright) | **no ejecutado** — requiere el stack en `:3100`. Se leyo el archivo; ningun resultado se da por verde. | 2026-09-14 | `4c44b4c` |

Todos los tests Python se corrieron con el venv del repo (`.venv/Scripts/pytest.exe`, Python 3.14.3).

## Matriz criterio → evidencia

Criterios copiados literales de `spec.md` y agrupados como alli. La cita final de cada criterio en
la spec (`— tests/...`, `(sin test)`, `(indirecto)`) se movio a la columna de tests; lo demas es
texto literal. Las sub-viñetas de un criterio se separan con `<br>`.

Reglas aplicadas:

- Criterio compuesto con una parte probada y otra no → **SIN TEST**, detallando que parte quedo
  cubierta.
- Criterio cuya unica evidencia es Playwright (`review-ui/tests/revision.spec.js`) → **SIN TEST**
  ejecutable: el test existe y se leyo, pero no se corrio (stack no levantado).
- Para cada SIN TEST se leyo el codigo citado para ver si lo contradice.

### Arranque y seleccion de proveedor

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 1 | Dado `LLM_PROVIDER` en `anthropic` u `openai` con `LLM_API_KEY` vacia, cuando se llama a `get_provider`, entonces levanta `LLMConfigurationError` y el mensaje contiene `LLM_API_KEY` y `stub` | `tests/test_composer.py::test_proveedor_real_sin_credencial_levanta` (2 parametrizaciones; `pytest.raises` y los dos `in`, `test_composer.py:39-45`) | CUMPLE |
| 2 | Dado `LLM_PROVIDER=anthropic` y `LLM_API_KEY` vacia, cuando arranca la app del composer, entonces el `lifespan` levanta `LLMConfigurationError` y el servicio no queda sirviendo | `tests/test_composer.py::test_el_servicio_no_arranca_sin_credencial` (`TestClient(app)` dentro de `pytest.raises`, `test_composer.py:393-399`) | CUMPLE |
| 3 | Dado `LLM_PROVIDER` en `anthropic`, `openai` u `ollama` con key `k`, cuando se llama a `get_provider`, entonces nunca devuelve `StubProvider` y `name` es el proveedor pedido | `tests/test_composer.py::test_ningun_proveedor_real_devuelve_el_stub` (3 parametrizaciones, `test_composer.py:55-56`; ver observacion sobre el `return` de `:53-54`) | CUMPLE |
| 4 | Dado cada valor de `LLM_PROVIDER`, cuando se llama a `get_provider`, entonces construye:<br>- `stub` → `StubProvider` con `name == "stub"`<br>- `anthropic` con key → `AnthropicProvider`<br>- `openai` con key → `OpenAIProvider`<br>- `ollama` sin key → `OllamaProvider` | `tests/test_composer.py::test_stub_solo_cuando_se_lo_pide` (`:61-62`), `tests/test_composer.py::test_anthropic_con_credencial` (`:68`), `tests/test_composer.py::test_openai_con_credencial` (`:72`), `tests/test_composer.py::test_ollama_no_necesita_credencial` (`:77`) | CUMPLE |
| 5 | Dado `LLM_PROVIDER` igual a `"  Anthropic "`, `"STUB"` u `"OpenAI"`, cuando se llama a `get_provider`, entonces `name` es el valor sin espacios y en minusculas | `tests/test_composer.py::test_el_valor_se_normaliza` (3 parametrizaciones, `:84`) | CUMPLE |
| 6 | Dado `LLM_PROVIDER` igual a `antropic`, `gpt`, `claude` o vacio, cuando se llama a `get_provider`, entonces levanta `LLMConfigurationError` con `no es un proveedor conocido` | `tests/test_composer.py::test_proveedor_desconocido_levanta` (4 parametrizaciones incluido `""`, `:90-92`) | CUMPLE |
| 7 | Dado `.env.example`, cuando `LLM_API_KEY` esta vacia, entonces `LLM_PROVIDER` es `stub` o vacio | `tests/test_composer.py::test_env_example_arranca_sin_credenciales` (`:420-424`). Hoy `.env.example:26-27` trae `LLM_PROVIDER=stub` y `LLM_API_KEY=` | CUMPLE |
| 8 | Dado un proveedor sin `LLM_MODEL` ni `LLM_BASE_URL`, cuando se construye, entonces usa `claude-fable-5` en `https://api.anthropic.com`, `gpt-4o` en `https://api.openai.com` o `llama3.1` en `http://ollama:11434` (`providers.py:275-276`, `providers.py:310-311`, `providers.py:344-345`) | ninguno (los tests de construccion solo afirman el tipo; Grep de `claude-fable-5\|gpt-4o\|llama3.1` en `tests/` sin coincidencias). Codigo leido: coincide con el criterio | SIN TEST |
| 9 | Dada una instalacion sin `LLM_PROVIDER` configurado, cuando arranca el composer, entonces usa `stub` (`config.py:36`) | ninguno (Grep de `llm_provider\|LLM_PROVIDER` fuera de `tests/test_composer.py` sin coincidencias; dentro, todos los tests fijan el valor explicitamente). Codigo leido: `teleflow/common/config.py:36` es `"stub"` | SIN TEST |

### Llamada al proveedor: clasificacion y reintentos

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 10 | Dada una respuesta del proveedor, cuando se genera con `llm_retry_attempts=3`, entonces se clasifica asi:<br>- `503` y despues `200` → devuelve el texto con 2 llamadas<br>- `429` con `retry-after` y despues `200` → devuelve el texto con 2 llamadas<br>- `503` persistente → `LLMTransientError` despues de 3 llamadas<br>- `400` → `LLMRequestRejected` con 1 llamada<br>- `401`, `403` o `404` → `LLMConfigurationError`<br>- `408` → se reintenta (`teleflow/common/retry.py:12`, `providers.py:240-243`)<br>- error de red (conexion rechazada, DNS, TLS, timeout de conexion) → se reintenta (`providers.py:222-223`)<br>- `200` cuyo JSON no es un objeto → `LLMRequestRejected` (`providers.py:227-229`) | Cubiertos: `tests/test_composer.py::test_un_503_se_reintenta_y_puede_salir_bien` (`:158-159`), `tests/test_composer.py::test_un_429_se_reintenta` (`:179-180`), `tests/test_composer.py::test_transitorio_persistente_agota_intentos` (`:186-189`), `tests/test_composer.py::test_un_400_falla_al_primer_intento` (`:166-169`), `tests/test_composer.py::test_credencial_o_modelo_mal_es_config_nuestra` (3 parametrizaciones, `:197-198`). Sin test en el composer: `408`, error de red y `200` no-objeto. `tests/test_adapters.py::test_rest_status_transitorio_es_retryable[408]` pasa, pero prueba `run_automated` del executor (`test_adapters.py:171-176`), no `_post_json`: no es el resultado observable del composer | SIN TEST (parcial: 5 de 8 casos cubiertos) |
| 11 | Dado un timeout de lectura contra el proveedor con `timeout=600`, cuando se llama a `_post_json`, entonces levanta `LLMTransientError` en el primer intento sin reintentar, y el mensaje contiene `600` y `self-hosted` | `tests/test_composer.py::test_un_timeout_de_lectura_falla_en_el_primer_intento` (`:612-619`) | CUMPLE |
| 12 | Dado un fallo transitorio con `retry-after`, cuando se espera antes del siguiente intento, entonces la espera es ese valor topeado a `llm_retry_max_delay`; sin `retry-after`, es full jitter sobre `llm_retry_base_delay * 2^intento` con el mismo tope (`providers.py:243-249`, `retry.py:41-48`) | ninguno: todos los tests usan `llm_retry_base_delay=0.0` y `llm_retry_max_delay=0.0` (`test_composer.py:144-146`) y ninguno mide `asyncio.sleep`. Codigo leido (`teleflow/composer_service/providers.py:243-252`, `teleflow/common/retry.py:41-48`): coincide | SIN TEST |
| 13 | Dado `llm_retry_attempts` menor que 1, cuando se llama al proveedor, entonces se hace exactamente 1 intento (`providers.py:200`) | ninguno (todos los tests usan `llm_retry_attempts=3` o el default). Codigo leido: `max(1, settings.llm_retry_attempts)` en `teleflow/composer_service/providers.py:200` | SIN TEST |

### Respuestas 200 que no sirven como borrador

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 14 | Dada una respuesta de Anthropic con `stop_reason: refusal` y `content` vacio, cuando se genera, entonces levanta `LLMRequestRejected` con `declinó` y `Reformulá` en el mensaje | `tests/test_composer.py::test_refusal_no_revienta_con_indexerror` (`:208-213`) | CUMPLE |
| 15 | Dada una respuesta truncada, cuando se genera, entonces levanta `LLMConfigurationError`:<br>- Anthropic con `stop_reason: max_tokens`, mensaje con `LLM_MAX_TOKENS`<br>- OpenAI con `finish_reason: length`<br>- Ollama con `done_reason: length` (`providers.py:369-372`) | Anthropic: `tests/test_composer.py::test_respuesta_truncada_no_se_guarda_como_borrador` (`:222-224`). OpenAI: `tests/test_composer.py::test_openai_truncado_tambien_se_detecta` (`:231-232`). Ollama: ninguno (Grep de `done_reason\|OllamaProvider(` en `tests/`: solo el `isinstance` de `:77`). Codigo leido: coincide | SIN TEST (parcial: Anthropic y OpenAI cubiertos) |
| 16 | Dada una respuesta sin texto o solo con espacios, cuando se genera, entonces levanta `LLMRequestRejected` con `el modelo no devolvió texto` (`providers.py:263-265`) | ninguno (Grep de `no devolvió texto` en `tests/` sin coincidencias). Codigo leido: coincide | SIN TEST |
| 17 | Dada una respuesta de OpenAI sin `choices`, cuando se genera, entonces levanta `LLMRequestRejected` (`providers.py:328-330`) | ninguno (todos los payloads OpenAI de los tests traen `choices`). Codigo leido: coincide | SIN TEST |
| 18 | Dada `llm_max_tokens=1234`, cuando se genera con OpenAI, entonces el payload lleva `max_tokens == 1234`; en Anthropic viaja como `max_tokens` (`providers.py:284`) y en Ollama como `options.num_predict` (`providers.py:354`) | OpenAI: `tests/test_composer.py::test_max_tokens_viaja_en_el_payload` (`:253`). Anthropic y Ollama: ninguno (Grep de `num_predict` en `tests/` sin coincidencias). Codigo leido: coincide | SIN TEST (parcial: OpenAI cubierto) |

### `POST /compose`

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 19 | Dado `LLM_PROVIDER=stub` y un parser que responde `valid: false` con un issue, cuando se compone `alta_socio`, entonces se persiste un borrador con `provider == "stub"` y `validation.parses == false`, y la respuesta trae `provider: "stub"` y el mensaje del issue | `tests/test_composer.py::test_compose_guarda_el_borrador_marcado` (`:373-377`; llama a `compose` directo, no por HTTP; ver observacion sobre "se persiste") | CUMPLE |
| 20 | Dado un pedido que el proveedor resuelve, cuando se hace `POST /compose`, entonces responde `201` con `status: "pending"`, `editado: false` y `source_generado: null` (`teleflow/composer_service/main.py:60`, `models.py:193`, `teleflow/composer_service/main.py:294`, `teleflow/composer_service/main.py:300`) | Python: ninguno (`test_compose_guarda_el_borrador_marcado` no pasa por HTTP ni afirma `status`, `editado` ni `source_generado`). `(indirecto)` `review-ui/tests/revision.spec.js` `crearBorrador` exige solo `201` (`revision.spec.js:19`) y **no se ejecuto**. Codigo leido: `teleflow/composer_service/main.py:60`, `teleflow/common/models.py:193` (`default="pending"`), `teleflow/composer_service/main.py:294,300`: coincide | SIN TEST |
| 21 | Dado un fallo del proveedor, cuando se hace `POST /compose`, entonces no se persiste nada y responde (`teleflow/composer_service/main.py:71-83`):<br>- `LLMRequestRejected` → `422` con `El proveedor rechazó el pedido`<br>- `LLMConfigurationError` → `500` con `Composer mal configurado`<br>- `LLMTransientError` → `502` con `Proveedor LLM no disponible` | ninguno (Grep de `rechazó el pedido\|mal configurado\|no disponible:` en `tests/` sin coincidencias en tests del composer). Codigo leido: los tres `raise HTTPException` ocurren antes de `session.add` (`teleflow/composer_service/main.py:71-83` vs `:100`): coincide | SIN TEST |
| 22 | Dado un `base_source`, cuando se compone, entonces el prompt es la descripcion seguida de `Versión actual del flow (modificala según el pedido):` y la fuente (`teleflow/composer_service/main.py:65-68`) | ninguno (Grep de `base_source` en `tests/test_composer.py` sin coincidencias). Codigo leido: coincide | SIN TEST |
| 23 | Dado un texto generado que empieza con tres backticks, cuando se compone, entonces se eliminan todas las lineas que empiezan con tres backticks (`teleflow/composer_service/main.py:86-89`) | ninguno (Grep de tres backticks en `tests/test_composer.py` sin coincidencias). Codigo leido: coincide (ver observacion sobre `l.strip()`) | SIN TEST |
| 24 | Dado `LLM_PROVIDER=stub`, cuando se compone, entonces el borrador es un esqueleto con el pedido comentado linea por linea con `// `, `process "proceso_borrador"` y `step "paso_inicial"` (`providers.py:385-408`), compila y la pantalla lo muestra como generado por el stub | `(indirecto)` `review-ui/tests/revision.spec.js` "el borrador muestra su estado de validación y quién lo generó" (`:103-117`), **no ejecutado**. Aun corriendo, solo afirma `.validation.ok`, `generado por` y `esqueleto para editar a mano`: no afirma el `// ` por linea ni los nombres `proceso_borrador` / `paso_inicial`. Python: ninguno (Grep de `proceso_borrador\|paso_inicial` en `tests/` sin coincidencias). Codigo leido (`teleflow/composer_service/providers.py:385-408`): coincide | SIN TEST |

### Validacion del borrador contra el parser

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 25 | Dado un parser que responde `valid: true`, cuando se valida, entonces `parses` es `true`, `issues` es `[]` y `checked_at` no es vacio | `tests/test_composer.py::test_borrador_que_compila_queda_marcado_ok` (`:302-304`) | CUMPLE |
| 26 | Dado un parser que responde `valid: false` con issues, cuando se valida, entonces no levanta, `parses` es `false` e `issues` son los del parser | `tests/test_composer.py::test_borrador_que_no_compila_se_marca_pero_no_levanta` (`:313-314`, igualdad de la lista) | CUMPLE |
| 27 | Dado un parser inalcanzable (`httpx.ConnectError`), cuando se valida, entonces `parses` es `None` (ni `true` ni `false`) y la validacion trae `error` | `tests/test_composer.py::test_parser_caido_no_se_confunde_con_compila` (`:324-325`, `is None`) | CUMPLE |
| 28 | Dado un error que no es de transporte ni de lectura de la respuesta (`RuntimeError`), cuando se valida, entonces la excepcion se propaga | `tests/test_composer.py::test_un_bug_nuestro_no_se_disfraza_de_parser_caido` (`:332-333`) | CUMPLE |
| 29 | Dado un parser que responde un status 4xx/5xx o un cuerpo que no es JSON, cuando se valida, entonces `parses` es `None` (`teleflow/composer_service/main.py:123-129`) | ninguno: el `_FakeResponse` de los tests tiene `raise_for_status` que nunca levanta y `json` que siempre devuelve el payload (`test_composer.py:262-266`). Codigo leido: `HTTPStatusError` es `httpx.HTTPError` y `JSONDecodeError` es `ValueError`, ambos atrapados en `teleflow/composer_service/main.py:125`: coincide | SIN TEST |

### Consulta de borradores

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 30 | Dados borradores guardados, cuando se hace `GET /drafts`, entonces devuelve como maximo 100 ordenados por `created_at` descendente, filtrables por `?status=`, con `provider`, `validation` y `editado` y sin `source`, `base_source` ni `source_generado` (`teleflow/composer_service/main.py:138-145`, `teleflow/composer_service/main.py:279-301`) | Python: ninguno (Grep de `list_drafts\|include_source` en `tests/` sin coincidencias; `tests/test_gateway_scopes.py:104` pega a `/drafts` del gateway y solo mira `!= 403`). `(indirecto)` `review-ui/tests/revision.spec.js` "un borrador corregido queda marcado en la lista" (`:314-327`), **no ejecutado**, y cubre solo `editado`. Codigo leido: coincide | SIN TEST |
| 31 | Dado un id que no existe, cuando se hace `GET /drafts/{id}`, entonces responde `404` con `Borrador no encontrado`; con un id que no es UUID, `422` (`teleflow/composer_service/main.py:148-154`) | ninguno (Grep de `Borrador no encontrado\|get_draft` en `tests/` sin coincidencias). Codigo leido: `draft_id: uuid.UUID` y el `404` en `teleflow/composer_service/main.py:149-153`: coincide | SIN TEST |

### Aprobacion

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 32 | Dado un borrador recien compuesto, cuando se aprueba desde la pantalla con version `1.0.0`, entonces el flow aparece en `GET /api/flows` | `(indirecto)` `review-ui/tests/revision.spec.js` "aprobar despliega ese borrador" (`:71-87`; el assert `toContain(nombre)` de `:85-86` si prueba el resultado observable). **No ejecutado**: Playwright requiere el stack | SIN TEST (sin test ejecutable) |
| 33 | Dado un borrador `pending` y un deploy que responde `< 400`, cuando se hace `POST /drafts/{id}/approve` con `version`, `actor_id` y `comment`, entonces se hace `POST {gateway_url}/flows/{name}` con `X-TeleFlow-API-Key` igual a `TELEFLOW_API_KEY` y body `source` = `draft.source`, `version` y `description: "Aprobado desde draft <id>"`; el borrador queda `approved`, se agrega a `comments` `{actor, action: "approve", comment, version}` y la respuesta incluye `deploy` con el cuerpo del gateway (`teleflow/composer_service/main.py:172-195`) | ninguno (Grep de `approve_draft\|Aprobado desde` en `tests/` sin coincidencias). Codigo leido (`teleflow/composer_service/main.py:172-195`): coincide | SIN TEST |
| 34 | Dado un borrador `pending` y un deploy que responde `>= 400`, cuando se aprueba, entonces responde `422` con `message: "El deploy falló — el borrador sigue pending"` y `upstream` con el cuerpo del gateway, y el borrador sigue `pending` sin entrada nueva en `comments` (`teleflow/composer_service/main.py:180-185`) | ninguno (Grep de `sigue pending` en `tests/` sin coincidencias). Codigo leido: el `raise` de `:180-185` va antes de mutar `status` y `comments` (`:187-191`): coincide | SIN TEST |
| 35 | Dado un borrador `approved` o `rejected`, cuando se aprueba, entonces responde `409` con `Borrador ya <estado>` y no se llama al gateway; con un id inexistente, `404` (`teleflow/composer_service/main.py:166-170`) | ninguno. Codigo leido: `404` y `409` en `:167-170`, antes del `httpx.AsyncClient` de `:173`: coincide | SIN TEST |
| 36 | Dado un borrador con cambios en el editor sin guardar, cuando se pulsa aprobar y se cancela el aviso de `sin guardar`, entonces el flow no aparece en `GET /api/flows`; del lado del servidor, lo desplegado es siempre `draft.source` (`teleflow/composer_service/main.py:177`) | `(indirecto)` `review-ui/tests/revision.spec.js` "aprobar con cambios sin guardar avisa que se despliega lo guardado" (`:275-292`), **no ejecutado**. La parte del servidor (`draft.source` en `teleflow/composer_service/main.py:177`) no tiene test Python | SIN TEST (sin test ejecutable) |

### Rechazo

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 37 | Dado un borrador recien compuesto, cuando se rechaza desde la pantalla con un comentario, entonces el flow no aparece en `GET /api/flows` | `(indirecto)` `review-ui/tests/revision.spec.js` "rechazar no despliega nada" (`:89-101`; `not.toContain(nombre)` en `:99-100`), **no ejecutado** | SIN TEST (sin test ejecutable) |
| 38 | Dado un borrador `pending`, cuando se hace `POST /drafts/{id}/reject`, entonces queda `rejected` y se agrega a `comments` `{actor, action: "reject", comment}`; sobre uno que no es `pending` responde `409` y sobre uno inexistente `404` (`teleflow/composer_service/main.py:203-217`) | ninguno (Grep de `reject_draft` en `tests/` sin coincidencias). Codigo leido: coincide | SIN TEST |

### Correccion de la fuente

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 39 | Dado un borrador `pending` y un parser que responde `valid: true`, cuando se edita con una fuente distinta, entonces `source` queda con la fuente nueva, `validation.parses` es `true` en el borrador y en la respuesta, y hay exactamente 1 commit | `tests/test_composer.py::test_editar_revalida_contra_el_parser` (`:478-481`) | CUMPLE |
| 40 | Dado un borrador nunca editado, cuando se edita, entonces `source_generado` guarda la fuente anterior y la respuesta trae `editado: true` | `tests/test_composer.py::test_editar_guarda_lo_que_habia_escrito_el_modelo` (`:490-492`) | CUMPLE |
| 41 | Dado un borrador con `source_generado` ya guardado, cuando se edita otra vez, entonces `source_generado` no cambia | `tests/test_composer.py::test_la_segunda_edicion_no_pisa_el_original` (`:504`) | CUMPLE |
| 42 | Dada una edicion con `actor_id: "yosdey"` y un comentario, cuando se guarda, entonces la ultima entrada de `comments` es exactamente `{actor: "yosdey", action: "edit", comment: <el comentario>}` | `tests/test_composer.py::test_editar_deja_rastro_con_actor` (igualdad de dict, `:514-516`) | CUMPLE |
| 43 | Dado un borrador `approved`, cuando se edita, entonces responde `409` y no hay commit; con `rejected` pasa por la misma rama (`teleflow/composer_service/main.py:253-254`) | `approved`: `tests/test_composer.py::test_editar_un_borrador_ya_aprobado_es_conflicto` (`:530-531`). `rejected`: ninguno (Grep de `status="rejected"` en `tests/` sin coincidencias). Codigo leido: `status != "pending"` en `teleflow/composer_service/main.py:253` cubre ambos | SIN TEST (parcial: `approved` cubierto) |
| 44 | Dada una fuente que, sin espacios de los bordes, es igual a la guardada, cuando se edita, entonces no hay commit, `comments` no cambia, `source_generado` sigue `null` y `editado` es `false` | `tests/test_composer.py::test_editar_con_la_misma_fuente_no_marca_el_borrador` (`:542-545`) | CUMPLE |
| 45 | Dada una fuente vacia o solo con espacios, cuando se edita, entonces responde `422` y no hay commit | `tests/test_composer.py::test_editar_con_fuente_vacia_es_422` (fuente `"   "`, `:554-557`) | CUMPLE |
| 46 | Dada una fuente que no compila, cuando se edita, entonces se guarda igual, la respuesta trae `validation.parses == false` y los issues del parser | `tests/test_composer.py::test_editar_algo_que_no_compila_guarda_igual_y_lo_dice` (`:570-572`; ver observacion sobre el commit) | CUMPLE |
| 47 | Dado un borrador que compila, cuando se lo rompe desde el editor y se guarda, entonces el badge pasa a `no compila`, y al restaurar la fuente y guardar vuelve a `compila` | `(indirecto)` `review-ui/tests/revision.spec.js` "guardar revalida contra el parser, en los dos sentidos" (`:239-257`), **no ejecutado** | SIN TEST (sin test ejecutable) |
| 48 | Dado un id inexistente, cuando se edita, entonces responde `404` (`teleflow/composer_service/main.py:250-252`); con el parser caido, la edicion se guarda con `validation.parses == None` (`teleflow/composer_service/main.py:269`, `teleflow/composer_service/main.py:125-129`) | ninguno: `_SesionConBorrador.get` siempre devuelve el borrador (`test_composer.py:441-442`) y ningun test de edicion simula el parser caido. Codigo leido: coincide | SIN TEST |

### Exposicion por el gateway

| # | Criterio (literal de spec.md) | Test(s) que lo prueban | Resultado |
|---|---|---|---|
| 49 | Dada una key, cuando llama a las rutas del composer por el gateway, entonces el scope exigido es (`teleflow/gateway/main.py:775-816`); con scopes `*`, `GET /drafts` no da `403`:<br>- `POST /compose` → `compose:write`<br>- `GET /drafts` y `GET /drafts/{...}` → `compose:read`<br>- `POST /drafts/{...}` (incluye `approve` y `reject`) → `compose:write`<br>- `PATCH /drafts/{id}/source` → `flows:deploy` | Cubierto: `tests/test_gateway_scopes.py::test_sin_config_la_key_global_conserva_todos_los_permisos` (`test_gateway_scopes.py:104-105`, `/drafts` con `*` no da `403`). Por ruta: ninguno (Grep de `compose:write\|COMPOSE_WRITE\|/compose\|/source` en `tests/` sin coincidencias en tests de scopes). Codigo leido (`teleflow/gateway/main.py:775-816`): coincide | SIN TEST (parcial: solo el caso `*` sobre `GET /drafts`) |
| 50 | Dada una accion con `compose:write` o `flows:deploy`, cuando termina, entonces queda en `audit_log` porque ambos scopes son de escritura (`auth.py:155-158`, `teleflow/gateway/main.py:199-207`) | `(indirecto)` `tests/test_auditoria.py::test_todo_scope_esta_clasificado` y `tests/test_auditoria.py::test_toda_ruta_con_scope_de_escritura_pasa_por_el_marcador`, ambos `PASSED`, pero ninguno prueba el resultado observable: el primero exige que todo scope este en lectura **o** escritura (`test_auditoria.py:213-222`), el segundo itera `SCOPES_DE_ESCRITURA` sea cual sea su contenido (`:237-242`). Si `COMPOSE_WRITE` pasara a `SCOPES_DE_LECTURA`, los dos seguirian verdes. Ninguno toca `audit_log`. Codigo leido: `COMPOSE_WRITE` y `FLOWS_DEPLOY` estan en `teleflow/gateway/auth.py:155-158` (`teleflow/gateway/main.py:199-207` no re-leido) | SIN TEST |
| 51 | Dado `POST /compose`, cuando el gateway lo proxea, entonces espera `compose_timeout` (660 s por default) en vez del timeout general del cliente (`teleflow/gateway/main.py:780-781`, `config.py:58`), y la cadena timeout del proveedor < gateway < `proxy_read_timeout` de nginx crece hacia afuera | `tests/test_composer.py::test_la_cadena_de_timeouts_es_estrictamente_creciente` (`PASSED`) prueba solo la desigualdad `llm < gateway < proxy` con `llm` = primer `timeout=<n>,` de `providers.py` = 120 (Anthropic, `providers.py:288`), no el de Ollama (600, `providers.py:366`), como ya anota la spec. Ningun test comprueba que la ruta `/compose` del gateway pase `compose_timeout` a `_proxy` (`teleflow/gateway/main.py:780-781`), ni el default 660. Codigo leido: `teleflow/gateway/main.py:780-781`, `teleflow/common/config.py:58` (660.0), `review-ui/nginx.conf.template:47` (720s); con Ollama la cadena real 600 < 660 < 720 se cumple, pero no la mide ningun test | SIN TEST (parcial: desigualdad con el timeout de Anthropic) |
| 52 | Dado el composer caido, cuando se llama a cualquier ruta del composer por el gateway, entonces responde `502` con `Servicio no disponible` (`teleflow/gateway/main.py:430-431`) | ninguno para rutas del composer: `tests/test_gateway_scopes.py::test_deploy_con_el_parser_caido_da_502_no_500` (`:113-121`) prueba `POST /flows/x`, otra ruta; `test_sin_config_la_key_global_conserva_todos_los_permisos` llega a `/drafts` con el composer caido pero solo afirma `!= 403`. Codigo leido: `_proxy` atrapa `httpx.RequestError` y devuelve `_bad_gateway` (`teleflow/gateway/main.py:430-431`, `:394-396`, `detail: "Servicio no disponible: <base_url>"`): coincide | SIN TEST |
| 53 | Dado el contrato OpenAPI del gateway, cuando se genera, entonces las rutas del composer llevan tag `composer` y `operation_id` explicitos y unicos (`componer_draft`, `listar_drafts`, `obtener_draft`, `operar_draft`, `editar_draft`) | `(indirecto)` `tests/test_openapi_contract.py::test_los_operation_id_son_unicos` (unicidad, `test_openapi_contract.py:38-40`) y `tests/test_openapi_contract.py::test_los_operation_id_no_son_los_autogenerados` (explicitos, `:44-47`; no citado por la spec, corrido aca: `PASSED`). `tests/test_openapi_contract.py::test_toda_ruta_esta_agrupada_en_una_familia_conocida` exige **algun** tag de `FAMILIAS` (`:16`, `:51-53`), no `composer` en estas rutas. Ningun test afirma los cinco nombres (Grep de `componer_draft\|operar_draft\|editar_draft\|listar_drafts` en `tests/` sin coincidencias). Codigo leido: tags y `operation_id` en `teleflow/gateway/main.py:775-804`: coincide | SIN TEST (parcial: unicidad y explicitos cubiertos) |

### Conteo

| Grupo | Criterios | CUMPLE | NO CUMPLE | SIN TEST |
|---|---|---|---|---|
| Arranque y seleccion de proveedor | 9 | 7 | 0 | 2 |
| Clasificacion y reintentos | 4 | 1 | 0 | 3 |
| Respuestas 200 que no sirven | 5 | 1 | 0 | 4 |
| `POST /compose` | 6 | 1 | 0 | 5 |
| Validacion contra el parser | 5 | 4 | 0 | 1 |
| Consulta de borradores | 2 | 0 | 0 | 2 |
| Aprobacion | 5 | 0 | 0 | 5 |
| Rechazo | 2 | 0 | 0 | 2 |
| Correccion de la fuente | 10 | 7 | 0 | 3 |
| Exposicion por el gateway | 5 | 0 | 0 | 5 |
| **Total** | **53** | **21** | **0** | **32** |

Contraste con las marcas de la spec:

- Todo criterio que la spec marca `(sin test)`, entero o en alguna parte, resulto SIN TEST: ninguno
  tiene un test que la spec no viera.
- Los 7 criterios con evidencia `(indirecto)` de Playwright (20, 24, 30, 32, 36, 37, 47; en el 20 y
  el 30 es solo una parte) quedan SIN TEST porque no se pudieron ejecutar; 32, 36 (lado pantalla), 37 y 47
  pasarian a CUMPLE si Playwright corre verde, porque sus asserts prueban el resultado observable.
  24 no: el test no afirma el contenido del esqueleto.
- Los 3 `(indirecto)` Python del gateway (50, 53) y la cita de `test_adapters.py` en el 10 pasan,
  pero no prueban lo que el criterio promete del composer.
- El criterio 51, que la spec presenta con test, queda SIN TEST parcial por dos huecos: el cableado
  de `compose_timeout` en la ruta y el timeout de Ollama.

Para los 32 SIN TEST se leyo el codigo citado: en ninguno el codigo contradice el criterio. Eso no
los vuelve CUMPLE.

## Criterios sin test

Lo que la spec promete y ningun test comprueba. Cada uno es trabajo pendiente, no un detalle.

- **#8** — modelo y base URL por default de los tres proveedores reales.
- **#9** — sin `LLM_PROVIDER` configurado, el composer usa `stub`.
- **#10** — clasificacion en el composer de `408`, error de red y `200` cuyo JSON no es objeto (los otros 5 casos si).
- **#12** — espera entre intentos: `retry-after` topeado y full jitter con tope.
- **#13** — `llm_retry_attempts < 1` → exactamente 1 intento.
- **#15** — Ollama con `done_reason: length` → `LLMConfigurationError` (Anthropic y OpenAI si).
- **#16** — respuesta sin texto → `LLMRequestRejected` con `el modelo no devolvió texto`.
- **#17** — OpenAI sin `choices` → `LLMRequestRejected`.
- **#18** — `max_tokens` en el payload de Anthropic y `options.num_predict` en Ollama (OpenAI si).
- **#20** — `POST /compose` por HTTP: `201`, `status: "pending"`, `editado: false`, `source_generado: null`.
- **#21** — `POST /compose` ante fallo del proveedor: `422` / `500` / `502` con su texto y sin persistir.
- **#22** — prompt con `base_source`.
- **#23** — limpieza de fences de markdown.
- **#24** — contenido del esqueleto del stub (Playwright no ejecutado y, aun corriendo, no afirma el contenido).
- **#29** — parser que responde 4xx/5xx o cuerpo no JSON → `parses: None`.
- **#30** — `GET /drafts`: tope 100, orden, filtro `status`, campos incluidos y excluidos.
- **#31** — `GET /drafts/{id}`: `404` y `422`.
- **#32** — aprobar desde la pantalla despliega (solo Playwright, no ejecutado).
- **#33** — aprobacion exitosa: request al gateway, `approved`, entrada en `comments`, `deploy` en la respuesta.
- **#34** — deploy `>= 400` → `422`, borrador sigue `pending` sin comentario nuevo.
- **#35** — aprobar un borrador no `pending` → `409` sin llamar al gateway; inexistente → `404`.
- **#36** — aprobar con cambios sin guardar y cancelar no despliega (solo Playwright, no ejecutado); lado servidor sin test.
- **#37** — rechazar desde la pantalla no despliega (solo Playwright, no ejecutado).
- **#38** — `POST /drafts/{id}/reject`: `rejected`, entrada en `comments`, `409` y `404`.
- **#43** — editar un borrador `rejected` → `409` (`approved` si).
- **#47** — el badge sigue a la fuente guardada en los dos sentidos (solo Playwright, no ejecutado).
- **#48** — editar id inexistente → `404`; editar con parser caido → `parses: None`.
- **#49** — scope exigido por cada ruta del composer en el gateway (solo el caso `*` sobre `GET /drafts`).
- **#50** — `compose:write` y `flows:deploy` quedan en `audit_log` (los tests citados no fijan la clasificacion de esos dos scopes).
- **#51** — `/compose` del gateway usa `compose_timeout`; la cadena de timeouts medida con Ollama.
- **#52** — composer caido → `502` `Servicio no disponible` en sus rutas del gateway.
- **#53** — tag `composer` y los cinco `operation_id` concretos (unicidad y no autogenerados si).

Concentracion: todo el ciclo de aprobacion y rechazo (#32-#38) queda sin un solo test Python. Es el
camino que despliega codigo, y hoy su unica evidencia es Playwright contra el stack. Tambien quedan
sin test los tres codigos HTTP que la spec pone en el Objetivo como la distincion central del
modulo (#21): se prueba la excepcion de cada familia, no el `422` / `500` / `502` que ve el cliente.

## Comportamiento observado que la spec no menciona

Tests que prueban algo que ningun criterio pide, y precisiones sobre el alcance real de los
asserts. Se anota, no se decide aca.

- **`tests/test_composer.py`**: sus 34 funciones mapean todas a algun criterio; no hay tests que
  sobren en el archivo del modulo.
- **Conteo de tests en la spec**: `spec.md:435` dice "36 funciones de test"; Grep de
  `^(async )?def test_` en `tests/test_composer.py` da **34** (44 items al parametrizar). Observacion
  para una persona: la spec no se edita desde aca.
- **`review-ui/tests/revision.spec.js`**: ademas de los 7 tests que usa esta spec, tiene 11 que ningun
  criterio de este modulo pide (badge en una linea, los tres estados de validacion, confirmacion al
  aprobar algo que no compila, diff al abrir, sin API key, veredicto con cambios sin guardar, diff
  contra el modelo, fragmento con apuntador, ir a la linea y los tres de la columna de numeros). Son
  de la pantalla (`spec/features/base-review-ui/`), no del composer. No se ejecutaron.
- **Criterio #3**: `test_ningun_proveedor_real_devuelve_el_stub` hace `return` si `get_provider`
  levanta `LLMConfigurationError` (`test_composer.py:51-54`). Si un cambio hiciera levantar a los tres
  proveedores con key, el test pasaria sin ejecutar ningun assert. Hoy no ocurre: los tests de
  construccion del criterio #4 fijan que los tres se construyen con key.
- **Criterio #7**: el test acepta `LLM_PROVIDER` vacio (`test_composer.py:421`), pero un
  `LLM_PROVIDER` vacio hace levantar a `get_provider` (lo prueba `test_proveedor_desconocido_levanta[]`).
  En el stack no importa porque `docker-compose.yml:15` convierte vacio en `stub`
  (`${LLM_PROVIDER:-stub}`); fuera de Compose, un `.env` con `LLM_PROVIDER=` no arrancaria
  `(inferencia: pydantic-settings no ignora valores vacios por default, no verificado)`. Observacion
  para una persona sobre si el criterio deberia aceptar "vacio".
- **Criterio #19**: "se persiste" queda probado como `session.add` del borrador
  (`test_composer.py:373`); el `commit` de `_FakeSession` no se cuenta (`:345-346`).
- **Criterio #46**: "se guarda igual" se afirma sobre `session.draft.source` (`test_composer.py:570`),
  sin contar commits; el conteo `commits == 1` solo esta en el camino que compila (#39,
  `test_composer.py:481`). El codigo no bifurca por `parses` antes del commit
  (`teleflow/composer_service/main.py:268-273`).
- **Criterio #23, alcance del codigo**: la condicion mira el texto ya `strip()`-eado y el filtro usa
  `l.strip().startswith("```")` (`teleflow/composer_service/main.py:86-89`), asi que tambien elimina
  lineas con backticks indentados. El criterio dice "lineas que empiezan con"; no lo contradice, pero
  es mas amplio.
- **Criterio #29, hueco adyacente**: si el parser responde `200` con JSON valido que no es objeto
  (p.ej. una lista), `data.get("valid")` levanta `AttributeError` fuera del `try`
  (`teleflow/composer_service/main.py:131-133`), que no es ni `parses: None` ni un bug "nuestro"
  `(inferencia: lectura de codigo, no ejecutado)`. Ningun criterio lo pide.
- **Criterio #51**: `Settings().compose_timeout` (`test_composer.py:637`) lee el `.env` del directorio
  de trabajo (`teleflow/common/config.py:8`); un `COMPOSE_TIMEOUT` local cambia lo que mide el test
  `(inferencia)`.
