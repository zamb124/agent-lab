# Примеры целевых контрактов

Примеры показывают форму архитектуры, а не готовые текущие Pydantic-модели.
Имена API и классов нужно адаптировать после принятия ADR.

## 1. Trusted builtin + flow binding

### Immutable definition

```yaml
id: crm.note.create
version: 3
machine_name: crm_create_note
title: Create CRM note
description: >-
  Creates one plain-text note on an existing CRM entity. Use it only after the
  target entity is known and the user asked to persist information. Do not use
  it for searching or updating entity fields. Returns the created note id and
  entity id; it does not return the full entity.
canonical_input_schema:
  $schema: https://json-schema.org/draft/2020-12/schema
  type: object
  additionalProperties: false
  properties:
    entity_id:
      type: string
      minLength: 1
      description: Stable CRM entity identifier.
    text:
      type: string
      minLength: 1
      maxLength: 10000
      description: Plain-text note body to persist.
  required: [entity_id, text]
canonical_output_schema:
  type: object
  additionalProperties: false
  properties:
    note_id:
      type: string
      description: Stable id of the created note.
    entity_id:
      type: string
      description: Entity that received the note.
  required: [note_id, entity_id]
argument_sources:
  entity_id: [model, binding.state]
  text: [model]
effects:
  kind: create
  data_classes: [crm_note]
  read_only: false
  destructive: false
  open_world: false
required_scopes:
  - crm.notes:create
confirmation_floor: preview
idempotency: required
executor:
  kind: trusted_adapter
  ref: crm.create_note
```

### Binding for one flow

```yaml
id: support.add_note
definition: crm.note.create@3
flow_id: support
node_id: support_agent
llm_name: add_customer_note
title: Add a note to the current customer
description: >-
  Saves a note on the customer already selected in this conversation. Use only
  when the user asks to remember or record information. Do not ask for a
  customer id: the flow supplies it. The result confirms the created note id.
parameter_bindings:
  entity_id:
    source: state
    path: variables.current_customer_id
  text:
    source: model
    field: note_text
model_schema_projection:
  type: object
  additionalProperties: false
  properties:
    note_text:
      type: string
      minLength: 1
      maxLength: 10000
      description: Exact plain-text information the user wants recorded.
  required: [note_text]
result_projection: [note_id]
confirmation_override: preview
```

LLM не может подменить `entity_id`: он отсутствует в provider schema. Executor
получает его только после server-side проверки allowlisted state path.

### Trusted adapter

Целевой псевдокод:

```python
async def execute_create_crm_note(
    command: CreateCrmNoteCommand,
    context: AuthorizedToolContext,
    port: CreateCrmNotePort,
) -> CreateCrmNoteResult:
    return await port.create(
        tenant_id=context.tenant_id,
        actor_id=context.actor_id,
        entity_id=command.entity_id,
        text=command.text,
        idempotency_key=context.idempotency_key,
    )
```

Handler получает ровно одну operation-specific capability. Он не получает
generic CRM service или platform request.

## 2. OpenAI strict projection

Canonical contract может иметь optional field:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "query": {
      "type": "string",
      "minLength": 1,
      "description": "Search phrase."
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 20,
      "default": 5,
      "description": "Maximum result count."
    }
  },
  "required": ["query"]
}
```

OpenAI strict projection не должна просто повторять canonical schema:

```json
{
  "type": "function",
  "function": {
    "name": "search_documents",
    "description": "Search indexed documents. Use it for tenant documents, not public web search. Returns up to the requested number of matches with stable document ids.",
    "strict": true,
    "parameters": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "query": {
          "type": "string",
          "description": "Search phrase."
        },
        "limit": {
          "type": ["integer", "null"],
          "description": "Maximum result count from 1 to 20; null uses 5."
        }
      },
      "required": ["query", "limit"]
    }
  }
}
```

Runtime compiler normalизует `null`/missing к canonical default и повторно
валидирует full command. Provider projection и canonical schema имеют разные
hashes и тестируются как пара.

## 3. Discriminated action вместо конфликтующих flags

Плохо:

```json
{
  "properties": {
    "create": {"type": "boolean"},
    "delete": {"type": "boolean"},
    "id": {"type": "string"}
  }
}
```

Хорошо:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "operation": {
      "oneOf": [
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "action": {"const": "create"},
            "title": {
              "type": "string",
              "minLength": 1,
              "description": "Title of the new item."
            }
          },
          "required": ["action", "title"]
        },
        {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "action": {"const": "delete"},
            "item_id": {
              "type": "string",
              "minLength": 1,
              "description": "Stable id of the item to delete."
            }
          },
          "required": ["action", "item_id"]
        }
      ]
    }
  },
  "required": ["operation"]
}
```

Если provider плохо поддерживает union, разделите tools либо скомпилируйте в
provider-supported shape и проверьте evals. Не ослабляйте runtime validator.

