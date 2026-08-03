# Стандарт архитектуры Flow Tools

## 1. Решение

Канонический паттерн платформы:

> Tool — это версионированная capability. Ее исполняемая реализация, редактируемое
> представление в flow и выданное на один запуск право доступа являются разными
> объектами.

Это одновременно решает три требования:

- разработчик flow видит договор, происхождение, эффекты и ограничения;
- LLM получает небольшой и точный provider-compatible schema;
- platform authorization не зависит от текста, сгенерированного LLM, UI или
  пользовательского кода.

Не используйте «декоратор над функцией» как полную архитектуру. Декоратор может
быть удобным authoring adapter, но definition, binding, policy и execution
pipeline должны существовать независимо от него.

## 2. Слои и модели

### 2.1 ToolDefinition

Immutable и versioned:

```text
ToolDefinition
├── id                         стабильная capability identity
├── version                    immutable revision
├── machine_name               provider-safe default name
├── title                      имя для человека
├── description                what / when / when-not / behavior
├── canonical_input_schema     JSON Schema 2020-12
├── canonical_output_schema    JSON Schema 2020-12
├── argument_sources           model | binding | runtime | secret_ref
├── effects                    read/write/destructive/open-world/data classes
├── required_scopes            минимальные server scopes
├── confirmation_floor         минимальная policy, которую binding не ослабит
├── idempotency                none | supported | required
├── executor                   trusted adapter / sandbox revision / MCP pin / flow pin
├── limits                     wall time, calls, bytes, cost, concurrency
└── provenance                 owner, trust class, review/signature/hash
```

Identity и version не должны зависеть от UI title. Изменение поведения, schema,
effects, scopes или реализации создаёт новую version.

### 2.2 ToolBinding

Mutable, flow/node scoped и versioned для audit:

```text
ToolBinding
├── id
├── definition_id + pinned_version
├── flow_id + node_id
├── llm_name
├── title/description override
├── parameter_bindings
│   ├── model.<field>
│   ├── const.<value>
│   ├── state.<allowlisted_path>
│   ├── context.<server_field>
│   └── secret_ref.<opaque_id>
├── model_schema_projection
├── result_projection
├── confirmation_override      только строже definition floor
├── budgets                    только меньше definition limits
└── enabled
```

Binding — безопасная «удобная обёртка». Компилятор binding обязан доказать, что
она не расширяет definition:

- model schema — подмножество аргументов;
- ограничения равны или строже;
- hidden values имеют разрешённый source;
- result projection — allowlist;
- permissions/effects/limits не ослаблены;
- executor и revision неизменны.

### 2.3 ToolRevision

Нужна для кода и внешних зависимостей:

- user code: immutable source bundle, language, dependency lock/hash, author,
  scan result, created_at;
- MCP: server identity, tool name, input/output schema hash, reviewed annotations,
  OAuth scopes и trust state;
- flow-as-tool: flow/branch revision и contract hash.

Platform builtin source не является редактируемым artifact. UI может показать
документированный contract и provenance, но не должен импортировать произвольный
platform object для получения source.

### 2.4 ToolGrant

Короткоживущий, подписанный и server-issued:

```text
ToolGrant
├── iss / aud / jti / iat / nbf / exp
├── actor_id / tenant_id
├── flow_id / branch_id / source_node_id / tool_call_id
├── definition_id / definition_version / binding_id
├── allowed_capabilities[]
│   ├── operation
│   ├── resource constraints
│   └── argument constraints or canonical hash
├── max_calls / max_cost / deadline
└── approval_id + approved_argument_hash (если нужен)
```

Manifest, показанный runner, строится из grant. Gateway проверяет grant на каждом
вызове; присутствие имени в manifest само по себе не авторизует действие.

## 3. Единый execution pipeline

```text
LLM tool_call
   │
   ▼
resolve binding + pinned definition
   │
   ▼
authorize actor/tenant/flow/node/version
   │
   ▼
validate model args
   │
   ▼
resolve const/state/context/secret_ref inputs
   │
   ▼
validate full command + policy/effects/budgets
   │
   ├── preview / parameter-bound approval ──┐
   │                                        │
   ▼                                        │
execute trusted adapter / sandbox / MCP ◀───┘
   │
   ▼
validate output schema → redact/project → audit
   │
   ▼
stable ToolResult returned to LLM
```

