---
project: copp-ia
type: concept
provenance: copp-ia@devyos@ae923b6
created: 2026-07-24
updated: 2026-08-08
tags: [concepto, calidad, resiliencia, observabilidad, patron]
---

# Fallas silenciosas — el patrón que más veces apareció en este proyecto

> Provenance: `copp-ia@devyos@3a345f2`. Sintetizado de **quince** work-streams distintos
> (`except-swallow-audit`, `limpieza-dx-openapi`, `observabilidad-negocio`,
> `composer-llm-hardening`, `auditoria-persistida`, `registry-cobertura`,
> `idempotencia-execute`, `review-ui-tests`, `estado-durable`, `fase-e-helm-kind`,
> `alerta-up-metrics-service`, `verificacion-imagenes-pipeline`, `ha-capa-de-datos`,
> `runbooks-y-dr`, `criterio-salida-fase-e`) que
> encontraron el mismo problema con caras distintas.

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
| 9 | `docker-compose.yml` | colas `durable=True` + mensajes `PERSISTENT` = la DLQ sobrevive | El servicio `rabbitmq` no tenía volumen, así que `/var/lib/rabbitmq` vivía en la capa escribible del contenedor: la DLQ sobrevivía a un `restart` y **se vaciaba con `up --build`**, el comando del README. Y las colas reaparecían (las declara la app), así que el operador veía la DLQ en **0** — que se lee como "no hubo fallas". Agregar el volumen **no alcanzó**: el nombre del nodo (`mnesia/rabbit@$HOSTNAME`) dependía del ID del contenedor, así que cada recreación estrenaba un nodo y dejaba el anterior huérfano dentro del volumen | `estado-durable` |
| 8 | `gateway/main.py` | mandar `Idempotency-Key` = estar protegido | El proxy arma los headers **desde cero** (correcto: evita colar headers del exterior a los servicios internos), así que el header estándar del cliente no llegaba al executor. El gateway respondía 202 y no había ninguna deduplicación: el cliente creía estar protegido de los reintentos y no lo estaba | `b6c7668` (`idempotencia-execute`) |
| 10 | `helm/teleflow/Chart.yaml` | un chart versionado = un chart instalable | Las imágenes que pedían los tres subcharts de Bitnami **fueron retiradas de Docker Hub**. `helm dependency update` sigue diciendo éxito —los *charts* siguen publicados— y el fallo aparece recién cuando un pod intenta bajar la imagen: ni el render ni un lint lo ven. **Variante nueva: el artefacto no cambió y dejó de funcionar solo.** Todos los casos anteriores eran código propio ocultando un fallo; este es una dependencia externa que se movió abajo | `23cc2c7` (`fase-e-helm-kind`) |
| 11 | tag de imagen mutable | `helm upgrade` → `deployed` = el código nuevo está corriendo | Con un tag que se reescribe (`latest`, `dev`) más `pullPolicy: IfNotPresent`, el pod spec renderizado es **byte a byte el mismo**: Kubernetes no tiene motivo para rotar los pods y tampoco vuelve a bajar la imagen. Helm reporta éxito porque, desde su punto de vista, el estado declarado ya se cumple. Verificado: `hasattr(..., '_tomar_turno')` → `False` dentro del pod, después de un upgrade "exitoso" | documentado (regla de tag inmutable) |
| 12 | `executor_service/engine.py` | `_recover()` retoma lo que quedó a mitad | Corría en **cada** réplica y nadie reclamaba la instancia: con 3 réplicas, **cada deploy con un expediente en vuelo lo ejecutaba 3 veces**. Medido: 63 requests donde iban 21, y **tres** transiciones `IN_PROGRESS → FAILED` del mismo caso. Con una integración real son tres altas, tres correos. Es el daño que la idempotencia de `/execute` evita **desde afuera**, ocurriendo desde adentro | `f168452` (`fase-e-helm-kind`) |
| 13 | `executor_service/adapters.py` | `${env.LMS_URL}` sin definir = error visible | Se reemplazaba por **cadena vacía**: el deploy pasaba, la validación pasaba, y el fallo aparecía cuando un expediente real llegaba al step, con un `UnsupportedProtocol` que no nombra la variable. Peor en credenciales: un `Bearer ${env.TOKEN}` sin TOKEN mandaba el header **vacío**, y con un servidor permisivo el request salía bien **sin autenticar** | `c42f13f` (`fase-e-helm-kind`) |
| 7 | `registry_service/main.py` | `latest` apunta a la versión mayor | `_semver_key` quitaba los no-dígitos de cada chunk, así que el `1` de `rc1` se sumaba al patch: `1.0.0-rc1` → `(1,0,1)`, **mayor** que `1.0.0`. Registrar un candidato después del estable movía `latest` al candidato y el executor disparaba procesos de negocio con él. El 201 llegaba igual y el pointer apuntaba a algo que existía | `4c7ce34` (`registry-cobertura`) |
| 14 | `executor_service/business_metrics.py` + las alertas que lo cubren | degradación elegante = el servicio aguanta un fallo de métricas | El `_loop` atrapa la excepción del refresh, loguea y sigue — **correcto**, un fallo de métricas no debe bajar el servicio. Y es exactamente lo que produce el silencio: con Postgres inalcanzable el pod queda **vivo**, `/metrics` responde y los gauges conservan el último valor bueno. Un backlog congelado en 10 es indistinguible de uno estable en 10, y `up` vale **1**, así que ninguna alerta de disponibilidad lo ve. Medido: 4 minutos con `up=1` y la alerta de caída en `inactive`. **Y la contramedida repite el patrón una capa más arriba:** una regla de alerta con un nombre de métrica mal escrito pasa `promtool check rules`, aparece en `kubectl get prometheusrule` y **nunca dispara** — la herramienta construida para detectar el silencio se vuelve silenciosa igual | `3524781` + `029135e` (`alerta-up-metrics-service`) |

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
- **Una garantía declarada arriba se puede perder abajo — y en más de una capa** (#9). El
  código de eventos declaraba todo bien (exchanges y colas durables, mensajes persistentes) y
  la DLQ se vaciaba igual porque faltaba el volumen. Puesto el volumen, **seguía perdiéndose**,
  porque el nombre del nodo dependía del ID del contenedor. Cada capa se veía correcta por
  separado: solo medir el resultado final —publicar, recrear, contar— lo mostró. Cuando algo se
  declara durable, la pregunta es **dónde termina el byte**, no qué dice la declaración.
- **El mecanismo correcto puede ser el que produce el silencio** (#14). En los trece casos
  anteriores había algo mal puesto: un `except` que no debía tragar, un `COPY` a la ruta
  equivocada, un fallback que mentía. Acá el `except` está **bien** — un fallo de métricas no
  debe bajar un servicio — y justamente por eso el fallo no se nota: sin él el colector moriría
  y `up` lo delataría. Es la contracara de #1, y la contramedida es la opuesta: no sacar el
  `except`, sino **emitir la evidencia de que se está usando** (un timestamp de último éxito, un
  contador de fallos). Cada vez que se decide "esto degrada en vez de caerse", queda pendiente
  publicar la señal de que está degradado; si no, se cambió una caída ruidosa por una mentira
  silenciosa. Vale para todo fallback, cache que sirve datos viejos o reintento que se rinde.
- **La herramienta que detecta el silencio puede ser silenciosa** (#14, segunda mitad). Una
  alerta sobre una métrica mal escrita es sintácticamente válida, se lista, y no dispara nunca:
  desde afuera es idéntica a un sistema sano. Por eso `promtool test rules` y no solo `check
  rules` — la diferencia es probar que **existe** versus probar que **funciona**, el mismo filo
  que separa `helm template` de instalar en un cluster. Regla práctica: cuando se construye un
  detector, hay que romperlo a propósito una vez y ver que grite.
- **Y también puede fallar por ruidoso** (modo gemelo del anterior, 2026-08-08). Un detector que
  reporta un hallazgo cuando en realidad **no pudo mirar** produce alarmas falsas, y con dos o
  tres alcanza para que nadie vuelva a abrir el reporte: el resultado final es el mismo silencio
  que arriba, por el camino opuesto. Apareció construyendo el chequeo de existencia de imágenes:
  "la imagen no está en el registry" y "no pude hablar con el registry" son el mismo exit code
  si uno no los separa, y el segundo caso llega solo —el rate limit anónimo de Docker Hub cortó
  una corrida y devolvió 7 falsos faltantes en potencia—. Por eso el script distingue tres
  desenlaces y los dos rojos dicen cosas distintas. La contracara: que el "no pude verificar"
  **no** cortara sería volver al detector callado. Regla práctica: un detector necesita un
  estado para *no sé*, y ese estado tiene que ser visible sin ser acusatorio.
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

**Pero la mutación no alcanza, y esto costó caro.** La verificación por mutación prueba que el
test **mira el mecanismo**; no prueba que el **escenario del test ocurra en producción**. En
`fase-e-helm-kind` un e2e verificaba exclusión mutua entre dos colectores forzando el
solapamiento temporal con un `sleep` inyectado: pasaba la mutación (quitar el lock lo hacía
fallar) **y pasaba con el bug puesto**, porque en el sistema real los ciclos nunca se solapan.
El arreglo se dio por bueno, se commiteó afirmándolo, y el bug siguió vivo hasta que se midió en
un cluster.

La pregunta que faltaba: **¿esta condición se produce sola afuera, o la estoy construyendo yo?**
Cuando un test necesita fabricar la condición que lo hace fallar —esperas inyectadas,
concurrencia forzada, relojes movidos— hay que sospechar que está probando un escenario que el
sistema no genera. En un solo día aparecieron **tres** tests vacuos de esta familia, y los tres
pasaban por el mismo motivo de fondo: reproducían una versión del escenario que el sistema real
no produce (un gauge compartido dentro de un proceso, cuando la multiplicación ocurre *entre*
procesos; un conteo de instancias en Prometheus, cuando el compose scrapea un target DNS único).

Regla práctica: **el escenario del test tiene que ser el que el sistema produce solo.** Si el bug
se dispara en cada deploy, el test tiene que ser un deploy — no dos hilos sincronizados a mano.

**Y cuando una comprobación local pasa, hay que preguntarse qué la hizo pasar** (caso 15,
`alerta-up-metrics-service`, 2026-07-31). Los catorce casos de la tabla son del sistema; este es
del **método de verificación**, y es la vuelta de tuerca que le faltaba a la regla de arriba. El
paso de `promtool` se movió al job `e2e` razonando que el `up --build` deja la imagen de
Prometheus en el daemon; se verificó local, **dio verde, y estaba verde por la causa equivocada**:
la imagen estaba ahí porque la había traído un `docker run` al principio de la sesión, no porque
el build la dejara. Con BuildKit, `compose build` deja la **base** en su caché de build y no en el
image store (`.github/workflows/ci.yml:66-69`). El entorno tenía la evidencia sin tener el
mecanismo — el equivalente, un nivel más arriba, del caso 3: el `COPY` corría perfecto y el
archivo estaba por otro motivo.

Dos cosas que conviene no suavizar. La primera: costó **tres intentos** meter ese paso al
pipeline, y **ninguno de los dos fallos los detectó quien los escribió** — los agarró el CI. La
segunda: el primer intento era un mal diseño contra el caso **#10** de esta misma página (las
imágenes de Bitnami retiradas de Docker Hub, "Docker Hub no es una dependencia confiable"),
escrito por la misma persona horas antes. **Saberlo no alcanzó**, lo cual dice que el valor de
esta página no está en haberla leído sino en usarla como checklist en el momento de decidir.

Lo que sí funcionó fue **`--pull=never`**: convirtió el supuesto equivocado en un fallo ruidoso
en lugar de un pull silencioso que anda de a ratos. Es la misma forma del fix de siempre —
cuando un paso puede resolverse por dos caminos y solo uno es el que se está afirmando,
prohibir el otro es lo que hace hablar al mecanismo.

**Y un grado más: una verificación que no se ejecuta produce el mismo output que una que pasa**
(caso 16, `ha-capa-de-datos`, 2026-08-08). El caso 15 es una comprobación que pasa por la causa
equivocada; este es una que **no ocurrió**, y desde afuera se lee igual.

Probando el failover del cluster de RabbitMQ hacía falta un control: matar el nodo que aloja una
cola **clásica** y ver que sí pierde el mensaje, porque sin eso "la quorum sobrevivió" no
distingue entre *el quorum funciona* y *el golpe no fue lo bastante fuerte*. El control se
escribió sacando el nodo de la columna `leader`, que para colas clásicas **viene vacía**: el
`grep` no encontró nada, el `delete pod ""` falló, y el "después" salió idéntico al "antes"
**por no haber matado nada**. Leído rápido —dos tablas iguales, el mensaje ahí— se parecía
bastante a un control que corrió bien.

Es la forma más barata de fabricarse evidencia falsa, y no necesita ningún mecanismo roto: basta
que el paso destructivo falle en silencio. Aparece en todo test que primero **busca** el objetivo
y después lo rompe (un pod, un archivo, un registro, una fila): si la búsqueda devuelve vacío, lo
que sigue no hace nada y el sistema queda intacto, que es exactamente lo que el test quería ver
para el caso bueno.

Regla práctica: **verificar el paso intermedio, no solo el resultado.** La pregunta no es "¿el
mensaje sobrevivió?" sino "¿a quién maté?". Y cuando un paso destructivo toma un objetivo
calculado, ese objetivo tiene que estar impreso o afirmado antes de usarlo — un `delete` con
argumento vacío debería cortar, no seguir.

## Y el que no tiene mecanismo ninguno: la documentación

**Caso 17** (`criterio-salida-fase-e`, 2026-08-18), y es de otra clase que los dos anteriores. El
15 es una comprobación que pasa por la causa equivocada; el 16, una que no se ejecutó. Este es un
artefacto que **nadie ejecuta nunca**, y por eso no tiene forma de avisar que se rompió.

Un `.md` o un `.typ` no tiene tests, no tiene tipos, no tiene CI. Cuando el código se mueve
debajo, la doc no falla: **sigue diciendo exactamente lo mismo, con la misma confianza.** No hay
`except` que trague nada porque no hay mecanismo que tragar — es el grado cero del silencio, y
por eso conviene tratarla como un artefacto de producción y no como prosa.

La evidencia son dos episodios, y el segundo fue el que convirtió la sospecha en patrón:

- **2026-08-08 (`runbooks-y-dr`).** Escribir el runbook **corriendo cada comando** encontró que
  citaba una tabla que no existe (`flow_versions`; es `flow_definitions`). Habría fallado en el
  único momento en que un runbook importa: justo después de un desastre.
- **2026-08-18 (`criterio-salida-fase-e`).** Escribir el checklist de instalación
  **ejecutándolo** encontró cuatro cosas de una sola pasada. El comando de producción de
  `docs/teleflow-deployment.typ` fallaba **en el primer intento** (`-f values-production.yaml`,
  y el archivo está en `helm/teleflow/`). `values-production.yaml` no se podía instalar tal como
  venía: exige TLS y traía `tls: []` con un comentario diciendo que el TLS seguía pendiente. Su
  lista de "PENDIENTE" declaraba pendientes el HA de la capa de datos y la observabilidad, hechos
  **diez días antes**. Y nada documentaba cómo construir las imágenes que el chart da por
  existentes.

**Lo que hay que no suavizar:** los cuatro estaban a la vista de cualquiera que abriera esos
archivos, y **ninguno se vio en semanas de trabajo sobre esos mismos archivos**. Aparecieron
todos en los primeros diez minutos de correrlos. Leer la doc no la verifica — leerla es
justamente lo que veníamos haciendo.

Dos vueltas de tuerca que valen aparte. La primera: en el episodio del checklist, el **README**
—la fuente *menos* autorizada según el orden de verdad del repo (código > `.typ` > `.md`)— tenía
el comando bien y el `.typ` lo tenía mal. La jerarquía de confianza ordena qué creer ante un
conflicto, pero **no predice cuál envejeció**; eso depende de cuál se tocó más recientemente. La
segunda: el chart **ya cortaba** el install si no se declaraba ninguna credencial, y aun así
declarar `existingSecret` sin crearlo daba `Install complete` con los 18 pods en
`CreateContainerConfigError`. La guarda cubría el caso de quien **lee** la documentación, no el
de quien **copia el ejemplo** — y el segundo es el frecuente.

Regla práctica: **la parte determinista de la doc se gatea; el resto se ejecuta cada tanto.** Lo
verificable sin red ni cluster —que los archivos que nombra existan, que las rutas de un `-f`
resuelvan desde donde se copia el comando, que las claves de `--set` estén en `values.yaml`—
vive en `tests/test_doc_contract.py` y corta merges. Lo demás (que la prosa describa bien el
comportamiento) no lo prueba ningún grep, y se paga ejecutando el checklist en la próxima
instalación real. Es el mismo reparto que el verificador de imágenes del caso #10: lo estático
gatea, lo que depende de un tercero va aparte.

Y un detalle del gate que es el mismo patrón mordiéndose la cola: al escribirlo dio **dos falsos
positivos** —tomó por ruta el usuario/password de RabbitMQ del README, y por clave inválida un
`--set` sobre un mapa que el chart deja vacío a propósito para el organismo—. Se corrigieron en
vez de agregarles excepciones puntuales, porque **un detector que grita de más enseña a
ignorarlo**, que es la forma que ya tenía documentada este repo (el modo gemelo del caso #10: el
detector que falla por ruidoso).

## Un pariente cercano, que no es lo mismo
El supuesto **"esto corre en un solo proceso"** apareció cuatro veces en este repo y comparte el
síntoma —degrada una garantía sin romper nada visible— pero tiene otra raíz: acá el mecanismo de
aviso existe y no corta; allá **no hay ningún mecanismo**, porque nadie decidió que hiciera
falta. Tiene su propia página: [[supuesto-de-proceso-unico]].

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
[[2026-07-24-metricas-de-negocio-gauges]] · work-stream `alerta-up-metrics-service`
(2026-07-31, caso 14: la frescura de los gauges y las alertas que la miran; y caso 15, el
primero sobre el método de verificación y no sobre el sistema) · `.github/workflows/ci.yml`
(el razonamiento del paso de `promtool`, comentado en el pipeline) ·
work-stream `verificacion-imagenes-pipeline` (2026-08-08, el modo gemelo: el detector que falla
por ruidoso) · `.github/workflows/imagenes.yml` · work-stream `ha-capa-de-datos` (2026-08-08,
caso 16: el control que no se ejecutó) · [[2026-08-08-alcance-del-ha-de-la-capa-de-datos]] ·
work-streams [[runbooks-y-dr]] (2026-08-08) y [[criterio-salida-fase-e]] (2026-08-18, caso 17:
la documentación, el artefacto que nadie ejecuta) · `docs/checklist-instalacion.md` ·
`tests/test_doc_contract.py` (la mitad determinista, gateando merges) ·
[[roadmap]]
