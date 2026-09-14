---
name: sync-jira
description: Lee el tasks.md consolidado de una feature en spec/features/ y crea las Cards correspondientes en el Jira de bpfocus via MCP, escribiendo de vuelta los IDs oficiales. Siempre en dry-run con confirmacion explicita antes de crear. Usar cuando una spec queda consolidada, cuando el usuario pide sincronizar tareas con Jira, o al invocar /sync-jira.
allowed-tools: Read, Edit, Grep, Glob, mcp__atlassian__getAccessibleAtlassianResources, mcp__atlassian__discover, mcp__atlassian__executeRead, mcp__atlassian__getJiraIssue, mcp__atlassian__searchJiraIssuesUsingJql
---

<!--
  allowed-tools lista solo lecturas a proposito. createJiraIssue, transitionJiraIssue y
  executeWrite quedan afuera: siguen pidiendo permiso en cada llamada, que es una segunda
  barrera ademas del dry-run.
-->


# Sincronizacion de tareas del repo con Jira

Convierte las tareas de `spec/features/<CLAVE>-<n>-<slug>/tasks.md` en Cards de Jira y deja el
ID oficial escrito en el archivo, de modo que cada linea del repo sea trazable contra su ticket.

Las reglas de formato de las cards estan en `@.claude/rules/atlassian-standards.md` y son
obligatorias.

## Invariantes

Estas no se negocian ni se saltean "porque es obvio":

1. **Nunca se crea un issue sin confirmacion explicita del usuario en este turno.** El dry-run
   es un paso, no una sugerencia. Un OK dado para otra feature no vale para esta.
2. **Una linea que ya tiene `[CLAVE-N]` esta sincronizada y no se recrea jamas.**
3. **Solo se crean issues en el proyecto que declara el frontmatter.** Sin `jira_project`, se
   frena y se pregunta.
4. **No se commitea ni se pushea.** `wiki/README.md:55`: los commits locales si, el `git push`
   lo hace siempre el owner.
5. **Solo el Jira de bpfocus.** Se usan unicamente las tools `mcp__atlassian__*`, nunca
   `mcp__claude_ai_Atlassian__*` (ese conector esta logueado en otra organizacion). Antes de
   cualquier otra llamada, `getAccessibleAtlassianResources` tiene que listar el cloudId
   `0941e7ed-5a17-4467-8e47-9e0d04b3ca1d`; si no aparece, se para. Toda llamada lleva ese
   `cloudId` explicito.

## Como se llaman las operaciones del MCP

El servidor `atlassian` (`.mcp.json`) expone pocas tools directas y el resto por catalogo.
Nombres verificados contra `discover` el 2026-09-13:

| Para que | Como se llama |
|---|---|
| Confirmar el sitio | `getAccessibleAtlassianResources` (directa) |
| Leer un issue | `getJiraIssue` (directa) |
| Buscar issues | `searchJiraIssuesUsingJql` (directa) |
| Crear una card | `createJiraIssue` (directa) |
| Transicionar | `transitionJiraIssue` (directa) |
| Listar proyectos | `executeRead` con `name: "listJiraProjects"` |
| Tipos de issue del proyecto | `executeRead` con `name: "listJiraProjectIssueTypesMetadata"` |
| Campos de un tipo | `executeRead` con `name: "getJiraIssueTypeMetaWithFields"` |
| Transiciones disponibles | `executeRead` con `name: "listJiraIssueTransitions"` |

En las `execute*`, el `cloudId` va **al mismo nivel que `name` e `inputs`**, nunca adentro de
`inputs`. Si una operacion no aparece con ese nombre, se vuelve a correr `discover` describiendo
el objetivo; no se inventa ni se adivina un nombre.

## Procedimiento

### 1. Resolver la feature

Si el usuario nombro una, usar esa. Si no, buscar con Glob los `spec/features/*/tasks.md` y
quedarse con los que tengan `status: consolidada` y al menos una tarea sin clave. Si hay mas de
uno, listarlos y preguntar cual — no asumir.

Si el `status` es `borrador`, la spec todavia esta iterando: decirlo y parar. Si es
`sincronizada` y no quedan tareas sin clave, informar "0 tareas para sincronizar" y terminar.
Si es `implementada`, es linea base as-built de algo que ya esta en el codigo (carpetas `base-*`):
informar "linea base as-built, no se sincroniza" y parar sin llamar a Jira.

### 2. Validar el frontmatter

Obligatorios: `jira_site`, `jira_project`, `jira_parent`. Si falta alguno, parar y pedirlo.
Adivinar el proyecto destino es la forma mas rapida de ensuciar el backlog de otro equipo.

### 3. Descubrir el esquema real de Jira

No asumir nombres ni ids de issue type: varian por proyecto y por idioma del sitio.

- `executeRead` → `listJiraProjects` (`query: <jira_project>`) → confirmar que el proyecto existe.
- `executeRead` → `listJiraProjectIssueTypesMetadata` (`projectIdOrKey`) → obtener el **id** del
  tipo a usar.
