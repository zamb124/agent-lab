# Аудит текущей реализации Flow Tools

Дата снимка: 2026-07-29 (обновление после Phase 0–4 foundations).

Перед реализацией перепроверьте каждую находку: рабочее дерево во время аудита
содержало незакоммиченные изменения.

## 1. Что уже сделано

### Phase 0 — security containment (частично)

- `FunctionTool` больше не обходит `BaseTool.run`: единый wrapper +
  permission regression tests.
- `/flows/api/v1/code/tool-source` резолвит только builtin `tool_id` через
  `ToolRegistry` (не произвольный `import_module` path).
- Execution token claims: `allowed_capabilities`, `max_calls`,
  `approved_argument_hash`, `audience`; gateway проверяет
  `allowed_capabilities`.
- Allowlisted `ToolContextView` вместо полного `ExecutionState.model_dump`
  в remote runner; manifest filter по `allowed_capabilities`.
- Source sanitizer hard-reject запрещённых `apps.*`/`core.*` импортов.

Осталось: Helm runner isolation (minimal env/SA/NetworkPolicy), полное
end-to-end ToolGrant minting с non-empty allowed set по умолчанию.

### Phase 1 — contract foundation

- Модели: `apps/flows/src/models/tool_contracts.py`
  (`ToolDefinition`, `ToolBinding`, `ToolRevision`, `ToolGrantClaims`,
  `ToolResultEnvelope`).
- Metadata на `BaseTool`/`@tool`: `output_schema`, `effects`,
  `confirmation_floor`, `idempotency`, `argument_sources`.
- OpenAI strict compiler: `compile_openai_strict_parameters` подключён к
  `BaseTool.to_openai_schema`.
- CI: `scripts/check_tool_contracts.py` (в `make lint`).

### Phase 2 — thin wrappers

- Clients: `WikiClient`, `DocumentsClient`, `CrmClient`, `SyncClient`,
  `FilesClient` (один в `core/clients/`), `LaraClient`, `WorktrackerClient`,
  `FlowsClient`, `TeamClient`, `DeviceClient`, …
- Tools → только `XxxClient()`; без Port/Facade/`get_*_service`/`runtime_deps`.
- In-process clients: `require_current_container().<dep>` внутри клиента.
- `SERVICE_CLIENT_ALLOWLIST` / `CONTAINER_ALLOWLIST` пусты.
- CI запрещает shadow-модули и `runtime_deps` в tools.

### Phase 3 — UI / approval foundations

- `ToolApprovalStore` (Redis) + `hash_tool_arguments`; flows editor propose
  пишет `approval_id` alongside Lara.
- `POST /flows/api/v1/tools/preview` — dual preview (model_view +
  execution_plan).
- `GET /flows/api/v1/tools/{tool_id}/contract` — `ToolDefinition`.
- UI: effects/confirmation badges; builtin editor без пустого code node.

### Phase 4 — backfill / eval stubs

- `iter_builtin_tool_definitions` / `build_tool_definition_from_base_tool`.
- `binding_from_tool_reference`.
- Eval dataset schema stubs: `tests/flows/evals/tool_selection_cases.json`.
- Script: `scripts/backfill_tool_definitions.py`.

## 2. Оставшиеся gaps

| Gap | Статус |
|---|---|
| Runtime materialization на `ToolReference` | ещё не Definition/Binding |
| ToolGrant minting с scopes по умолчанию | claims есть; default `[]` = unrestricted |
| Helm runner secret isolation | не завершено |
| LaraActionEngine → единый ToolApproval pipeline | store есть; Lara ещё apply-path |
| `ToolResultEnvelope` enforced на всех builtins | модель есть |
| Live LLM eval gate | только schema stubs |
| Full effects metadata на всех 194 tools | wiki/scheduling + частично |
| `sandbox_codegen` ServiceClient | последний allowlist entry |

## 3. Definition of done (ещё не полностью)

- ни один implementation kind не обходит policy pipeline;
- UI change не может расширить privilege;
- runner image/env не содержит platform secret или source;
- grant разрешает только attached tool revision и нужные capabilities;
- input/output/provider schemas валидируются в CI;
- все flows pin-ят definition/binding revisions;
- breaking changes имеют explicit migration;
- tool/effect/access видны человеку до сохранения и до approval;
- LLM evals и abuse tests блокируют regression.
