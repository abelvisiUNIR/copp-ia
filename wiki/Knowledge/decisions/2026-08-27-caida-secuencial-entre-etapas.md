---
project: copp-ia
date: 2026-08-27
status: accepted
---

# Qué pasa cuando termina una etapa: la caída secuencial y las ramas que se derraman

## Context

Provenance: `copp-ia@devyos@abd828a`.

Cuando una etapa termina, el motor avanza a **la siguiente del archivo**, salvo que sea una
etapa `decision`, que elige destino. Está en dos lugares que dicen lo mismo:
`build_stage_dag()` agrega la arista `stage[i] -> stage[i+1]` para toda etapa que no sea
decisión (`executor_service/engine.py:69`), y el intérprete hace `cursor["stage"] += 1`
(`engine.py:491`).

La consecuencia es que **las ramas de una decisión no están aisladas**. Con este proceso:

```
stage "decidir" { mode: decision  when ... -> stage.ok  else -> stage.mal }
stage "ok"      { mode: sequential steps [step.avisar_ok] }
stage "mal"     { mode: sequential steps [step.avisar_mal] }
```

la rama `ok` corre, termina, y **sigue de largo hacia `mal`**: se ejecutan las dos. Para que
haga lo que aparenta hay que cerrar la primera rama con una etapa terminal:

```
stage "fin" { mode: decision steps [] else -> stage.end }
```

**Todos los ejemplos que tienen decisiones repiten ese pegote**: `venta_internet_hogar.tflow`,
`reclamo_corte.tflow` y el ejemplo de referencia que el composer le muestra al modelo
(`composer_service/providers.py`). `ceibal.tflow` no lo tiene porque no declara ninguna etapa
`decision` — no es un contraejemplo, es un archivo al que el problema no le aplica. Cuando cada
ejemplo que usa una construcción necesita la misma línea extra para que haga lo que aparenta,
la línea es una pista sobre el lenguaje.

Evidencia acumulada en un solo día (2026-08-27), recorriendo el producto de punta a punta:

- **El modelo lo cometió dos veces**, en flows independientes generados a partir de
  descripciones distintas.
- **Dos revisores humanos no lo vieron.** El dueño del proyecto aprobó y desplegó uno de esos
  flows; quien lo acompañaba había leído ese archivo varias veces esa tarde. El defecto quedó
  **latente en producción local** hasta que un chequeo nuevo lo encontró.
- **Cada bloque, leído por separado, está bien.** No hay nada mal escrito: el error vive en el
  espacio entre dos bloques correctos.
- El flow afectado, al firmarse la aprobación, iba a mandar el correo de aprobación, después el
  de rechazo, y después el aviso a RRHH de que nadie había respondido. Tres mensajes
  contradictorios por una licencia aprobada.

El 2026-08-27 se agregó a `dsl/validator.py` un chequeo que detecta el derrame y lo reporta
como error. **Esta decisión es sobre si además conviene cambiar el lenguaje**, porque detectar
un defecto que el lenguaje invita a cometer es tratar el síntoma.

Dos hechos que condicionan cualquier cambio:

- **No existe un marcador de versión del lenguaje.** Nada en el `.tflow`, en el AST ni en el
  registro dice bajo qué semántica se escribió un flow.
- **El registro congela el AST, no su interpretación.** `flow_definitions` guarda `source` y
  `ast` (`common/models.py:35-36`), pero cómo el motor camina ese AST lo decide el código del
  executor. Cambiar la regla de avance **cambia el comportamiento de todos los flows ya
  registrados**, incluidos los que nadie va a volver a mirar.

## Decision

**Opción D: las ramas de una misma decisión no se derraman una en otra.**

Al terminar un stage, el proceso cae en el siguiente **salvo** que ese siguiente sea otra rama
de la decisión de la que venimos; en ese caso la rama terminó y con ella el proceso. La regla es
acotada a propósito: un stage común sigue cayendo en el de al lado, y una rama de varios stages
sigue encadenada hasta toparse con su hermana.

