---
project: copp-ia
date: 2026-08-27
status: accepted
---

# Corregir el borrador dentro de la pantalla de revisión

## Context

Provenance de todo lo que se afirma acá sobre el código: `copp-ia@devyos@f70413c`.

La pantalla de revisión (`review-ui/src/App.jsx`) tiene hoy dos botones —**Aprobar y desplegar**
y **Rechazar**— y ninguna forma de tocar el código. Si el borrador tiene un error, el revisor
lo ve, sabe en qué línea está, y no puede hacer nada desde ahí: tiene que salir a una terminal,
recuperar la fuente, arreglarla, correr `tflow validate` y `tflow deploy`.

Esto dejó de ser teórico el 2026-08-27, recorriendo el ciclo completo con el modelo local
(`qwen2.5-coder:7b` vía ollama) para escribir una guía de uso. **De 6 composiciones, 3 no
compilaron.** Los fallos, todos de la misma familia —detalles de sintaxis sobre una estructura
por lo demás correcta—:

- `type: wait`, un tipo de paso que no existe.
- Un `step` definido adentro de un `stage`, donde la gramática espera `mode`.
- `execute: entity.empleado.dias_licencia -= 1`: aritmética sobre campos, que el DSL no tiene.
- Ramas de un `stage` de decisión apuntando a un `step` en vez de a un `stage` — este último
  inducido por una descripción ambigua de quien pedía, no por el modelo.

Dos hallazgos más de la misma corrida, que enmarcan la decisión:

- **Un borrador puede compilar y estar mal.** Uno de los que sí compiló se desplegó y se
  ejecutó: le rechazó la licencia a un empleado sin que ninguna persona la mirara, porque el
  paso que debía ser `human_task` quedó `automated` y la decisión evaluaba una señal que nadie
  emitía. Badge verde, comportamiento inverso al pedido.
- **Describir la estructura mejora mucho el resultado.** Las descripciones en prosa de negocio
  suelta fallaron por sintaxis; al nombrar las piezas del modelo (entidad, regla, proceso con
  etapas, pasos declarados fuera del proceso) la sintaxis salió bien y el único error fue
  semántico. Regenerar cuesta ~4 min y no es reproducible: el servicio no fija `temperature`,
  y la misma descripción produjo flows distintos en corridas sucesivas.

La decisión se aceptó el mismo día, después de que el dueño del proyecto recorriera el ciclo
completo por su cuenta y **quedara frenado en este punto dos veces**: una con un borrador que
inventó `type: wait` y otra con uno que inventó `on_timeout` dentro de un `stage`. En los dos
casos vio el error con línea y columna en la pantalla, y tuvo que salir a una terminal —con
ayuda para extraer la fuente, porque tampoco hay forma de bajarla— para cambiar una línea.

El dato que cambia el análisis: **aprobar un borrador ya despliega código que nunca pasó por
git.** El registro versiona de forma inmutable y la aprobación queda auditada con actor y
comentario, pero no hay repositorio, revisión de pares ni CI en ese camino. El atajo existe hoy,
con o sin editor.

Piezas que ya están construidas y hoy no se aprovechan:

- `POST /parse` está expuesto en el gateway (`teleflow/gateway/main.py:655`) con scope
  `flows:read`, y devuelve los mismos issues con nivel, línea y columna que consume
  `tflow validate` (`teleflow/cli.py:52`).
- La interfaz ya tiene motor de diff: `review-ui/src/diff.js` (`lineDiff`), usado en
  `App.jsx:265`.
- El composer ya acepta `base_source` (`teleflow/composer_service/main.py:66`): concatena el
  flow actual al prompt bajo "Versión actual del flow (modificala según el pedido)". Está
  cableado en `review-ui/src/api.js:29` pero **ningún formulario lo envía**, y el CLI no lo
  expone (`cli.py:119`). Es decir: la iteración sobre un flow existente está implementada y es
  inalcanzable para un usuario.

## Decision

1. **La pantalla de revisión pasa a permitir editar la fuente del borrador antes de aprobar.**
2. **La validación de lo editado se pide siempre al servidor**, vía `POST /parse`. Nunca se
   valida en el navegador: el veredicto tiene que darlo el mismo parser que va a interpretar el
   flow en producción.
3. **Editar invalida el badge.** El estado de validación se calcula al generar; sobre código
   modificado, un badge viejo es una afirmación falsa. Queda neutro hasta revalidar, y aprobar
   sin revalidar pide confirmación explícita, igual que hoy se hace al aprobar algo que no
   compila (`App.jsx:57-64`).
4. **Se conserva la fuente original del modelo y se muestra el diff contra la versión humana.**
   La revisión deja registrado qué propuso el modelo y qué cambió la persona.
5. **Editar exige el scope de despliegue** (`flows:deploy`), no el de composición: modificar el
   código que se va a desplegar es la misma responsabilidad que desplegarlo.
6. **El camino del archivo no se retira.** `tflow validate` sobre un `.tflow` versionado en git
   sigue siendo el camino para un flow que va a vivir años. La edición en pantalla cierra el
   ciclo de un borrador; no reemplaza al repositorio.

Queda **fuera de alcance** de esta decisión, y se registra aparte: exponer `base_source` en la
interfaz y en el CLI.

## Rationale

