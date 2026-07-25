---
project: copp-ia
type: concept
provenance: copp-ia@devyos@b6c7668
created: 2026-07-24
updated: 2026-07-25
tags: [concepto, calidad, resiliencia, observabilidad, patron]
---

# Fallas silenciosas — el patrón que más veces apareció en este proyecto

> Provenance: `copp-ia@devyos@b6c7668`. Sintetizado de siete work-streams distintos
> (`except-swallow-audit`, `limpieza-dx-openapi`, `observabilidad-negocio`,
> `composer-llm-hardening`, `auditoria-persistida`, `registry-cobertura`, `idempotencia-execute`) que encontraron el
> mismo problema con caras distintas.

## Qué es
Un mecanismo que **parece** estar protegiendo algo y no lo está, y que cuando falla **no
produce ninguna señal**: ni excepción, ni test rojo, ni panel en rojo. El sistema sigue
respondiendo "bien". La única forma de enterarse es ir a mirar el resultado real.

No es lo mismo que un bug: un bug rompe algo y se nota. Esto **degrada una garantía** sin
romper nada visible, así que sobrevive indefinidamente. Los casos de abajo llevaban semanas o
meses en el repo antes de encontrarse, y ninguno se encontró por un test.

## Los casos (verificados, no hipotéticos)

| # | Dónde | Qué parecía | Qué pasaba | Fix |
|---|---|---|---|---|
| 1 | `rules.py`, `entities.py`, `view360.py`, `domain.py` | `except Exception` que loguea y sigue = manejo de errores | El evento se ACKeaba igual → la DLQ recién construida nunca recibía nada; un invariante con typo nunca se aplicaba (sin un solo log): un organismo podía correr meses creyendo que validaba | `ef7af86` (`except-swallow-audit`) |
| 2 | `gateway/main.py` | `operation_id` explícito en todas las rutas = contrato estable | `api_route(methods=[...])` con varios métodos hacía que todas las operaciones heredaran el **mismo** id; FastAPI avisa por `UserWarning` y **no falla**, así que el contrato roto se exportaba igual | `97698fe` (`limpieza-dx-openapi`) |
| 3 | `observability/grafana.Dockerfile` | dashboards versionados en el repo = dashboards en Grafana | Los dashboards se copiaban a `/var/lib/grafana`, donde monta el volumen `grafana-data`; Docker copia la imagen al volumen **solo cuando lo crea vacío**, así que en toda instalación existente el volumen viejo tapaba la imagen nueva. El dashboard simplemente no aparecía | `eacc05d` (`observabilidad-negocio`) |
| 4 | `composer_service/providers.py` | `LLM_PROVIDER=anthropic` = borradores generados por un modelo | Sin credencial, `get_provider` logueaba un `warning` y devolvía el `stub`: `/compose` respondía **201** y el analista recibía un esqueleto con `TODO:` creyendo que lo escribió el modelo. Peor, el log registraba el proveedor *pedido*, así que **la única traza decía lo contrario de lo que pasó**. Un typo en la variable caía al mismo lugar sin ni siquiera el warning | `fa479cb` (`composer-llm-hardening`) |
| 5 | `composer_service/providers.py` | HTTP 200 = respuesta utilizable | Un rechazo por políticas del modelo llega con **200**, `stop_reason: refusal` y `content: []`; una respuesta cortada por límite de tokens llega con **200** y un `.tflow` a la mitad. La primera reventaba con un `IndexError` reportado como "error del proveedor"; la segunda se guardaba como borrador | `5d89f94` (`composer-llm-hardening`) |
| 6 | `gateway/main.py` | un middleware que registra al final = registra siempre | El 500 lo arma un middleware de **Starlette** que envuelve a los de la app: una excepción no atrapada salta por encima del middleware propio, `call_next` propaga y el código que sigue nunca corre. Un deploy que crasheaba a mitad de camino no dejaba registro de auditoría — el intento más interesante de todos | `982f12b` (`auditoria-persistida`) |
| 8 | `gateway/main.py` | mandar `Idempotency-Key` = estar protegido | El proxy arma los headers **desde cero** (correcto: evita colar headers del exterior a los servicios internos), así que el header estándar del cliente no llegaba al executor. El gateway respondía 202 y no había ninguna deduplicación: el cliente creía estar protegido de los reintentos y no lo estaba | `b6c7668` (`idempotencia-execute`) |
| 7 | `registry_service/main.py` | `latest` apunta a la versión mayor | `_semver_key` quitaba los no-dígitos de cada chunk, así que el `1` de `rc1` se sumaba al patch: `1.0.0-rc1` → `(1,0,1)`, **mayor** que `1.0.0`. Registrar un candidato después del estable movía `latest` al candidato y el executor disparaba procesos de negocio con él. El 201 llegaba igual y el pointer apuntaba a algo que existía | `4c7ce34` (`registry-cobertura`) |

