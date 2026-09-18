---
project: copp-ia
date: 2026-09-17
status: accepted
---

# El producto se llama Coppia y la base TeleFlow no se renombra

## Context

Provenance: `copp-ia@docs/coppia-como-nombre@e3bf250`.

El producto se llama **Coppia**: **C**lientes, **O**fertas y **P**roductos con **IA**.

No es un nombre nuevo, es el que estaba y nadie había escrito. El repo remoto es
`github.com/abelvisiUNIR/copp-ia`, el directorio de trabajo es `COPP-IA`, y **los 22 ADRs de este
vault —contando este— llevan `project: copp-ia` en el frontmatter, igual que el roadmap, el
backlog y los conceptos**. Viene del primero, `2026-06-30-adr-001-lark-lalr.md`, cuyo provenance
es `copp-ia@main@6046648`. Lo que nunca se escribió es qué significa la sigla ni cómo se
relaciona con "TeleFlow", que es el nombre que aparece en el código y en toda la documentación
formal: `AGENTS.md` abría con "copp-ia · TeleFlow Platform" sin explicar la yuxtaposición.

La pregunta práctica que esto dejaba abierta no es de marca sino operativa: cuando alguien
escribe algo nuevo mañana, ¿qué nombre le pone? Y la que viene detrás: ¿hay que renombrar lo que
ya existe?

Renombrar no es cosmético, porque el nombre está incrustado en identificadores que consumen
máquinas ya instaladas. Lo que hay hoy, verificado:

**19 métricas Prometheus distintas con prefijo `teleflow_`**, definidas en siete archivos: 6 de
negocio en `teleflow/executor_service/business_metrics.py:51,69,73,78,94,98`, 4 del gateway en
`teleflow/gateway/main.py:110,169,262,266`, 2 del motor en
`teleflow/executor_service/engine.py:45,48`, 2 de HTTP en `teleflow/common/observability.py:15,20`,
2 de dominio en `teleflow/executor_service/domain.py:27,32`, 2 de eventos en
`teleflow/executor_service/events.py:26,31` y 1 de entidades en
`teleflow/executor_service/entities.py:34`.

**Esas métricas tienen consumidores declarados en el repo**, y ahí está el punto:
- `helm/teleflow/alerts/alerts.yml` referencia dos por nombre
  (`teleflow_business_metrics_last_success_timestamp_seconds` en la línea 49 y
  `teleflow_business_metrics_refresh_failures_total` en la 59). Esas reglas son **una sola
  fuente** que consumen la imagen de Prometheus del compose y el `PrometheusRule` opt-in del
  chart.
- `helm/teleflow/dashboards/teleflow-negocio.json` usa 5 métricas distintas en 11 líneas, y
  `teleflow-overview.json` usa 4 en 5 líneas.

**Otros identificadores de runtime:**
- Cola RabbitMQ `teleflow.rules.v2` (`teleflow/common/config.py:82`), ya migrada desde `v1` para
  pasar a quorum queues.
- Claves Redis `teleflow:signal:` (`teleflow/executor_service/engine.py:51`) y
  `teleflow:keys:revocadas` (`teleflow/gateway/main.py:259`).
- Header de autenticación `X-TeleFlow-API-Key`, declarado como security scheme en
  `teleflow/gateway/main.py:75`, leído en la 152, y emitido por el composer en
  `teleflow/composer_service/main.py:176`.
- Variables de entorno `TELEFLOW_API_KEY` y `TELEFLOW_API_KEY_SCOPES` (`.env.example:4,9`).

Y **143 ocurrencias de `teleflow` en los `.py` del paquete**, que son el nombre del paquete y sus
imports.

## Decision

**El producto se llama Coppia. Lo que ya existe no se renombra. Lo que se construya de ahora en
más se nombra Coppia, y la compatibilidad con la base TeleFlow es un criterio de aceptación.**

En concreto:

1. **No se renombra nada de lo existente**: ni el paquete `teleflow/`, ni el CLI `tflow`, ni la
   extensión `.tflow`, ni las 19 métricas, ni la cola, ni las claves de Redis, ni el header, ni
   las env vars, ni el chart, ni los servicios del compose. Un identificador cambia solo si hay
   una razón funcional propia —no estética—, con su ADR y su migración.
2. **Lo nuevo se nombra Coppia**: specs y ADRs nuevos, servicios nuevos, métricas nuevas
   (`coppia_*`), colas nuevas (`coppia.*`), repos nuevos.
3. **Regla de desempate**: si el nombre lo lee una **máquina ya instalada** (métrica, cola, clave
   de Redis, header, env var, tabla), se respeta el existente. Si lo lee una **persona** (doc,
   spec, card de Jira, nombre de un servicio nuevo), se usa Coppia.
4. **La compatibilidad es requisito, no cortesía**: un `.tflow` que validaba y ejecutaba antes
   tiene que seguir validando y ejecutando igual. El DSL, el contrato del gateway y el esquema de
   la base no rompen.
5. **La documentación previa no se reescribe.** Los ADRs, las notas de este vault y los `.typ`
   dicen TeleFlow porque así se llamaba cuando se escribieron.

La regla queda en `AGENTS.md`, que es la fuente única que leen todos los agentes.

## Rationale

**Lo que compra renombrar es coherencia de marca en la superficie. Eso ya se consigue escribiendo
Coppia en la documentación, que es donde una persona lee el nombre.** Lo que cuesta es concreto y
está listado arriba: 19 métricas con dos dashboards y dos reglas de alerta que las nombran, una
cola declarada, dos claves de Redis, un header que es el mecanismo de auth de todas las
integraciones, y dos env vars que están en el `.env` de cada instalación.

