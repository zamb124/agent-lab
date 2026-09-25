---
name: design-flow-tools
description: "Проектировать, создавать, изменять и ревьюить tools для Flow-платформы: понятный UI-контракт для разработчика, точная JSON Schema для LLM, безопасные platform capabilities, sandbox для пользовательского кода, permissions/HITL, versioning и tool evals. Использовать при работе с builtin/code/MCP/flow-as-tool, ToolReference/ToolRegistry/BaseTool, capability gateway, редактором tools или схемами входа/выхода."
---

# Design Flow Tools

Проектируй tool как версионированную capability с двумя независимыми интерфейсами:

1. человек и LLM видят ясный, узкий контракт;
2. сервер отдельно решает, разрешено ли выполнить конкретное действие.

Не считай description, JSON Schema, UI-ограничения, sandbox manifest или LLM-инструкции механизмом авторизации.

## Сначала выбери маршрут

| Задача | Маршрут |
|---|---|
| Новый или изменяемый platform builtin | Immutable `ToolDefinition` + trusted adapter к узкому use-case port |
| Удобная версия существующего builtin для flow | Editable `ToolBinding`; не копируй и не открывай platform-код |
| Новый tool с кодом разработчика flow | Immutable user `ToolRevision` в untrusted sandbox |
| MCP tool | Pin server/tool/schema revision; проверяй trust, scopes и изменения схемы |
| Flow/node как tool | Версионированный orchestration contract; не маскируй его под inline code |
| Только преобразование уже известных данных | Предпочти deterministic node/код; tool LLM не нужен |
| Ответ из контекста модели без данных или действий | Не создавай tool |

Перед изменением классифицируй:

- кто владеет реализацией: platform, tenant developer или external MCP;
- где исполняется код: trusted process, isolated runner или remote server;
- какие данные читаются и какие эффекты возможны;
- какие аргументы выбирает LLM, какие задаёт binding, какие выдаёт runtime;
- можно ли безопасно повторить вызов;
- требуется ли preview, approval или idempotency key.

## Загрузи нужный контекст

Всегда:

1. прочитай `.cursor/rules/tools.mdc` и релевантные разделы `.cursor/rules/flows.mdc`;
2. для продуктового домена сначала прочитай `.cursor/rules/<service>.mdc`;
3. следуй порядку поиска из `AGENTS.md`: rule → graph → semantic → grep → snippet/read;
4. прочитай [architecture-standard.md](references/architecture-standard.md).

Дополнительно:

- при аудите текущего runtime, UI или миграции — процедура скила `.cursor/skills/refactor-engineer/SKILL.md`;
- при создании схемы, binding или нового API прочитай
  [contract-examples.md](references/contract-examples.md).

## Целевой паттерн

Разделяй четыре сущности:

- `ToolDefinition`: стабильная identity, immutable version, canonical input/output schemas, effects, scopes, executor reference и runtime limits;
- `ToolBinding`: редактируемое представление конкретного flow/node — LLM name, title, descriptions, visible arguments, defaults/mappings, result projection и более строгая approval policy;
- `ToolRevision`: immutable source/dependencies для user code либо pinned external revision;
- `ToolGrant`: короткоживущая серверная capability, ограниченная actor/tenant/flow/node/tool revision, allowed operations/resources и budgets.

Все виды tools проводи через один non-overridable execution pipeline:

`resolve → authorize → resolve hidden inputs → validate → preview/approve → execute → validate output → redact → audit/result`.

Реализация наследника должна задавать только бизнес-операцию. Она не должна обходить authorization, billing, timeout, tracing, output validation или redaction переопределением публичного `run`.

## Проектируй контракт для человека и LLM

Для каждого tool зафиксируй:

- стабильный machine id и отдельный человекочитаемый title;
- что tool делает, когда применять и когда не применять;
- какие данные читает и какой внешний/внутренний эффект создаёт;
- что означает каждый model-visible параметр, его формат, единицы, ограничения и пример;
- какой структурированный результат возвращается;
- ожидаемые ошибки, retryability и поведение при повторном вызове;
- trust/provenance, version, permissions и необходимость подтверждения.
- Права tool и flow — `.cursor/rules/authorization.mdc` и `.cursor/rules/tools.mdc` § Инварианты (п.5).

Используй canonical JSON Schema Draft 2020-12. Требуй object root, `additionalProperties: false` у каждого объекта, descriptions, constraints и `output_schema`. Делай невозможные состояния невыразимыми через enum или discriminated union вместо связанных boolean-флагов.

