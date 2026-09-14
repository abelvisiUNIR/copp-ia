# copp-ia — TeleFlow Platform (Claude Code)

Las reglas del proyecto viven en `AGENTS.md`, que es la fuente unica para todas las herramientas.
Este archivo solo agrega lo especifico de Claude Code.

@AGENTS.md

## Subagentes, comandos y hooks

- Subagentes en `.claude/agents/`: `analista-requisitos`, `disenador-tecnico`,
  `desglosador-tareas`, `implementador`, `revisor`, `validador-spec`, `seguridad-infra`.
- Comandos en `.claude/commands/`: `/especificar`, `/disenar`, `/desglosar`, `/implementar`,
  `/revisar`, `/validar`, `/seguridad`, `/as-built`. No se llaman `/plan` ni `/review` para no
  pisar los built-in.
- Hook `PostToolUse` (`.claude/settings.json` → `.claude/hooks/spec_consolidada.py`): al editar un
  `tasks.md` en `status: consolidada` con tareas sin clave, avisa que corresponde `/sync-jira` en
  dry-run. No llama a la red.

## Jira

Las tareas de una feature consolidada se sincronizan con `bpfocus.atlassian.net` a traves de la
skill `sync-jira`. El formato de las cards y los limites de lo que el agente puede tocar en ese
Jira estan en:

@.claude/rules/atlassian-standards.md

El servidor `atlassian` de `.mcp.json` se autentica por **OAuth**: `/mcp` → `atlassian` →
Authenticate, con la cuenta de bpfocus activa en el navegador (si esta abierta otra cuenta de
Atlassian, el OAuth autoriza esa). **Ninguna credencial vive en un archivo**: ni en el repo ni en
`settings.local.json`.

En la misma sesion puede estar conectado el conector Atlassian de claude.ai
(`mcp__claude_ai_Atlassian__*`), logueado en **otra** organizacion. `sync-jira` solo usa
`mcp__atlassian__*` y verifica el cloudId de bpfocus antes de operar.