## 4. User-code tool revision

```yaml
tool:
  id: tenant.acme.lookup_shipping
  owner_tenant_id: acme
revision:
  id: rev_018f
  language: python
  source_hash: sha256:...
  dependency_lock_hash: sha256:...
  input_schema_hash: sha256:...
  output_schema_hash: sha256:...
  status: active
requested_capabilities:
  - operation: http.fetch_json
    constraints:
      methods: [GET]
      hosts: [shipping.example.com]
      path_prefixes: [/v1/shipments/]
      max_response_bytes: 262144
sandbox:
  image: code-runner-python@sha256:...
  runtime_class: gvisor
  network: gateway_only
  state_fields: []
  secret_refs: [shipping-api]
  limits:
    wall_seconds: 10
    cpu_seconds: 3
    memory_mb: 128
    pids: 32
    output_bytes: 65536
```

Код не получает значение `shipping-api`. Он вызывает:

```python
result = await capabilities.http.fetch_json(
    connection_ref="shipping-api",
    method="GET",
    path=f"/v1/shipments/{shipment_id}",
)
```

Gateway:

1. проверяет grant и connection ownership;
2. запрещает другой host/method/path;
3. подставляет secret;
4. применяет DNS/SSRF policy;
5. ограничивает размер/таймаут;
6. редактирует response/logs.

## 5. Invocation-scoped grant

```json
{
  "iss": "flows",
  "aud": "capability-gateway",
  "jti": "grant_01J...",
  "iat": 1785330000,
  "nbf": 1785330000,
  "exp": 1785330060,
  "actor_id": "user_42",
  "tenant_id": "company_7",
  "flow_id": "support",
  "branch_id": "default",
  "source_node_id": "support_agent",
  "tool_call_id": "call_123",
  "definition": "crm.note.create@3",
  "binding_id": "support.add_note",
  "allowed_capabilities": [
    {
      "operation": "crm.notes:create",
      "resources": {"entity_ids": ["entity_9"]}
    }
  ],
  "max_calls": 1,
  "approved_argument_hash": "sha256:...",
  "approval_id": "approval_55"
}
```

Минимальные проверки gateway:

- signature, issuer, audience, time window, replay/jti;
- actor/tenant/execution context match;
- requested operation и resource subset;
- tool/binding/version match;
- call budget;
- approval and canonical args hash для protected effect.

## 6. Stable result/error

Success:

```json
{
  "ok": true,
  "data": {
    "note_id": "note_123"
  },
  "error": null
}
```

Failure:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "entity_not_found",
    "message": "The selected CRM entity no longer exists.",
    "retryable": false,
    "field": "entity_id"
  }
}
```

`error.code` — стабильный enum. `message` безопасен для LLM/user. Internal cause,
traceback и trace id остаются в server telemetry.

## 7. Parameter-bound approval

Proposal:

```json
{
  "status": "approval_required",
  "proposal": {
    "tool": "mail.send@4",
    "summary": "Send one email to alex@example.com",
    "effects": ["external_send"],
    "arguments_preview": {
      "to": ["alex@example.com"],
      "subject": "Contract update",
      "body": "…"
    },
    "argument_hash": "sha256:..."
  }
}
```

Approval record:

```json
{
  "approval_id": "approval_55",
  "actor_id": "user_42",
  "tool_revision": "mail.send@4",
  "argument_hash": "sha256:...",
  "expires_at": "2026-07-29T15:01:00Z"
}
```

Apply с другим recipient/body/version должен быть отклонён.

## 8. UI dual preview

```text
What the model sees
────────────────────────────────────────
add_customer_note(note_text: string)
Use when the user asks to record…

What will execute
────────────────────────────────────────
Capability   crm.note.create@3
Entity       Current customer (ent…9)     [from state]
Text         "Call back on Friday"         [from model]
Effect       CREATE crm_note
Permission   crm.notes:create
Approval     Preview required
Idempotency  Required
```

Ни secret value, ни полный state, ни platform source в preview не показываются.

## 9. Review test matrix

| Case | Expected |
|---|---|
| Valid model args | exactly one authorized execution |
| Unknown input field | validation error before handler |
| Model supplies runtime-only field | schema/validation rejection |
| Binding widens enum/range | binding compile failure |
| Denied actor calls builtin/code/MCP | same permission denial |
| Runner requests ungranted capability | gateway denial |
| Runner requests other tenant resource | gateway denial |
| Expired/replayed grant | gateway denial |
| Destructive args changed after approval | approval denial |
| Same write + idempotency key retried | no duplicate effect |
| Handler returns wrong shape | output contract error |
| Output contains secret-marked field | redacted/blocked |
| MCP schema hash changed | quarantine/re-review |
| Prompt injection in fetched content | cannot expand tool/grant scope |