Не проси LLM передавать значения, которые уже знает код: tenant/user/flow ids, state-derived ids, policy flags, secret values и idempotency context. Пометь источник каждого implementation-аргумента как `model`, `binding`, `runtime` или `secret_ref`; в provider schema попадают только `model`.

Храни canonical schema отдельно от provider projection. Для OpenAI strict projection учитывай, что все object properties должны быть required, а логически optional поля представляются nullable. Не порти canonical contract провайдерскими ограничениями.

## Ограничивай UI-редактирование

Редактор builtin меняет `ToolBinding`, а не `ToolDefinition` и не trusted source.

Разрешай binding:

- улучшать title/description/examples;
- переименовывать model-facing аргументы через явный mapping;
- скрывать аргумент, если его безопасно поставляет binding/runtime;
- сужать enum/range/format;
- задавать allowlisted result projection;
- усиливать confirmation и budgets.

Запрещай binding:

- менять executor или privileged source;
- ослаблять scopes, effects, validation или confirmation floor;
- расширять canonical schema;
- превращать secret/runtime field в model-visible;
- получать больше state, capabilities или output fields, чем разрешает definition.

Для изменения user-owned code создавай новую immutable revision и показывай diff. Для builtin давай явные действия `Customize binding` и `Fork as untrusted tool`; fork не наследует platform privilege.

## Держи границу безопасности на сервере

- Проверяй actor, tenant, flow, source node, tool id/version, resources и argument hash в executor/gateway.
- Выдавай runner только subset manifest, разрешённый конкретному invocation grant.
- Не передавай runner полный `ExecutionState`; собери allowlisted context view.
- Не передавай secrets значениями. Пользовательский код оперирует opaque `secret_ref`, а gateway подставляет secret внутри разрешённой операции.
- Не давай user code generic `platform.request`, произвольный service client, database credentials или импорт platform modules.
- Считай AST/import filtering только lint/defense-in-depth, не sandbox boundary.
- Запускай untrusted code в отдельном минимальном image без platform source и app secrets, с non-root/read-only/seccomp/drop-all, resource limits, default-deny network и sandboxed runtime.
- Не загружай произвольный module path ради показа source. Source отдай только из авторизованного artifact store по tool revision id.
- Считай MCP annotations подсказками; policy принимает решение только по доверенному server-side metadata.

## Эффекты и подтверждение

Задай server-owned effect metadata минимум для:

`read`, `create`, `update`, `delete`, `external_send`, `financial`, `admin`, `code_execute`.

Для write/destructive/open-world операций:

- отделяй proposal/preview от apply;
- привязывай approval к actor, tool revision и canonical argument hash;
- инвалидируй approval после изменения аргументов или версии;
- требуй idempotency key там, где runtime может повторить вызов;
- не позволяй самой LLM определять необходимость approval.

## Обязательный результат проектирования

Перед кодом выдай или зафиксируй:

1. `Decision`: почему это tool и какой trust route выбран.
2. `Contract`: identity/version, model-visible input, hidden input, output и errors.
3. `Effects`: data classes, side effects, scopes, idempotency и approval.
4. `UI`: что разработчик видит, может менять и как тестирует.
5. `Runtime`: executor, grant, sandbox/network и redaction.
6. `Migration`: compatibility, version pinning и rollback.
7. `Verification`: unit/contract/security tests и LLM evals.

Если хотя бы один пункт неизвестен, не маскируй его произвольным default. Найди источник правды или сделай риск явным.

## Проверки перед завершением

Минимальный gate:

- schema проходит Draft 2020-12 validation и provider compilation;
- одинаковые args валидируются на UI/API/executor boundary;
- неизвестные поля отклоняются;
- output соответствует `output_schema`, не является JSON-строкой внутри JSON;
- permission denial одинаков для builtin, code, MCP и flow-as-tool;
- binding доказуемо только сужает definition;
- untrusted code не видит platform source, environment secrets или полный state;
- grant не позволяет вызвать unattached tool/capability;
- destructive call без parameter-bound approval отклоняется;
- retry write-call не создаёт второй эффект;
- logs/trace редактируют secrets и чувствительные outputs;
- evals измеряют выбор tool, валидность args, отказ от tool и recovery после ошибки.

При правках кода также выполни проверки из `backend-engineer`/`frontend-engineer` skills и релевантные тесты проекта.