## La forma común
En los primeros cuatro, el mecanismo de aviso existía y **no cortaba**:

- un `except` que loguea (o ni eso) y deja seguir,
- un `UserWarning` que se imprime y no falla,
- un `COPY` que se ejecuta perfecto sobre un path que otra cosa tapa,
- un `warning` antes de un fallback que devuelve algo plausible.

**Un aviso que no corta no es protección.** Es documentación de que algo salió mal, dirigida a
un lector que no está mirando.

Dos variantes que conviene tener presentes, porque no se buscan igual:

- **El fallback como `return` final de una función es un catch-all** (#4). El `warning` cubría
  el caso previsto —proveedor real sin credencial— pero el `return StubProvider()` del final
  atrapaba además todo lo no enumerado, como un typo en la variable, sin dejar rastro alguno.
  Al revisar un fallback, la pregunta no es "¿avisa?" sino **"¿qué más termina acá?"**.
- **También llegan por el camino del éxito** (#5). Los casos 1-4 son fallos tragados; hay que
  buscarlos en los `except` y los fallbacks. El caso 5 no pasa por ningún manejo de errores:
  es un **200 con contenido inservible**. No hay `except` que lo cubra — hay que mirar el campo
  que dice *cómo terminó* la operación (`stop_reason`, `finish_reason`) y no solo el status.
- **Y el código que registra puede no llegar a correr** (#6). No es que el mecanismo falle: es
  que la excepción **salta por encima** de él. En un stack de middlewares, el manejo de errores
  del framework envuelve a los de la aplicación, así que "esto corre al final de cada request"
  es falso justo para los requests que fallan. Vale para cualquier middleware que registre,
  mida o limpie algo. La única forma de verlo es **probar el camino de excepción explícito**.
- **Una función que nunca falla puede estar corrompiendo un orden** (#7). `_semver_key`
  aceptaba cualquier string y siempre devolvía una tupla: esa tolerancia *era* el bug, porque
  el `1` de `rc1` terminaba sumado al número de patch. No hay excepción que atrapar ni log que
  leer — el resultado es simplemente incorrecto. Cuando una función de parseo o normalización
  no tiene forma de fallar, la pregunta es **qué hace con lo que no entiende**.

Y los primeros tres son peores por *dónde* caen: la DLQ, el contrato de API y el dashboard de backlog
son justamente las cosas que uno mira para saber si el resto anda bien. Cuando la falla
silenciosa está en la capa de garantías, el resultado no es "falta un dato" sino **evidencia
falsa de que todo está bien**: cero eventos en la DLQ, cero backlog pendiente, contrato
publicado sin errores.

## Cómo se encontraron (y qué dice eso del método)
- **Ninguno por un test.** Todos pasaban la suite en verde.
- **#1** por auditoría deliberada: leer los 14 `except Exception` del repo uno por uno, después
  de que un bug caro de `resiliencia-executor` resultara ser de esa familia.
- **#2** al versionar el contrato: el JSON exportado tenía ids repetidos, cosa que solo se ve
  mirando el artefacto, no corriendo la app.
- **#3** al levantar el stack y abrir Grafana. El JSON era válido, los tests pasaban, la imagen
  se construía sin error.
- **#7** sondeando `_semver_key` con casos concretos **antes de escribir el primer test**,
  para saber qué había que fijar. Escribir tests encontró el bug antes que los tests.
- **#6** sondeando la implementación propia antes de darla por buena: preguntarse "¿qué
  caminos NO estoy registrando?" y medir cada uno. Aparecieron tres huecos que la suite en
  verde no mostraba.
- **#4 y #5** leyendo el código para estimar el trabajo, antes de tocar nada. El roadmap decía
  que faltaba "integrar el LLM real"; los proveedores ya estaban implementados y lo que fallaba
  era el comportamiento. **Estimar mirando el código encontró un bug que meses de uso no
  habían encontrado.**

**Regla que sale de acá:** para trabajo sobre garantías (resiliencia, contratos,
observabilidad), *verde en local no es evidencia*. Hay que mirar el artefacto real — la cola,
el `.json` exportado, el dashboard — al menos una vez.

Vale también para las interfaces, con una vuelta de tuerca: en `composer-llm-hardening` el
badge de validación de la `review-ui` se partía en dos líneas y se salía de la tarjeta, **con
el build en verde y el bundle servido correcto**. Todo lo verificable sin ojos estaba bien. Si
el artefacto es visual, mirarlo es parte de la verificación, no una cortesía.

## Qué hacer con esto
Al tocar algo que promete una garantía, preguntarse las cuatro:

1. **Si esto falla, ¿qué se rompe visiblemente?** Si la respuesta es "nada", falta un corte.
2. **¿El aviso corta o solo informa?** Un `warning`, un `log.error` o un `continue` no cortan.
   Si la garantía importa, tiene que fallar: excepción que se propaga, o test que la fija.
3. **¿Estoy verificando el mecanismo o el resultado?** Que el `COPY` esté en el Dockerfile no
   dice que el archivo esté en el contenedor.

4. **¿La cobertura depende de que alguien se acuerde?** Una lista de rutas, de campos o de
   casos a tratar es algo que el próximo cambio olvida actualizar, y el olvido no hace ruido.
   Cuando se puede, engancharlo donde ya está la información: en `auditoria-persistida` el
   registro se enganchó en `auth.require(...)` —que ya sabía qué scope exige cada ruta— así
   una ruta nueva queda cubierta sin que su autor haga nada. Y como complemento, un test que
   **obligue a decidir**: que la clasificación de scopes sea exhaustiva, para que uno nuevo no
   pueda quedar afuera por omisión. Automático no alcanza; hay que cerrar el hueco por defecto.

**Un test vacuo es peor que no tener test**, porque desactiva la sospecha: el ítem queda
marcado como cubierto. En [[review-ui-tests]] hicieron falta **tres intentos** para que el test
de una regresión visual fallara con el defecto puesto — las dos primeras versiones pasaban
igual, y solo midiendo la geometría en el navegador se entendió por qué (el estado no era el
que rompía, el nombre no tenía el largo justo, y la assertion miraba lo que no era: el pill
partido **igual queda dentro** de la tarjeta; lo que lo delata es que el navegador lo renderiza
como dos cajas).

Y al escribir el test que lo fija: **verificarlo con una mutación**. En
`observabilidad-negocio` el test de contrato dashboards↔métricas se comprobó rompiendo a
propósito el nombre de una métrica (tiene que fallar) — porque un test vacuo que no puede
fallar nunca es, él mismo, otra falla silenciosa. Ya había aparecido uno así en
`limpieza-dx-openapi`.

## Qué NO es una falla silenciosa
No todo lo que se pasa por alto entra acá, y forzar el encaje hace perder el patrón. Caso real
(`saneamiento-comando-tipado`, 2026-07-24): `mypy .` no chequeaba **ni un archivo**, pero
fallaba con **exit code 2** — gritaba. Lo que estaba oculto no era el fallo sino la
**divergencia** entre el comando documentado y el que gateaba los merges, que hacía razonable
convivir con el error. Fix distinto, entonces: no un corte donde no lo había, sino un test que
compare las dos fuentes ([[2026-07-24-alcance-mypy]]). Antes de aplicar este patrón, medir:
¿el mecanismo calla, o avisa y el problema es otro?

## Sources
Work-streams `except-swallow-audit` (2026-07-14), `limpieza-dx-openapi` (2026-07-19),
`observabilidad-negocio` (2026-07-24), [[composer-llm-hardening]] (2026-07-25) ·
[[2026-07-25-composer-llm-fallos-explicitos]] ·
[[2026-07-14-clasificacion-errores-integracion]]
(la trampa del "envolver un fallo de red en un error genérico") ·
[[2026-07-24-metricas-de-negocio-gauges]] · [[roadmap]]