Публичный executor method должен быть final/non-overridable в практическом
смысле. Реализация tool регистрирует только handler `_execute(command, context)`
или equivalent. Permission, billing, tracing, timeout, idempotency, output
validation и redaction оборачиваются платформой.

Ошибки также являются частью контракта:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "permission_denied",
    "message": "The current actor cannot create notes for this entity.",
    "retryable": false,
    "field": null
  }
}
```

Не возвращайте JSON, сериализованный в строку. Не отправляйте LLM traceback,
SQL/internal URLs, secret values или полный validation input.

## 4. Contract-first schema

### Canonical schema

- Draft 2020-12 — единый dialect для storage/API/runtime validation.
- Root `type: object`.
- `additionalProperties: false` на каждом object level.
- У каждого model-visible field есть `description`.
- Для string задаются semantic format/pattern/minLength; для number — units и
  bounds; для array — items и bounds.
- Enum используется для конечного набора вариантов.
- Взаимоисключающие формы задаются discriminated `oneOf`, а не комбинацией
  boolean flags.
- Default означает реальное runtime behavior, а не только подсказку UI.
- Input examples обязаны валидироваться.
- Output schema обязателен и содержит только high-signal данные.

Pydantic может быть authoring source для trusted Python handlers, но
`model_json_schema()` — начало compilation, а не финальный provider contract.
Проверяйте extra-field policy, descriptions, refs/unions и compatibility.

### Provider projections

Храните:

```text
canonical JSON Schema
        ├── runtime validator
        ├── UI form schema
        ├── OpenAI strict projection
        ├── Anthropic projection
        └── MCP inputSchema/outputSchema