**Prohibir la edición no protege la trazabilidad, porque el bypass ya existe.** Aprobar
despliega sin git. Negar el editor no agrega una garantía: solo obliga a que la corrección
ocurra fuera de la herramienta, y a que el archivo corregido llegue al repositorio *si alguien
se acuerda*. Es lo peor de las dos opciones —ni la disciplina del repositorio, ni la comodidad
del editor.

**El contexto está en la pantalla, no en la terminal.** Quien puede juzgar si `revisar_solicitud`
debe esperar a un jefe es quien está leyendo el borrador con el pedido original del analista a
la vista. Mandarlo a otra herramienta lo aleja justo cuando tiene el contexto completo.

**Regenerar es la respuesta equivocada para un error de detalle.** Cuesta ~4 min contra menos de
un segundo de `POST /parse`, y al no ser reproducible puede romper lo que ya estaba bien. La
regeneración tiene sentido cuando la *forma* está mal —el modelo entendió otro proceso—, no
cuando falta una palabra.

**Guardar el diff humano contra modelo es lo que vuelve "revisión" a esta pantalla.** Sin eso, la
pantalla decide sobre un texto sin autor distinguible. Con eso, responde una pregunta que un
organismo va a hacer: qué parte de este proceso la escribió una máquina y qué parte una persona.
El motor de diff ya existe, así que el costo es de cableado.

**La validación del lado del servidor no es negociable.** Un validador en el navegador sería una
segunda implementación de la gramática, condenada a divergir de `teleflow/dsl/teleflow.lark`,
que es la fuente de verdad del lenguaje (ADR-001).

## Notas de implementación

Verificado al aceptar la decisión, y reduce el alcance respecto de lo que suponía el borrador
de este ADR:

- **`approve` no hay que tocarlo.** Despliega `draft.source`
  (`teleflow/composer_service/main.py:177`), así que si la edición actualiza esa columna, la
  aprobación funciona sin cambios.
- **La validación ya está factorizada.** `_validate_source()`
  (`teleflow/composer_service/main.py:107`) pega contra `parser-service` y devuelve el mismo
  dict que se guarda en `FlowDraft.validation`, con `parses: None` para "no se pudo verificar".
  El endpoint de edición la reutiliza tal cual.
- **La migración sigue un patrón ya usado en la tabla.** `flow_drafts` tiene columnas nullable
  agregadas después de existir (`provider`, `base_source`), con el criterio escrito en
  `teleflow/common/models.py:188`: "Nullable por los borradores anteriores a la columna". La
  columna con la fuente original del modelo se agrega igual: sin backfill.

## Consequences

- El revisor cierra el ciclo sin salir de la aplicación en el caso más frecuente: la estructura
  sirve y hay que corregir unas líneas.
- Aparece una segunda vía para desplegar código no versionado en git, ahora con edición humana
  incluida. **No es una vía nueva** —aprobar ya lo hacía— pero sí más capaz, y conviene decirlo
  en la documentación de operación en vez de dejarlo implícito.
- La pantalla gana estado: código editado, badge neutro, fuente original guardada. Es
  complejidad real en `App.jsx`, hoy el componente más grande de la interfaz.
- Hay que extender el almacenamiento del borrador para guardar la fuente original además de la
  editada. Es una migración de Alembic sobre `flow_drafts`.
- Los tests de la interfaz tienen que cubrir el caso peligroso: **editar y aprobar sin
  revalidar**. Es la regresión que volvería el badge una mentira.
- No resuelve la corrección estructural: para eso sirve `base_source`, que queda pendiente.

## Alternatives

**Dejarlo como está y documentar el camino del archivo.** Descartado: el argumento a favor era
proteger la trazabilidad de git, y esa protección no existe porque aprobar ya la evita.

**Un editor completo, con autocompletado y resaltado del DSL.** Descartado por
desproporcionado: el caso real observado es corregir entre una y seis líneas. Un editor de
código sería una superficie grande de mantenimiento para un uso marginal.

**Validar en el navegador para que la corrección sea instantánea.** Descartado: duplicaría la
gramática fuera de su fuente de verdad. `POST /parse` responde en menos de un segundo; el
problema nunca fue la latencia.

**Exponer solo `base_source` y no permitir edición manual.** Descartado como sustituto, aceptado
como complemento: pedirle un cambio al modelo cuesta ~4 min y no es reproducible, así que para
un `type: wait` mal escrito es peor que editar. Sirve para cambios de forma, y se decide aparte.

**Permitir editar sin exigir revalidación, confiando en el revisor.** Descartado: el badge es la
única señal automática de la pantalla, y una señal que puede quedar desactualizada silenciosamente
es peor que no tenerla.

## Sources

- Corrida completa del ciclo del 2026-08-27 contra el stack local con `LLM_PROVIDER=ollama`,
  modelo `qwen2.5-coder:7b`: 6 composiciones, 3 sin compilar, 1 compilando con comportamiento
  inverso al pedido.
- `review-ui/src/App.jsx` — pantalla de revisión: botones, confirmación al aprobar algo roto
  (l. 57-64), uso de `lineDiff` (l. 265).
- `review-ui/src/diff.js` — motor de diff existente.
- `review-ui/src/api.js:29` — `compose` acepta `base_source` y ningún formulario lo envía.
- `teleflow/gateway/main.py:655` — `POST /parse`, scope `flows:read`.
- `teleflow/cli.py:52` — `cmd_validate`, consumidor actual de `/parse`.
- `teleflow/composer_service/main.py:66` — uso de `base_source` en el prompt.
- `teleflow/dsl/teleflow.lark` — fuente de verdad del lenguaje (ADR-001).
