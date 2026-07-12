---
project: copp-ia
status: active
created: 2026-07-12
updated: 2026-07-12
tags: [dx, gateway, cli, swagger, quick-win]
---

# Quick win DX — Swagger auth + CLI utf-8

## Goal
Dos fixes de developer-experience detectados en la validación ([[2026-07-09-validacion-doc-vs-codigo]]):
1. Gateway sin *security scheme* → Swagger no podía autenticar (todo daba 401 desde "Try it out").
2. CLI `tflow` crasheaba al imprimir ✓/✗ en consolas Windows cp1252.

## Context
Rama `fix/dx-swagger-cli` desde `devyos`.

## Current State — HECHO
- **Gateway** (`gateway/main.py`): `APIKeyHeader(name="X-TeleFlow-API-Key", auto_error=False)`
  agregado como dependencia global del `FastAPI`. Ahora OpenAPI expone `securitySchemes` y cada
  operación lleva `security: [{APIKeyHeader: []}]` → **Swagger muestra "Authorize"** y envía el
  header. La validación real sigue en el middleware (auto_error=False no rechaza).
- **CLI** (`cli.py`): `sys.stdout/err.reconfigure(encoding="utf-8")` al inicio de `main()` →
  ya no crashea imprimiendo ✓/✗ en cp1252 (adiós al workaround `PYTHONIOENCODING=utf-8`).
- **Verificado:** mypy 0; openapi con `APIKeyHeader`; CLI `validate` imprime `✓ válido` sin env;
  gateway reconstruido y **e2e 3/3** verdes.

## Next Steps
- [x] Security scheme en el gateway.
- [x] Fix utf-8 del CLI.
- [ ] Commit (código + wiki) y merge a `devyos`.

## Notas
- Warning preexistente (no de este cambio): "Duplicate Operation ID" en los catch-all
  `/relations/{rest}` y `/drafts/{rest}` (mismo handler para varios métodos). Cosmético; candidato
  a limpieza futura (Fase D) con `operation_id` explícitos.

## Log
- 2026-07-12: creado y ambos fixes aplicados/verificados.
