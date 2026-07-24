---
project: copp-ia
type: concept
provenance: copp-ia@devyos@1305d99
created: 2026-07-24
updated: 2026-07-24
tags: [concepto, calidad, resiliencia, observabilidad, patron]
---

# Fallas silenciosas — el patrón que más veces apareció en este proyecto

> Provenance: `copp-ia@devyos@1305d99`. Sintetizado de tres work-streams distintos
> (`except-swallow-audit`, `limpieza-dx-openapi`, `observabilidad-negocio`) que encontraron
> el mismo problema con tres caras distintas.

## Qué es
Un mecanismo que **parece** estar protegiendo algo y no lo está, y que cuando falla **no
produce ninguna señal**: ni excepción, ni test rojo, ni panel en rojo. El sistema sigue
respondiendo "bien". La única forma de enterarse es ir a mirar el resultado real.

No es lo mismo que un bug: un bug rompe algo y se nota. Esto **degrada una garantía** sin
romper nada visible, así que sobrevive indefinidamente. Los tres casos de abajo llevaban
semanas o meses en el repo antes de encontrarse, y ninguno se encontró por un test.

## Los tres casos (verificados, no hipotéticos)

| # | Dónde | Qué parecía | Qué pasaba | Fix |
|---|---|---|---|---|
| 1 | `rules.py`, `entities.py`, `view360.py`, `domain.py` | `except Exception` que loguea y sigue = manejo de errores | El evento se ACKeaba igual → la DLQ recién construida nunca recibía nada; un invariante con typo nunca se aplicaba (sin un solo log): un organismo podía correr meses creyendo que validaba | `ef7af86` (`except-swallow-audit`) |
| 2 | `gateway/main.py` | `operation_id` explícito en todas las rutas = contrato estable | `api_route(methods=[...])` con varios métodos hacía que todas las operaciones heredaran el **mismo** id; FastAPI avisa por `UserWarning` y **no falla**, así que el contrato roto se exportaba igual | `97698fe` (`limpieza-dx-openapi`) |
| 3 | `observability/grafana.Dockerfile` | dashboards versionados en el repo = dashboards en Grafana | Los dashboards se copiaban a `/var/lib/grafana`, donde monta el volumen `grafana-data`; Docker copia la imagen al volumen **solo cuando lo crea vacío**, así que en toda instalación existente el volumen viejo tapaba la imagen nueva. El dashboard simplemente no aparecía | `eacc05d` (`observabilidad-negocio`) |

## La forma común
En los tres, el mecanismo de aviso existía y **no cortaba**:

- un `except` que loguea (o ni eso) y deja seguir,
- un `UserWarning` que se imprime y no falla,
- un `COPY` que se ejecuta perfecto sobre un path que otra cosa tapa.

**Un aviso que no corta no es protección.** Es documentación de que algo salió mal, dirigida a
un lector que no está mirando.

Y los tres son peores por *dónde* caen: la DLQ, el contrato de API y el dashboard de backlog
son justamente las cosas que uno mira para saber si el resto anda bien. Cuando la falla
silenciosa está en la capa de garantías, el resultado no es "falta un dato" sino **evidencia
falsa de que todo está bien**: cero eventos en la DLQ, cero backlog pendiente, contrato
publicado sin errores.

## Cómo se encontraron (y qué dice eso del método)
- **Ninguno por un test.** Los tres pasaban toda la suite en verde.
- **#1** por auditoría deliberada: leer los 14 `except Exception` del repo uno por uno, después
  de que un bug caro de `resiliencia-executor` resultara ser de esa familia.
- **#2** al versionar el contrato: el JSON exportado tenía ids repetidos, cosa que solo se ve
  mirando el artefacto, no corriendo la app.
- **#3** al levantar el stack y abrir Grafana. El JSON era válido, los tests pasaban, la imagen
  se construía sin error.

**Regla que sale de acá:** para trabajo sobre garantías (resiliencia, contratos,
observabilidad), *verde en local no es evidencia*. Hay que mirar el artefacto real — la cola,
el `.json` exportado, el dashboard — al menos una vez.

## Qué hacer con esto
Al tocar algo que promete una garantía, preguntarse las tres:

1. **Si esto falla, ¿qué se rompe visiblemente?** Si la respuesta es "nada", falta un corte.
2. **¿El aviso corta o solo informa?** Un `warning`, un `log.error` o un `continue` no cortan.
   Si la garantía importa, tiene que fallar: excepción que se propaga, o test que la fija.
3. **¿Estoy verificando el mecanismo o el resultado?** Que el `COPY` esté en el Dockerfile no
   dice que el archivo esté en el contenedor.

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
`observabilidad-negocio` (2026-07-24) · [[2026-07-14-clasificacion-errores-integracion]]
(la trampa del "envolver un fallo de red en un error genérico") ·
[[2026-07-24-metricas-de-negocio-gauges]] · [[roadmap]]
