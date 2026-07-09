---
project: copp-ia
date: 2026-06-30
status: accepted
provenance: copp-ia@main@6046648
tags: [adr, composer, llm]
---

# ADR-003: LLM configurable por instancia de organismo

> Provenance: `copp-ia@main@6046648`. Fuente: `docs/teleflow-adr.typ:126-138`,
> `TeleFlow-Arquitectura-v1.0.md:850-856`. Implementación: `teleflow/composer_service/providers.py`.

## Context
Cada organismo tiene restricciones propias: OSE puede usar Claude API; Antel puede requerir
modelo self-hosted por regulación; el Ministerio puede necesitar datos en territorio.

## Decision
El proveedor LLM se configura por **variables de entorno** (`LLM_PROVIDER`, `LLM_API_KEY`,
`LLM_MODEL`, `LLM_BASE_URL`). La interfaz `LLMProvider` (ABC, método `generate(prompt)→str`)
abstrae **anthropic | openai | ollama | stub**. Cambiar de proveedor es config, no código.

## Rationale
Desacopla el producto de un proveedor único. `LLMProvider` es un ABC con un solo método.

## Consequences
- (hecho — `providers.py`) `AnthropicProvider` (default model **`claude-fable-5`**),
  `OpenAIProvider` (`gpt-4o`), `OllamaProvider` (`llama3.1`, sin API key), `StubProvider`.
- `get_provider()` cae a **Stub** si falta `LLM_API_KEY` en anthropic/openai
  (`providers.py:154-164`). Default del compose: `LLM_PROVIDER=stub`
  (`docker-compose.yml:13`); `.env.example` trae `anthropic`.
- ⚠️ La tabla de la sección 9.3 del `.md` omite `stub` — el `.typ`, el `.env.example` y el
  código sí lo listan. Ver [[2026-07-09-validacion-doc-vs-codigo]].

## Alternatives
LLM fijo (solo Claude) · config en DB · plugin system (sobre-ingeniería para 4 proveedores).

## Sources
`docs/teleflow-adr.typ:126-138` · `teleflow/composer_service/providers.py`