Tres de esos costos no son "buscar y reemplazar":

- **Una cola no se rebautiza desde afuera.** El tipo y el nombre los fija quien declara, que es
  el código; renombrar obliga a una migración como la que ya se hizo de `teleflow.rules.v1` a
  `v2`. Esa migración existió porque compraba quorum queues y HA. Un rename no compra nada
  equivalente.
- **El header es el contrato de auth de cada integración del organismo.** Cambiarlo rompe a todo
  consumidor externo a la vez, y el organismo no tiene por qué desplegar en sincronía con
  nosotros.
- **Las métricas rompen hacia atrás en los datos, no solo en el código.** Una serie renombrada
  empieza de cero: los paneles pierden la historia y las alertas basadas en ventanas quedan
  ciegas justo durante la transición. Eso es exactamente el patrón de
  [[fallas-silenciosas]]: el sistema sigue "arriba" y el detector deja de ver.

Hay además un argumento de método. El repo ya decidió dos veces que **el registro histórico no se
reescribe**: los `provenance: copp-ia@devyos@<sha>` se conservaron al retirar la rama `devyos`
(PR #13), por la misma razón por la que aquí se conserva TeleFlow en la documentación previa.
Reescribir la historia para que parezca que siempre se llamó Coppia sería falsear el registro, y
el vault tiene "nada inventado" como primera convención (`wiki/README.md:45`).

**Sobre la sigla**: Clientes, Ofertas y Productos nombra el **dominio de negocio** al que apunta
el producto, no tipos que hoy estén en el lenguaje. El DSL no tiene entidades predefinidas: la
gramática declara `entity_block: "entity" STRING "{" entity_item* "}"`
(`teleflow/dsl/teleflow.lark:20`), y el nombre lo elige quien escribe el flow —los ejemplos
declaran `"nino"` y `"curso"` (`examples/ceibal.tflow:7,47`)—. La correspondencia con los 6
templates TMForum que el roadmap tiene en Fase F es **una dirección, no una implementación**
`(inferencia)`.

## Consequences

- Alguien que entra al repo ve `teleflow/` y lee Coppia en la documentación. La yuxtaposición
  sigue existiendo, pero ahora **está explicada** en `AGENTS.md` y acá, que es lo que faltaba.
- El repo queda con dos nombres conviviendo por tiempo indefinido. Es el costo aceptado: se paga
  en claridad de lectura una sola vez, contra pagar en migraciones y roturas cada vez.
- Un servicio nuevo llamado `coppia-*` va a emitir métricas `coppia_*` junto a las `teleflow_*`
  del resto. Los dashboards van a mezclar prefijos. **Es intencional** y marca la frontera entre
  lo construido antes y después de esta decisión.
- **Límite consciente:** si algún día hay una razón funcional para renombrar (por ejemplo, un
  cambio mayor de contrato que ya obligue a migrar a los consumidores), este ADR no lo impide.
  Lo que prohíbe es renombrar *sin* esa razón.

## Alternatives

**Rename total, ahora.** Descartada. El alcance verificado es: 143 ocurrencias en los `.py` del
paquete, 19 métricas, 2 dashboards, 2 reglas de alerta, 1 cola con migración, 2 claves de Redis,
1 header de auth, 2 env vars, el chart completo y los servicios del compose. Y el alcance en
código es la parte fácil: la parte cara es que toda instalación existente tiene que reconfigurar
su `.env`, sus integraciones y su Prometheus, coordinado. No hay ningún beneficio funcional del
otro lado de ese trabajo.

**Rename parcial: solo lo visible (paquete, CLI, extensión), dejando los identificadores de
runtime.** Descartada por peor que las dos puntas. Deja el sistema mitad y mitad sin una regla que
explique dónde está el corte, que es justo el problema que este ADR viene a resolver. Además
rompe los imports de todo el código y la extensión de los flows ya escritos —o sea, paga el costo
de romper sin comprar la coherencia—.

**No decidir nada y dejar que cada quien elija.** Descartada: es el estado actual, y es el que
generó la pregunta.

## Sources

- `teleflow/executor_service/business_metrics.py:51,69,73,78,94,98` — métricas de negocio.
- `teleflow/executor_service/engine.py:45,48,51` — métricas del motor y prefijo de señales en Redis.
- `teleflow/common/observability.py:15,20` — métricas HTTP comunes.
- `teleflow/executor_service/domain.py:27,32` · `events.py:26,31` · `entities.py:34` — métricas de
  dominio, eventos y entidades.
- `teleflow/gateway/main.py:75,110,152,169,259,262,266` — security scheme, header, métricas y
  clave de revocaciones.
- `teleflow/composer_service/main.py:176` — el composer emite el header hacia el gateway.
- `teleflow/common/config.py:82` — `rules_queue: str = "teleflow.rules.v2"`.
- `teleflow/dsl/teleflow.lark:20` — `entity_block`, el nombre de la entidad es un `STRING` libre.
- `examples/ceibal.tflow:7,47` — entidades `"nino"` y `"curso"`.
- `.env.example:4,9` — `TELEFLOW_API_KEY`, `TELEFLOW_API_KEY_SCOPES`.
- `helm/teleflow/alerts/alerts.yml:49,59` — las dos métricas que las reglas nombran.
- `helm/teleflow/dashboards/teleflow-negocio.json`, `teleflow-overview.json` — 5 y 4 métricas.
- `wiki/README.md:45` — "nada inventado".
- [[fallas-silenciosas]] — el patrón del detector que deja de ver sin que el sistema se caiga.
- [[roadmap]] — Fase F, los 6 templates TMForum.