Vive en `siguiente_stage()` (`executor_service/engine.py`), una función pura, y el cursor de la
instancia recuerda de qué decisión viene con `_cursor["rama"]`. `build_stage_dag()` aplica la
misma regla para que el grafo diga lo mismo que el intérprete.

**El pegote deja de ser necesario**: un proceso con dos ramas y sin `stage "fin"` ahora valida y
ejecuta correctamente. Verificado contra el stack: eligiendo una rama corre un solo paso, y
eligiendo la otra corre el otro.

**Se hace ahora porque no hay ninguna instalación productiva**
([[2026-08-18-senal-de-escalado-del-executor]] lo deja escrito). Los únicos flows registrados son
de prueba y descartables. Es la ventana más barata que va a existir para cambiar la semántica del
lenguaje, y se cierra sola: el día que haya un primer organismo, esto pasa de ser un cambio de
tarde a una migración negociada.

## Rationale

El principio que ordena las alternativas: **el caso peligroso tiene que ser el que pide
sintaxis explícita**. Hoy es al revés — terminar una rama, que es lo que casi siempre se
quiere, exige tres líneas de pegote; derramarse sobre la rama de al lado, que casi nunca se
quiere, es el default silencioso.

**Por qué D y no B, después de haber recomendado B.** Este ADR se escribió recomendando la
opción B —que el destino de una rama termine el proceso—. Al ir a implementarla apareció que
**B no cierra**: si la rama termina al completarse su stage, una rama no puede tener más de un
stage, y la salida que el propio ADR proponía ("quien quiera continuar lo dice con un
`else -> stage.X`") tampoco sirve, porque ese stage de continuación está más abajo y ya no se
alcanza. B obligaría a que toda rama fuera de un solo stage.

Y el motivo por el que D se había descartado —"es contextual, difícil de predecir leyendo el
archivo"— **la evidencia lo contradice**. El comportamiento de D es exactamente el que
asumieron el modelo (dos veces), el dueño del proyecto al revisar y aprobar, y quien lo
acompañaba leyendo esos archivos toda la tarde. Cuando tres lectores independientes leen un
proceso y los tres concluyen lo que D hace, D no es la regla sorprendente: es la que ya está en
la cabeza de todos. La sorprendente es la que estaba implementada.

**Sobre la compatibilidad.** El argumento en contra es serio en general: la semántica de
ejecución de un motor de procesos es lo último que se debería poder cambiar por debajo de flows
ya desplegados, y un organismo que instaló hace seis meses no puede descubrir que sus
expedientes se comportan distinto porque el proveedor cambió de opinión sobre un default.

Pero hoy **no hay ningún flow desplegado fuera de desarrollo**, así que ese costo es cero y solo
puede subir. Bloquear el cambio detrás del marcador de versión (opción E) sería pagar el precio
de la compatibilidad sin tener con quién ser compatible. E sigue siendo correcta y queda como
deuda anotada, no como condición previa.

## Consequences

Ya aplicadas:

- **El chequeo `_check_derrame_entre_ramas` se retiró del validador**, junto con sus tests. Bajo
  la semántica nueva el derrame no ocurre, así que marcarlo sería un falso positivo — y un
  validador con falsos positivos enseña a ignorarlo. Había entrado ese mismo día: tratar el
  síntoma sirvió para descubrir la enfermedad y se descarta al curarla. Los tres chequeos de
  firmas del mismo commit siguen vigentes.
- **La regla se extrajo a `siguiente_stage()`**, una función pura, en vez de quedar como lógica
  dentro del intérprete. Adentro necesitaba base de datos para probarse, y la semántica del
  lenguaje tiene que ser verificable sin levantar nada.
- **El cursor de la instancia gana `_cursor["rama"]`**, la decisión de la que viene. Es un campo
  nuevo en un JSON, así que las instancias en vuelo lo leen como ausente y se comportan como
  antes hasta la próxima decisión.

Pendientes, anotadas y sin fecha:

- **El pegote `stage "fin"` quedó innecesario** en `venta_internet_hogar.tflow`,
  `reclamo_corte.tflow` y el ejemplo de referencia del prompt del composer. No molesta —esos
  stages siguen ejecutándose y terminando el proceso—, pero el prompt le sigue enseñando al
  modelo a escribir una línea que ya no hace falta. Limpiarlo simplifica lo que tiene que
  acertar.
- **La documentación de arquitectura describe el modelo de etapas** y no menciona esta regla.
- **Opción E, el marcador de versión del lenguaje.** Sigue siendo correcta y ahora es deuda
  explícita: el próximo cambio de semántica ya no va a encontrar la ventana abierta.

## Alternatives

**A. No cambiar el lenguaje; quedarse con la detección.** Es el estado actual desde hoy. Cuesta
cero y no rompe nada. Deja el pegote como idioma permanente y acepta que cada flow nuevo nazca
con la oportunidad de equivocarse, atajada por un chequeo. Es la opción segura y la que hay que
batir.

**B. El destino de una rama termina el proceso por defecto** *(recomendada)*. Al terminar la
última etapa alcanzada desde una rama, el proceso completa en vez de caer en la siguiente.
Quien quiera continuar lo dice explícitamente con una decisión de un solo destino
(`else -> stage.X`), que es la misma cantidad de pegote que hoy — pero movida al caso raro.
Compatible con el comportamiento **observable** de los ejemplos del repositorio que usan
decisiones: sus etapas `fin` dejarían de ejecutarse y ninguna hace nada más que terminar.

**C. Eliminar la caída secuencial en todas las etapas.** Cada etapa declara su sucesora. Es lo
más explícito y lo más verboso: un proceso lineal de cinco etapas pasa a necesitar cuatro
declaraciones de continuidad que hoy no escribe nadie. Descartable salvo que aparezca otro
motivo, porque encarece el caso mayoritario para arreglar el minoritario.

**D. Una rama termina cuando la etapa siguiente es otra rama de la misma decisión.** Arregla
exactamente el defecto observado y no toca ningún otro caso, así que es la más compatible.
Pero hace que el comportamiento de una etapa dependa de una propiedad **no local** —quién la
referencia desde arriba—, y eso es difícil de explicar y de predecir leyendo el archivo. Un
lenguaje declarativo que hace magia contextual es peor que uno con un default incómodo.

**E. Marcador de versión del lenguaje en el `.tflow` y en el registro.** No es alternativa a las
anteriores: es **condición previa** de B, C y D. Sin poder decir "este flow se escribió bajo la
semántica v2", cualquier cambio reinterpreta silenciosamente flows que nadie volvió a leer. Con
el marcador, el motor puede ejecutar cada versión bajo sus propias reglas y la migración pasa a
ser una decisión del organismo y no del proveedor.

## Sources

- `teleflow/executor_service/engine.py:60-70` — `build_stage_dag()`, la arista
  `stage[i] -> stage[i+1]` para etapas que no son decisión.
- `teleflow/executor_service/engine.py:478-495` — el avance del cursor: `+= 1` salvo decisión.
- `teleflow/dsl/validator.py` — `_check_derrame_entre_ramas()`, la detección agregada hoy.
- `teleflow/common/models.py:35-36` — el registro guarda `source` y `ast`; la interpretación
  vive en el executor.
- `examples/venta_internet_hogar.tflow`, `examples/reclamo_corte.tflow` — los dos ejemplos con
  decisiones cierran sus ramas con un `stage` decision terminal. `examples/ceibal.tflow` no
  declara ninguna decisión, así que no aplica.
- `teleflow/composer_service/providers.py` — el ejemplo de referencia del prompt repite el mismo
  pegote y lo explica en sus notas.
- Corrida completa del 2026-08-27: dos flows generados con el defecto, uno desplegado con el
  defecto latente y detectado recién por el chequeo nuevo.