```

OpenAI strict требует `additionalProperties: false` у объектов и все properties
в `required`; логически optional field делается nullable. Некоторые JSON Schema
features не поддерживаются, поэтому provider compiler должен либо корректно
понижать schema, либо давать build-time ошибку.

Описание tool должно отвечать на четыре вопроса:

1. Что именно делает?
2. Когда использовать и когда не использовать?
3. Как интерпретировать параметры, эффект и ограничения?
4. Что означает результат?

Проводите «intern test»: новый инженер должен корректно вызвать tool, имея только
catalog card/schema, без чтения реализации.

### Tool set

Не показывайте модели весь catalog. Binding/skill/tool-search выбирает малый
релевантный набор. Известные runtime значения не должны расходовать arguments и
создавать возможность подмены.

## 5. UI для прозрачности

### Catalog card

Показывайте без открытия кода:

- title, machine name, stable id и pinned version;
- owner/provenance и trust badge: Platform / Your code / MCP / Flow;
- what / when / when-not;
- model-visible inputs и источники скрытых inputs;
- output example;
- data accessed и effect badges;
- required permissions/scopes;
- confirmation/idempotency/retry behavior;
- runtime location и limits;
- schema/code change status и последний contract/eval result.

### Editor

Рекомендуемые вкладки:

1. **Overview** — назначение, usage boundaries, examples.
2. **Inputs** — form-first schema, source каждого поля и live call preview.
3. **Output** — schema и result projection.
4. **Effects & access** — data, permissions, external systems, confirmation.
5. **Implementation** — только user-owned code; для builtin — provenance/docs.
6. **Tests** — example calls, negative cases, dry-run и LLM evals.
7. **Versions** — semantic diff, consumers и migration action.

Всегда показывайте две формы preview:

- `What the model sees`: name, description и model schema;
- `What will execute`: resolved fields с masked secret/runtime values, effects,
  target resources и approval requirement.

Raw JSON Schema оставляйте как advanced mode. Основной путь — типизированная
форма, которая не позволяет сохранить некорректный contract.

### Редактирование

- `Customize for this flow` создаёт/правит binding.
- `Edit implementation` доступно только owner user tool и создаёт revision.
- `Fork platform tool` создаёт untrusted tool без inherited platform scopes.
- Breaking change требует новой major revision и явной миграции consumers.

## 6. Security architecture

### Trusted platform tools

Используйте ports-and-adapters:

```text
tool handler → operation-specific application port → domain service/repository
```

Не возвращайте handler общий service locator, container или raw platform HTTP.
Например, `CreateCrmNotePort.create(command, actor)` безопаснее, чем
`get_crm_service()` с десятками методов.

Trusted handler всё равно проходит общий policy pipeline. Trusted означает
доверие к реализации, а не автоматическое право конкретного user/flow.

### User code

AST validation полезна для понятных ошибок, но не изолирует процесс. Требуется
реальная runtime boundary:

- отдельный минимальный image без platform source;
- никаких DB URLs, encryption/JWT/OAuth/provider keys в environment;
- отдельный low-privilege service account;
- non-root, no privilege escalation, drop all capabilities, read-only root,
  seccomp/AppArmor;
- ephemeral writable tmp с quota;
- CPU/memory/PID/wall-time/output/cost limits;
- namespace default-deny ingress/egress; allow only gateway/DNS при необходимости;
- sandboxed runtime (например, gVisor/Kata/microVM) для hostile multi-tenant code;
- single-execution isolation или доказанная очистка worker pool;
- gateway calls только с invocation-scoped grant.

Полный `ExecutionState` не пересекает boundary. Создавайте schema-validated
`ToolContextView` только из полей, объявленных definition/binding.

Secret передаётся как opaque reference. Конкретная capability получает secret
server-side, использует его для одного разрешённого вызова и никогда не
возвращает значение.

Generic `platform.request`, unrestricted HTTP, arbitrary file/network access и
raw service clients несовместимы с least privilege. Если нужен HTTP, задайте
host/method/path/data policy и SSRF-safe resolution на gateway.

### MCP

- allowlist trusted servers;
- pin schema hash/version и OAuth scopes;
- diff/re-review после schema/description change;
- namespacing предотвращает shadowing;
- validate input и structured output локально;
- treat tool results as untrusted content;
- не доверять remote `readOnlyHint`/`destructiveHint` как authorization fact.

### Source transparency

Прозрачность не равна раскрытию всего platform source. Для builtin показывайте
контракт, effects, data lineage, version, owner и audit evidence. Source endpoint
должен читать только artifact по авторизованному tool revision id; никогда не
делайте `import_module(user_supplied_path)` для UI.

## 7. Effects, HITL и retries

Server-owned taxonomy:

| Effect | Default |
|---|---|
| read, closed-world | auto при наличии scope |
| read, open-world/sensitive | scope + output/data controls |
| create/update, reversible | preview либо policy-controlled auto |
| delete/external_send/financial/admin | parameter-bound approval |
| code_execute | sandbox + explicit capability budget |

Approval хранит canonical args hash, actor, definition revision, expiry и target.
Любое изменение делает approval недействительным.

Для retryable writes требуется idempotency key. Executor сохраняет operation
record до side effect и возвращает предыдущий результат при повторе того же key.

## 8. Versioning и compatibility

Считайте breaking:

- удаление/переименование input/output field;
- сужение допустимого input без миграции;
- изменение semantic meaning/default;
- новый side effect, scope или data class;
- read-only → write, idempotent → non-idempotent;
- изменение implementation с observable incompatible behavior.

Consumer pin хранит definition version и binding revision. Catalog может
предлагать upgrade, но runtime не должен молча переключать flow.

## 9. Verification

### Deterministic tests

- schema meta-validation и examples;
- canonical ↔ provider projection;
- unknown/missing/type/bounds validation;
- binding narrowing proof;
- permission parity для всех implementation kinds;
- output validation и secret redaction;
- grant scope/expiry/audience/replay/call budget;
- approval args hash;
- idempotent retry;
- sandbox escape/network/env/state negative tests;
- MCP schema drift.

### LLM evals

Измеряйте минимум:

- правильный выбор tool;
- правильный отказ от tool;
- валидность arguments;
- отсутствие model guesses для runtime fields;
- clarification при недостающих user inputs;
- recovery после retryable/non-retryable error;
- отказ от destructive call без approval;
- устойчивость к prompt injection в external tool results.

Версионируйте eval dataset вместе с definition. Любое изменение description,
schema или доступного tool set требует regression run.

## 10. Первичные источники

- [OpenAI: Function calling — defining functions and strict mode](https://developers.openai.com/api/docs/guides/function-calling)
- [Anthropic: Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
- [Anthropic: Tool-use contract](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works)
- [MCP schema: Tool, inputSchema, outputSchema, annotations](https://modelcontextprotocol.io/specification/2025-11-25/schema)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)
- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/)
- [Pydantic discriminated unions](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions)
- [OWASP AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html)
- [OWASP MCP Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [gVisor security model](https://gvisor.dev/docs/architecture_guide/security/)