- `executeRead` → `getJiraIssueTypeMetaWithFields` (`projectIdOrKey`, `issueTypeId`,
  `requiredFieldsOnly: true`) → campos requeridos. Si el proyecto exige un campo que la spec no
  tiene, decirlo antes del dry-run, no descubrirlo a mitad de la creacion.
- `getJiraIssue` sobre `jira_parent` → confirmar que existe y que es un padre valido.

Tipo de issue: `Subtarea` solo si `jira_parent` es una Tarea o Historia y el proyecto lo
permite; en el caso normal (padre = Epic) las cards son `Tarea` o `Historia`.

### 4. Detectar duplicados antes de crear

Dos chequeos, porque uno solo no alcanza:

- **Por archivo**: las lineas con `[CLAVE-N]` se saltean.
- **Por Jira**: `searchJiraIssuesUsingJql` con `parent = <jira_parent>` (y, si el proyecto no
  soporta `parent`, por `project` + label `spec-driven`) para traer las cards que ya cuelgan del
  padre. Comparar summaries normalizados (minusculas, sin acentos, sin espacios repetidos).

Este segundo chequeo es el que evita duplicar un backlog entero si alguien revirtio el
`tasks.md` o lo regenero desde cero. Si aparece una coincidencia, tratarla como ya sincronizada
y proponer escribir su clave en el archivo en vez de crear una card nueva.

### 5. Dry-run (obligatorio)

Mostrar una tabla con una fila por card a crear:

| # | Summary | Tipo | Padre | Labels |

Debajo, para la primera card, mostrar la descripcion completa que se va a enviar, para que se
vea el formato real y no solo el titulo. Y listar aparte:

- las tareas que se saltean por ya tener clave,
- las que se saltean por coincidir con una card existente (con su clave),
- cualquier campo requerido del proyecto que haya que completar a mano.

Cerrar con el conteo exacto: "Se crearian N cards en `<PROYECTO>` colgando de `<PADRE>`."

**Parar aca y esperar el OK.** No encadenar la creacion en el mismo turno.

### 6. Crear

Tras el OK, una card por vez con `createJiraIssue`, en el orden del archivo.

Si una falla: registrar el error, **seguir con las demas**, y al final reportar cuales se
crearon y cuales no, con el motivo. Abortar a la mitad sin decirlo deja el `tasks.md` mintiendo
sobre el estado real de Jira, que es peor que el fallo original.

### 7. Escribir de vuelta

Editar `tasks.md`:

- En cada linea creada, insertar la clave en negrita justo despues del checkbox:
  `- [ ] **[BPF-101]** Texto original de la tarea`
- El texto de la tarea **no se reescribe**: tiene que seguir matcheando lo que se mando a Jira.
- Frontmatter: `status: sincronizada` y `synced: <YYYY-MM-DD>`.
- Si alguna card fallo, el `status` queda en `consolidada` (todavia hay trabajo pendiente) y se
  dice explicitamente.

Reportar al usuario las claves creadas con su link (`https://bpfocus.atlassian.net/browse/<CLAVE>`).

## Modo `--cerrar` (sincronizacion inversa)

Invocado explicitamente, nunca por el hook y nunca encadenado a una creacion.

Para cada linea `- [x]` con clave: `getJiraIssue` para ver el estado actual,
`executeRead` → `listJiraIssueTransitions` para descubrir la transicion disponible hacia el estado final del
workflow (no asumir que se llama "Done": depende del proyecto), y recien despues
`transitionJiraIssue`.

Mismo contrato: tabla de lo que se va a transicionar, confirmacion, y despues ejecutar. Solo
issues con label `spec-driven`. Una card ya cerrada se saltea en silencio.

## Si el MCP no responde

Si no aparecen las tools `mcp__atlassian__*`, o el cloudId de bpfocus no esta entre los
recursos accesibles, **no es un problema a resolver reintentando**. Suele ser una de estas
cosas, y conviene decir cual:

1. El servidor no esta autenticado o la sesion OAuth expiro → el owner corre `/mcp` →
   `atlassian` → Authenticate.
2. El OAuth quedo en **otra cuenta** de Atlassian (el navegador tenia abierta la de otra
   organizacion): aparecen recursos, pero no el cloudId de bpfocus → re-autenticar con la cuenta
   de bpfocus activa, o desde una ventana privada.
3. Alguien volvio a poner un header `Authorization` en `.mcp.json`: con header presente, Claude
   Code no ofrece OAuth. Si responde `401 invalid_token`, la credencial es de tipo equivocado.
   Antecedente de 2026-09-13: se habia cargado la Admin API key de la organizacion (`ATCTT…`),
   que no sirve para el Rovo MCP. Ese MCP solo acepta OAuth, un token personal `ATATT…` en
   `Basic base64(email:token)` o una key de service account en `Bearer`.

En todos los casos: informar y parar. No intentar la REST API de Jira por afuera del MCP, ni
caer a las tools `mcp__claude_ai_Atlassian__*`.
