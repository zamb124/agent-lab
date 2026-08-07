# План полной миграции: Flow UI как единственный интерфейс поверх A2A

> Статус: **архитектурный и реализационный план; реализация ещё не начата**  
> Дата фиксации: 2026-08-03  
> Последнее уточнение: 2026-08-04 — durable reopen/share/autosync continuity; canonical Linnex catalog identity для multi-domain platform; layout grid и строгий editor/runtime WYSIWYG  
> Область: `agent-lab`, прежде всего `flows`, durable execution, capability gateway, общий frontend, embed, voice, HITL и внешние A2A flow  
> Ключевое ограничение: **обычные и существующие A2A Artifacts/Parts остаются полностью поддерживаемыми**. Они не объявляются legacy и не заменяются частным UI-протоколом.

---

## 0. Для чего нужен этот документ

Этот документ является блокирующим планом перед реализацией. Он фиксирует:

1. один итоговый wire-протокол без параллельных ветвей «chat» и «UI»;
2. точную границу между стандартным A2A 1.0 и опциональным A2UI;
3. сохранение обычных `text`, `raw`, `url`, `data` Parts и произвольных A2A Artifacts;
4. модель, в которой чат — только редактируемый шаблон страницы;
5. хранение полного актуального UI и заполненных значений в durable `ExecutionState`;
6. серверный контракт `Submit`, который запускает или продолжает flow;
7. task/artifact persistence, чтобы `SendMessage`, stream, `GetTask`, `ListTasks`, reconnect, push и replay показывали один и тот же результат;
8. безопасный путь UI-изменений из flow и sandbox capability;
9. точный список создаваемых, изменяемых, переносимых и удаляемых файлов;
10. порядок hard-cut миграции без внутренней chat-ветви после cutover;
11. durable continuity: тот же экран и данные после close/reload/new device/share;
12. layout grid как часть самого `FlowUIDocument`, а не декоративная сетка только в editor;
13. строгий WYSIWYG-контракт: editor canvas и пользовательский экран запускают один production renderer, catalog, CSS, tokens и render context;
14. тесты, observability, security, accessibility, performance и критерии готовности.

До принятия этого плана не следует менять runtime-код. После принятия этапы выполняются строго по gates из раздела 23: следующий этап не начинается, пока не закрыты проверки предыдущего.

### 0.1. Изученные источники истины

Локальные источники:

- A2A SDK: `a2a-sdk>=1.0,<2`, сейчас lock фиксирует `1.1.1`;
- официальный A2A 1.0 fixture pin в `tests/flows/a2a_conformance/fixtures/official/`;
- `.cursor/rules/a2a.mdc`, `streaming.mdc`, `durable_execution.mdc`, `execution_state.mdc`, `session.mdc`, `flows.mdc`, `flows_chat.mdc`, `frontend.mdc`, `files.mdc`, `voice.mdc`, `handoff.mdc`;
- фактические обработчики A2A, emitters, durable ledger, code runners, frontend runtime, editor, embed и тесты.

Внешние первичные источники:

- [A2UI: обзор и актуальные версии](https://a2ui.org/);
- [A2UI v0.9.1 extension specification](https://github.com/a2ui-project/a2ui/blob/main/specification/v0_9_1/docs/a2ui_extension_specification.md);
- [A2UI v0.9.1 Basic Catalog implementation guide](https://a2ui.org/specification/v0.9.1-basic-catalog-implementation-guide/);
- [A2UI actions](https://a2ui.org/concepts/actions/);
- [A2UI data binding](https://a2ui.org/concepts/data-binding/);
- [A2UI messages reference](https://a2ui.org/reference/messages/);
- [A2A protocol specification](https://a2a-protocol.org/latest/specification/).

Принятая версия для первого production cut: **A2UI v0.9.1** с отдельным version codec. A2UI v1.0 не должен проникать в доменную модель до стабилизации; переход на него должен потребовать замены codec/schema fixtures, а не переписывания runtime и редактора.

---

## 1. Неподвижные архитектурные решения

Следующие решения не являются предметом оптимизации во время реализации.

### 1.1. Один транспорт и один протокол

- Единственный сетевой transport пользователь ↔ flow: **A2A 1.0 JSON-RPC + SSE**.
- `SendMessage`, `SendStreamingMessage`, `GetTask`, `ListTasks`, `CancelTask`, `SubscribeToTask` и push notification продолжают работать как A2A.
- A2UI передаётся **внутри стандартного A2A `Part.data`** и объявляется как опциональное A2A extension/media type.
- Отдельного `/chat/send`, `/ui/submit`, WebSocket-протокола редактора или второго reducer ingress не создаётся.
- A2UI не добавляет новый `Part.kind`, новый `Artifact.kind` или новый тип stream event.

### 1.2. Обычные A2A Artifacts — не legacy

Полноценными и равноправными остаются:

- `Part.text`;
- `Part.raw` с `filename` и `mediaType`;
- `Part.url` с `filename` и `mediaType`;
- `Part.data` с любым валидным JSON value;
- произвольные `Artifact.name`, `description`, `artifactId`, `metadata`, `extensions`;
- смешанные Parts внутри одного Artifact;
- append/update одного Artifact с постоянным `artifactId`;
- неизвестные платформе артефакты внешнего A2A агента.

Существующие именованные артефакты платформы также сохраняются как A2A-контракт:

- `response`, `reasoning`;
- `operator_reply`, `user_message`, `operator_files`;
- `tool_call_<id>`, `tool_result_<id>`;
- `node_start_<id>`, `node_complete_<id>`, `node_error_<id>`;
- `edge_executed_*`, `edge_error_*`;
- общий `artifact` и файловые артефакты.

Удаляется только **платформенная special-case семантика** `artifact.name == "ui_event"` после перевода всех её producers/consumers. Само имя не становится запрещённым на A2A wire: внешний или старый клиентский Artifact с именем `ui_event` по-прежнему losslessly сохраняется и отображается generic projector как неизвестный data Artifact. Обычные A2A Artifacts не удаляются и не обязаны становиться A2UI.

### 1.3. Чат — шаблон, а не runtime

- Нет доменного типа `ChatState`, отдельного chat reducer и отдельного chat transport.
- Есть `FlowUIDocument`, renderer и editor.
- «Чат» — стандартный редактируемый шаблон `chat`, состоящий из тех же компонентов каталога: layout, artifact feed, composer, file controls, task controls и `Submit`.
- SPA-страница чата, drawer Lara, editor test, embed, landing demo и HITL используют один `<platform-flow-ui>` с разными документами/режимами.
- Любой chat-like UX можно изменить в редакторе без создания параллельного runtime.

### 1.4. Один ingress reducer

На клиенте существует ровно одна цепочка:

```text
A2A JSON-RPC/SSE StreamResponse
        │
        ▼
Task + Artifact accumulator (lossless A2A projection)
        │
        ├── A2UI data part ──► A2UI codec/reducer ──┐
        │                                           │
        └── ordinary A2A part ─► Part→UI projector ─┤
                                                    ▼
                                         Flow UI materialized view
                                                    │
                                                    ▼
                                         <platform-flow-ui>
```

Ни A2UI, ни текущие именованные artifacts не получают отдельный SSE parser, store или render loop.

### 1.5. Полный UI находится в state

- В `ExecutionState` всегда находится полный materialized `FlowUIDocument`: все страницы/surfaces, компоненты, bindings, текущая активная страница и значения.
- Введённые пользователем значения не живут только в DOM или transient frontend store.
- Flow видит принятую сервером ревизию UI и может изменить document/data model перед следующим ответом.
- Durable ledger остаётся источником истины; `ExecutionState` — materialized projection.
- Изменения UI пишутся semantic delta, а не постоянным whole-state overwrite.
- Закрытие браузера, reload, новая вкладка, открытие на другом устройстве или переход по share-link **не создают UI из default template заново**: новый экран получает authoritative current `FlowUIDocument` этой же session/context и отрисовывает его в том виде, в котором он был сохранён.
- Восстанавливаются как минимум active page/surface, component tree, `/content`, заполненные `/values`, session-owned navigation state и накопленные A2A Tasks/Artifacts.
- Share-link указывает на тот же durable context/document (если пользователь явно не выбрал «создать копию»), поэтому получатель видит ту же принятую сервером ревизию, а не пустую новую сессию.
- Для сохранения ещё не отправленных через Submit полей существует отдельный A2A autosync/control command; autosync сохраняет UI state, но не запускает flow.

### 1.6. Submit — единственный flow-invoking action UI-клиента

- В интерактивном опубликованном документе обязательно существует доступная кнопка с зарезервированным action name `platform.ui.submit`.
- Нажатие создаёт стандартный A2A user `Message` и запускает новый Task либо resume текущего `input-required` Task.
- Локальные действия (`navigate`, tabs, modal open/close, set value) применяются немедленно на клиенте и не вызывают flow; если их state помечен как session-owned, фоновый `platform.ui.sync` только сохраняет его через A2A.
- Другие server events до отдельного расширения политики не запускают flow.
- Обычный A2A клиент без UI по-прежнему запускает flow обычным `Message` с любыми стандартными Parts; требование кнопки относится к editor-generated UI, а не ломает A2A.

### 1.7. Никакого двойного представления одного результата

- Один и тот же логический UI update не отправляется одному клиенту одновременно как A2UI и как дублирующий text artifact.
- Для A2UI-capable клиента выбирается A2UI representation.
- Для клиента без extension выбирается стандартная A2A fallback representation.
- Независимые runtime artifacts (`tool_call`, file, reasoning и т. п.) могут присутствовать рядом с UI update, потому что это отдельные факты, а не дубль.

### 1.8. Без произвольного исполняемого UI

- Flow передаёт декларативные компоненты только из trusted catalog.
- Никаких script tags, arbitrary HTML, dynamic JS imports, `eval`, inline event handlers или flow-provided custom elements.
- Markdown санитизируется; URL и media проходят allowlist/SSRF/content checks; data bindings проходят schema/pointer validation.

### 1.9. Canvas редактора является production-экраном, а не его имитацией

- Сетка, responsive placement, gaps, margins, max-width и component sizing являются типизированными данными `FlowUIDocument`; editor не хранит второй, визуальный layout рядом с runtime layout.
- В центре Interface workspace монтируется **тот же production `<platform-flow-ui>` из того же собранного asset**, что открывается конечному пользователю. Отдельные `editor renderer`, preview CSS, fork catalog components и «почти такие же» mock widgets запрещены.
- Renderer запускается в изолированном production render frame с точным размером целевой поверхности. CSS/editor chrome родительского окна не должен каскадировать внутрь frame.
- Selection rectangles, drag handles, column/baseline grid, rulers, guides и snap indicators рисуются отдельным editor overlay **поверх** frame. Overlay не добавляет wrapper-элементы в component tree, не меняет box model и никогда не попадает в опубликованный UI.
- Editor изменяет `FlowUIDocument` domain commands, после чего production renderer получает новую immutable revision и рендерит её обычным способом. Inspection bridge имеет только read-only доступ `componentId → DOMRect/computed layout`; менять production DOM через bridge запрещено.
- Preview без overlays буквально равен production renderer. Run workspace использует тот же frame и настоящий A2A Task, а не другой preview runtime.
- Результат маркируется `Exact` только если совпали document revision/state sequence, renderer build hash, catalog manifest checksum, design-token checksum, font manifest checksum, target surface profile, viewport, brand, theme, locale/timezone/direction и capability/permission context. При любом несовпадении editor показывает `Context differs` с конкретным diff и не обещает 1:1.
- Граница гарантии формулируется честно: при одинаковых browser engine/version, CSS viewport, device pixel ratio, font/image assets и render context DOM, computed layout и pixels должны совпасть 1:1. Между разными browser/OS допускаются только заранее измеренные rasterization-различия; component geometry, breakpoints, order, visibility и values обязаны оставаться одинаковыми.
- Для окончательной проверки разработчик может открыть signed preview URL на целевом устройстве. URL загружает опубликованный production shell/renderer и ту же immutable draft revision; это не отдельная реализация preview.

---

## 2. Терминология и границы протокола

### 2.1. A2A `Part`

Минимальная стандартная единица содержимого A2A. В локальном A2A 1.0 protobuf oneof установлен ровно один из `text | raw | url | data`. Поля `metadata`, `filename`, `mediaType` принадлежат Part. На wire нет `kind`.

### 2.2. A2A `Artifact`

Task output с устойчивым `artifactId`, именем, Parts, metadata и extensions. Artifact создаёт агент/flow. Клиент в `Message` отправляет Parts, а не Artifacts.

Это принципиально: требование «каждый компонент — артефакт для A2A» реализуется без нарушения спеки так:

- каждый UI component имеет стабильный `componentId`;
- каждая отображённая внешняя Part имеет lossless provenance `{taskId, artifactId, partIndex}`;
- значения всех input-компонентов входят в единый `a2uiClientDataModel` при autosync/submit;
- UI surface update является A2A Artifact, внутри которого лежит пакет A2UI messages;
- **не** создаётся один A2A Artifact на каждый input component и **не** отправляются client-side Artifacts в `Message`.

Так сохраняются и лаконичность, и стандарт A2A.

### 2.3. A2UI surface/page

Wire-представление декларативной поверхности A2UI. В доменной модели платформы surface соответствует странице либо независимой panel/modal surface. Один A2A Artifact обновляет одну логическую surface и сохраняет постоянный `artifactId` при stream append/update.

### 2.4. `FlowUIDocument`

Внутренняя version-neutral materialized модель всего UI контекста. Она не является копией конкретного wire JSON v0.9.1. `A2UI091Codec` преобразует её в официальные `createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface` и обратно.

### 2.5. Generic Part projector

Детерминированный UI adapter для любого обычного A2A Artifact. Он не меняет wire, не «угадывает намерение» и не удаляет неизвестные данные. Его задача — безопасно показать Part через trusted components.

---

## 3. Фактическое состояние проекта и найденные архитектурные разрывы

Этот раздел описывает причины миграции; он должен использоваться как regression checklist.

### 3.1. Blocking `SendMessage` теряет обычные artifacts

`apps/flows/src/channels/a2a.py::_build_task_from_events` сейчас:

- читает текст только из artifacts с именами `response` и `reasoning`;
- игнорирует произвольные artifacts;
- игнорирует `raw`, `url`, произвольный `data`, Part metadata и Artifact extensions;
- заменяет исходные IDs случайными UUID;
- меняет JSON-response в частный `{data: {res: ...}}`;
- для простого текста часто не возвращает Artifact вообще;
- собирает blocking Task по другой логике, чем streaming client reducer.

Это уже нарушает требуемую совместимость и должно быть исправлено до A2UI.

### 3.2. `GetTask` не восстанавливает artifacts

`apps/flows/src/channels/base.py::_get_task_from_state` строит status/history из `ExecutionState`, но не возвращает Task artifacts. После завершения stream или рестарта произвольный output теряется для `GetTask`.

### 3.3. Artifact append сейчас не имеет устойчивой identity

`apps/flows/src/streaming/base.py::emit_text` создаёт новый UUID для каждого chunk, даже при `append=True`. Стандартный append должен обновлять Artifact с тем же ID. Аналогичная identity policy не централизована для reasoning/operator streams.

### 3.4. Durable state хранит только последний task

- `workflow_instances.task_id` и `ExecutionState.task_id` описывают текущий/последний запуск;
- session — `{flow_id}:{context_id}`;
- `_get_task_from_state` по сути возвращает один Task на весь context;
- `ListTasks` не имеет полноценной durable task collection;
- прошлые Task artifacts и terminal snapshots не восстанавливаются.

Для многостраничной долговечной UI-сессии context должен жить долго, но каждый законченный user submit должен оставаться отдельным A2A Task.

### 3.5. Вход A2A сводится к тексту

`A2AChannel._prepare_a2a_params` использует `get_message_text`, отдельно сохраняет файлы и затем передаёт строку `content`. Structured A2UI action, full data model и произвольные `data` Parts не становятся типизированным interaction envelope.

### 3.6. Внешний A2A client схлопывает результат

`core/clients/a2a_client.py`:

- отправляет только text Part;
- указывает некорректно узкий `acceptedOutputModes: ["text"]`;
- возвращает `A2ATaskResponse.response/status/raw`;
- делает structured artifacts побочным `raw`, а не first-class result.

`RemoteFlowNode` записывает только текст в `state.response`. Поэтому внешний A2UI или обычный structured Artifact не может пройти через remote flow без потерь.

### 3.7. UI сейчас является вторичной chat-ветвью

- `core/frontend/static/lib/chat/platform-chat.js` — монолит 4273 строки;
- `a2a-chat-runtime.js`, `chat-state.js`, `chat-controller.js` формируют отдельную chat projection;
- custom `ui_event` отдельно маппится в transient `_uiBlocksByTaskId`;
- hydration восстанавливает сообщения, но не полный UI и artifacts;
- unknown `data` Parts отображаются неполно;
- chat blocks и renderer существуют параллельно стандартным A2A artifacts.

### 3.8. Editor редактирует только graph

`apps/flows/ui/events/resources/editor.resource.js` хранит `branchData`, graph selection, execution state и history, но не UI document. `flow-editor-page.js` предлагает canvas/focus и execution panel; полноценного Interface workspace нет.

### 3.9. Небезопасный путь `ui_events_pending`

- `ExecutionState.ui_events_pending` доступен sandbox state view;
- capability `state.push_ui_event(s)` мутирует возвращаемый user-controlled state;
- language runners возвращают только state/result/interrupt;
- host не отделяет доверенный platform effect от произвольной state mutation.

UI-команды должны идти отдельным типизированным side channel и применяться только host-side validator.

### 3.10. Конфигурация закрепляет chat как отдельный продукт

- `FlowConfig.chat: FlowChatSettings`;
- `EmbedConfig.chat_override`;
- `/chat-profile`;
- `<platform-chat-settings-fields>`;
- bundles с top-level `chat`;
- OpenAPI и i18n с chat-specific contract.

Это не позволяет чату быть лишь шаблоном общего UI.

---

## 4. Целевая архитектура модулей

```text
┌───────────────────────────────────────────────────────────────────────┐
│                         Design time                                   │
│ Flow editor: Logic | Interface | Run                                 │
│   Interface editor ──► FlowInterfaceConfig / UI template             │
└──────────────────────────────┬────────────────────────────────────────┘
                               │ publish/version
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    Durable runtime / context                          │
│ A2A Message ─► Interaction parser ─► Flow execution                  │
│      │              │                    │                            │
│      │              └─ accepted values ─► ExecutionState.ui_document │
│      │                                   │                            │
│      │        trusted UI effects ◄───────┘                            │
│      │                     │                                          │
│      ▼                     ▼                                          │
│ A2A task ledger ──► task/artifact projections ──► representation     │
└──────────────────────────────┬────────────────────────────────────────┘
                               │ A2A Task/StreamResponse only
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                               Client                                  │
│ A2A accumulator ─► A2UI codec OR generic Part projector              │
│                  ─► one Flow UI store ─► <platform-flow-ui>           │
└───────────────────────────────────────────────────────────────────────┘
```

### 4.1. Domain layers

1. **A2A wire layer** — protobuf types from `a2a-sdk`; version/header/method validation.
2. **Task projection layer** — lossless Tasks, Messages, Artifacts and stream updates.
3. **Interaction layer** — normalizes ordinary A2A input or UI submit into a Flow interaction without changing original Message.
4. **Flow UI domain layer** — version-neutral document, components, data model, revision and commands.
5. **A2UI codec layer** — only место знания v0.9.1 wire schema.
6. **Representation layer** — выбирает A2UI либо generic A2A fallback для UI effects.
7. **Frontend projection layer** — lossless accumulator + one UI reducer.
8. **Renderer/editor layer** — trusted catalog, presentation and authoring.

Зависимости направлены внутрь: renderer не знает о JSON-RPC; Flow UI domain не импортирует Lit; execution nodes не конструируют wire A2UI JSON вручную.

---

## 5. Единый A2A compatibility profile

### 5.1. Wire baseline

- Protocol version: локально зафиксированный A2A `1.0`.
- Binding: JSON-RPC 2.0; streaming/push body — A2A `StreamResponse` ProtoJSON.
- Request header: `A2A-Version: 1.0`.
- Extension activation header: канонический `A2A-Extensions`.
- Part ProtoJSON: ровно одно из `text`, `raw`, `url`, `data`; **никакого `kind`**.
- Enum wire values остаются `ROLE_*` и `TASK_STATE_*`.
- A2A protobuf types берутся только из `a2a-sdk`; собственная альтернативная модель wire не создаётся.

### 5.2. A2UI AgentCard extension

AgentCard каждого Flow объявляет поддержку, но не требует её:

```json
{
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "extendedAgentCard": false,
    "extensions": [
      {
        "uri": "https://a2ui.org/a2a-extension/a2ui/v0.9.1",
        "required": false,
        "description": "Declarative Flow UI over standard A2A data parts",
        "params": {
          "supportedCatalogIds": ["https://linnex.io/a2ui/catalog/platform/v1"],
          "acceptsInlineCatalogs": false
        }
      }
    ]
  }
}
```

Правила:

- `required=false`, иначе ordinary A2A client станет несовместимым;
- `supportedCatalogIds` — только доверенные каталоги;
- inline catalogs в первом релизе запрещены;
- `skills[].inputModes/outputModes` и defaults используют MIME types (`text/plain`, `application/json`, при необходимости `application/a2ui+json`), но не выдуманный mode `"a2ui"`;
- extension negotiation не строится только на `acceptedOutputModes`;
- точный AgentCard JSON валидируется локальным A2A 1.0 protobuf fixture.

### 5.2.1. Канонический домен каталога и multi-domain runtime

Основная platform identity — **Linnex**, primary apex — **`linnex.io`**. Поэтому канонический идентификатор platform catalog:

```text
https://linnex.io/a2ui/catalog/platform/v1
```

Multi-domain правила:

- catalog ID — стабильный protocol identifier и не вычисляется из текущего HTTP `Host`;
- все Linnex deployments/brands (`linnex.io` и другие apex из `platform_brands`) рекламируют один канонический Linnex catalog ID, если component schema одинакова;
- source of truth для default canonical apex — существующий `primary_platform_domain` (`linnex.io`), а не новый hardcode, разбросанный по сервисам;
- создать единый resolver/constant уровня Flow UI, который строит и валидирует canonical catalog URI из primary domain; production default обязан дать URI выше;
- API, AgentCard endpoint URL, embed assets, short/share links, OAuth и Files URLs остаются host/brand-aware через `resolve_brand(host)`, `resolve_public_base_url` и существующие platform-brand settings;
- frontend на любом поддерживаемом домене может загружать renderer/assets same-origin, одновременно используя `https://linnex.io/...` как логическую identity каталога;
- внешний client не обязан делать network import по catalog ID: renderer выбирается из уже доверенного локального registry; URI служит negotiation/schema identity;
- на `https://linnex.io/a2ui/catalog/platform/v1` должен публиковаться immutable/versioned manifest/schema description для tooling и документации;
- alias catalog IDs для других доменов не рекламируются, иначе negotiation/cache/component identity фрагментируются; отдельный ID допустим только для действительно другого schema catalog;
- официальный extension URI остаётся `https://a2ui.org/a2a-extension/a2ui/v0.9.1`: домен Linnex относится к нашему component catalog, а не подменяет identity стандарта A2UI.

Обязательные tests запускают один и тот же negotiated UI на primary `linnex.io` и минимум одном дополнительном configured brand host: catalog ID одинаковый, runtime origins/branding разные.

### 5.3. Client capability handshake

A2UI-capable клиент на каждом первом сообщении контекста и после capability change передаёт:

- `A2A-Extensions: https://a2ui.org/a2a-extension/a2ui/v0.9.1`;
- `message.metadata.a2uiClientCapabilities` по официальной схеме;
- собственный platform catalog ID и поддержанные components/functions;
- locale, timezone, viewport class и accessibility preferences — только в разрешённом platform metadata namespace;
- `configuration.acceptedOutputModes` либо опускается, либо содержит настоящие MIME types.

Сервер фиксирует **negotiation snapshot на Task**, а не читает меняющиеся заголовки во время stream.

### 5.4. Выбор representation

`A2ARepresentationSelector` использует следующий детерминированный порядок:

1. A2UI URI активирован в `A2A-Extensions`;
2. `a2uiClientCapabilities` валиден;
3. клиент поддерживает server catalog ID и требуемые components/functions;
4. request policy/accepted MIME не запрещает `application/a2ui+json`;
5. UI effect может быть закодирован выбранной версией.

Если все условия выполняются — `representation=a2ui-0.9.1`. Иначе — `representation=generic-a2a`.

Выбор сохраняется в task projection. Mid-stream switching запрещён.

### 5.5. A2UI внутри стандартного Artifact

Иллюстрация локального A2A 1.0 wire (точные A2UI messages должны генерироваться codec из официальных schema fixtures):

```json
{
  "artifactUpdate": {
    "taskId": "task-42",
    "contextId": "ctx-7",
    "artifact": {
      "artifactId": "surface-main",
      "name": "ui.surface.main",
      "parts": [
        {
          "data": [
            {"createSurface": {"surfaceId": "main", "catalogId": "https://linnex.io/a2ui/catalog/platform/v1"}},
            {"updateComponents": {"surfaceId": "main", "components": []}},
            {"updateDataModel": {"surfaceId": "main", "path": "/", "value": {}}}
          ],
          "metadata": {"mimeType": "application/a2ui+json"}
        }
      ],
      "metadata": {
        "platformUi": {
          "documentId": "flow-ui:ctx-7",
          "baseRevision": 11,
          "revision": 12,
          "schemaVersion": 1,
          "representation": "a2ui-0.9.1"
        }
      },
      "extensions": ["https://a2ui.org/a2a-extension/a2ui/v0.9.1"]
    },
    "append": false,
    "lastChunk": true
  }
}
```

Здесь намеренно нет `kind`. MIME находится в Part metadata; extension URI остаётся стандартным Artifact extension.

### 5.6. Ordinary Artifact остаётся неизменным

```json
{
  "artifactUpdate": {
    "taskId": "task-42",
    "contextId": "ctx-7",
    "artifact": {
      "artifactId": "report-1",
      "name": "quarterly-report",
      "description": "Generated report and source data",
      "parts": [
        {"text": "Отчёт готов", "mediaType": "text/markdown"},
        {"url": "https://files.example/report.pdf", "filename": "report.pdf", "mediaType": "application/pdf"},
        {"data": {"rows": 128, "quality": 0.97}, "mediaType": "application/json"}
      ],
      "metadata": {"producer": "external-agent"},
      "extensions": ["https://example.org/a2a/report/v1"]
    },
    "append": false,
    "lastChunk": true
  }
}
```

Сервер сохраняет этот envelope побайтно эквивалентно на уровне ProtoJSON semantics. Frontend показывает его через generic projector; ему не требуется A2UI.

### 5.7. Submit request

Для UI-клиента `platform.ui.submit` является A2UI user action внутри стандартного user Message. Иллюстрация:

```json
{
  "jsonrpc": "2.0",
  "id": "rpc-91",
  "method": "SendStreamingMessage",
  "params": {
    "message": {
      "messageId": "msg-91",
      "role": "ROLE_USER",
      "contextId": "ctx-7",
      "parts": [
        {
          "data": [
            {
              "userAction": {
                "name": "platform.ui.submit",
                "surfaceId": "main",
                "sourceComponentId": "submit-order",
                "context": {"formId": "order-form"}
              }
            }
          ],
          "metadata": {"mimeType": "application/a2ui+json"}
        }
      ],
      "metadata": {
        "a2uiClientCapabilities": {},
        "a2uiClientDataModel": {
          "main": {
            "values": {"email": "user@example.com", "quantity": 2}
          }
        },
        "platformUi": {
          "documentId": "flow-ui:ctx-7",
          "revision": 12,
          "actionId": "action-unique-91"
        }
      }
    }
  }
}
```

Точное поле `userAction` и capability payload должны сериализоваться official codec; пример задаёт платформенные инварианты, а не заменяет schema.

### 5.8. Namespace ownership data model

Для каждой surface data model разделён на три пространства:

```text
/content   — agent-owned display data
/values    — user-editable component values
/system    — runtime/task/provenance/navigation state
```

Сервер при submit:

- принимает от клиента только разрешённые paths внутри `/values`;
- пересобирает `/content` и `/system` из своей текущей ревизии;
- проверяет schema каждого binding;
- отбрасывает unknown component IDs/paths;
- не доверяет client-side validation;
- фиксирует accepted patch и interaction в durable ledger;
- возвращает conflict при stale revision, не молча перетирает state.

### 5.9. Совместимость A2UI spec header naming

В документах A2UI встречается `X-A2A-Extensions`, тогда как A2A extension contract использует `A2A-Extensions`. Для проекта канон:

- отправлять и принимать `A2A-Extensions`;
- добавить его в embed CORS allow headers;
- не добавлять постоянный legacy `X-` alias без отдельного подтверждённого interop test;
- если конкретный внешний A2UI client требует `X-A2A-Extensions`, поддержка реализуется только в versioned HTTP boundary adapter и не проникает в domain/runtime.

### 5.10. Generic fallback для UI effect

Если UI effect создан, но Task не negotiated A2UI, `GenericUIRepresentationEncoder` формирует **только стандартные A2A Parts**:

1. строит доступное semantic text/Markdown представление изменившейся surface;
2. сохраняет ссылки/файлы как `url`/`raw` Parts без преобразования их identity;
3. при допустимом `application/json` может добавить один `data` Part с declarative snapshot для machine client;
4. ставит обычный Artifact name/description и platform provenance metadata;
5. не ставит A2UI MIME/extension и не требует знания platform catalog;
6. не отправляет этот fallback тому же клиенту рядом с A2UI copy.

Fallback encoder не пытается передать layout в произвольном HTML. Его минимальная гарантия — meaningful accessible content и стандартные machine-readable Parts. Уже существующие ordinary artifacts не проходят через encoder и остаются byte/semantic-equivalent.

### 5.11. UI bootstrap и восстановление тоже идут через A2A

`/interface-profile` не становится вторым каналом доставки страниц. Он отдаёт только control-plane данные, которые не являются разговором с flow: viewer permissions, embed look, locale policy, catalog/capability hints. Template, runtime values и UI patches через него не передаются.

Runtime bootstrap:

1. новый `<platform-flow-ui>` создаёт/восстанавливает `contextId`;
2. если известен последний `taskId`, вызывает стандартный `GetTask`/`SubscribeToTask` и применяет UI artifacts;
3. если Task неизвестен либо нужен authoritative current snapshot, отправляет A2A extension control Message `platform.ui.bootstrap` с capabilities/context;
4. server materializes или читает `ExecutionState.ui_document`, создаёт короткий A2A bootstrap Task и возвращает full A2UI либо generic snapshot Artifact;
5. graph/flow nodes при bootstrap **не запускаются**;
6. повторный bootstrap идемпотентен по `actionId`/document revision;
7. только последующий `platform.ui.submit` начинает/resumes graph execution.

`platform.ui.bootstrap` не является editor component action и не появляется в пользовательском catalog. Это versioned control command внутри optional A2UI extension, а не REST UI protocol. Ordinary A2A clients его не используют.

### 5.12. A2A autosync: состояние сохраняется до Submit

Чтобы закрытый или расшаренный экран действительно открылся с теми же заполненными данными, недостаточно передавать data model только в `platform.ui.submit`. Ввод и session-owned navigation синхронизируются отдельной control-командой `platform.ui.sync` внутри того же A2A/A2UI extension.

Контракт sync:

```text
platform.ui.sync
  contextId / documentId
  baseRevision
  clientMutationId
  changed /values paths (либо compact data-model patch)
  explicit allowlisted view state:
    activePageId
    active tabs
    opened session-owned surfaces/modals
    expanded/collapsed component state marked durable by the template
```

Правила:

- sync идёт стандартным A2A `Message` через `SendMessage`/`SendStreamingMessage`; отдельного REST save-state endpoint нет;
- server возвращает стандартный A2A `Message` acknowledgement либо control Task с accepted revision; graph nodes не запускаются;
- server применяет только `/values` и отдельный allowlist session-owned view state; произвольная запись `/content`/`/system` запрещена;
- изменения группируются debounce, но немедленно flushятся на blur, page navigation, перед share и перед Submit;
- Submit включает полный разрешённый data model и атомарно выполняет последний sync + `BeginInteractionTurn`, поэтому race между autosave и запуском flow невозможен;
- создание share-link блокируется, пока текущий `clientMutationId` не подтверждён server revision;
- `pagehide`/`visibilitychange` выполняют best-effort keepalive flush, но correctness не зависит только от ненадёжного unload event;
- frontend держит локальный encrypted/origin-scoped pending mutation journal (например IndexedDB) для abrupt offline close и повторяет его после reopen с OCC;
- UI явно показывает `Saving… / Saved / Offline changes`, чтобы пользователь понимал, какая ревизия доступна другому устройству;
- другой браузер/share viewer всегда видит последнюю **server-acknowledged** ревизию; неподтверждённый keystroke после физического обрыва сети невозможно обещать удалённому устройству и он остаётся только в local recovery journal;
- sync idempotent по `(contextId, clientMutationId)` и использует revision conflict/rebase, а не last-write-wins.

Значения и view state, созданные самим Flow в ответе, уже durable и не нуждаются в обратном client sync. Template/schema обновление опубликованного Flow не сбрасывает существующую session автоматически: она продолжает использовать сохранённые `ui_template_version` и document, пока явно не выполнена versioned UI migration/reset.

---

## 6. Compatibility matrix

| Клиент/источник | Вход | Выход | UI поведение | Требуемая гарантия |
|---|---|---|---|---|
| Обычный A2A client | любые `text/raw/url/data` Parts | обычные Task/Message/Artifacts | не требуется | ни один Part/metadata/extension не теряется |
| Текущий platform client во время миграции | text + file URL + metadata | текущие именованные artifacts | новый generic projector | визуальная функциональность не хуже текущей |
| Новый `<platform-flow-ui>` | A2UI submit + full data model | A2UI и ordinary artifacts | один reducer | full UI hydration/reconnect |
| Внешний A2UI A2A client | official v0.9.1 | negotiated A2UI | его renderer | без platform-private обязательных полей |
| Внешний A2A agent через `remote_flow` | произвольный Message/Task | произвольные artifacts | generic/A2UI projection | structured result проходит без text collapse |
| Embed | тот же A2A endpoint | тот же stream | universal renderer | origin/auth/locale/theme работают |
| Voice | ordinary text или A2UI submit | те же artifacts | renderer + TTS projector | нет отдельного voice protocol для flow |
| HITL/operator | обычные reply/file artifacts | Task resume/status | универсальная surface | takeover/reconnect сохраняются |
| Public search | URL/data Parts и platform artifacts | generic/A2UI | универсальные catalog components | custom `ui_event` больше не нужен |
| Reopen/reload/new device | bootstrap/GetTask с тем же context | full current document snapshot | atomic hydration без default flash | та же page, values, surfaces, tasks/artifacts |
| Share-link viewer | opaque share grant → тот же context/document | full current acknowledged revision | read-only либо collaborator mode | share не создаёт пустую session и ждёт autosync |

### 6.1. Запрещённые деградации

- ordinary client не обязан понимать A2UI, чтобы вызвать flow;
- наличие A2UI не должно скрывать unknown Artifact;
- `SendMessage` и `SendStreamingMessage` не могут возвращать разные итоговые artifacts;
- `GetTask` после рестарта не может возвращать меньше, чем видел stream;
- renderer не может считать unknown data ошибкой всего Task;
- malformed A2UI Part изолируется на уровне Part/Artifact, остальные события продолжают применяться;
- UI-capable client не получает два одинаковых ответа из status message и response artifact.

---

## 7. Task, context и lifecycle

### 7.1. Идентичности

- `contextId` — долгоживущий conversation/UI context.
- `session_id = {flow_id}:{context_id}` — durable workflow instance.
- `taskId` — один A2A run/interaction.
- `messageId` — immutable входное сообщение.
- `artifactId` — immutable identity одного output artifact внутри Task.
- `documentId` — UI document контекста; по умолчанию `flow-ui:{context_id}`.
- `surfaceId` и `componentId` стабильны внутри document.

### 7.2. Создание нового Task

- Первое ordinary Message или UI Submit без active resume target создаёт новый Task ID.
- Следующий submit после terminal Task создаёт новый Task ID с тем же context.
- Task получает snapshot negotiated extensions, flow config version, interface template version и starting UI revision.
- `workflow_instances.task_id` остаётся только указателем на active/latest task, а не единственным хранилищем истории.

### 7.3. Resume

- Если Task находится в `INPUT_REQUIRED`/`AUTH_REQUIRED` и Message ссылается на этот `taskId`, продолжается тот же Task.
- Stale/terminal task resume отклоняется стандартной A2A ошибкой; автоматически переносить ответ в новый Task нельзя.
- HITL takeover, OAuth и breakpoint сохраняют существующую semantics, но читают/пишут task projection.

### 7.4. Terminal boundary

- `COMPLETED`, `FAILED`, `CANCELED`, `REJECTED` закрывают Task.
- `INPUT_REQUIRED`/`AUTH_REQUIRED` являются paused/interrupted boundary; subscription может быть продолжена согласно текущей platform policy.
- Конец LLM chunk/node не закрывает Task.
- `emit_complete` не дублирует уже опубликованный response: terminal status может не содержать message, если ответ materialized в Artifact; policy централизована.

### 7.5. `GetTask`

`GetTask(id=taskId)` читает `a2a_task_projections`, messages и artifacts. Он:

- возвращает точный последний status;
- применяет `historyLength` только к history, не к artifacts;
- сохраняет Artifact order;
- возвращает accumulated Parts после append;
- возвращает metadata/extensions;
- не перестраивает output из `state.response`.

Текущий convenience lookup по context при необходимости сохраняется как явно названный repository method `get_latest_for_context`, но не смешивается с стандартным `GetTask.id` и не используется внутри conformance path.

### 7.6. `ListTasks`

- Читает collection task projections, а не workflow instance list.
- Поддерживает фильтры context/status/created time и стабильную cursor pagination.
- Сортировка `(created_at DESC, task_id DESC)`.
- Авторизация и company/flow isolation применяются до pagination.

### 7.7. `SubscribeToTask` и reconnect

1. Клиент передаёт task ID и опциональный `afterSequence` в platform metadata extension.
2. Сервер читает durable snapshot на sequence `N`.
3. Отдаёт Task snapshot.
4. Реплеит durable task events `(afterSequence, N]`, если они нужны.
5. Подписывается на live events после `N`.
6. Дедуплицирует по `(taskId, sequence)`.

Redis остаётся low-latency fan-out, но не источником истины. Потеря Pub/Sub event не приводит к потере Task output.

### 7.8. Новый turn в существующем durable context

При submit после terminal Task выполняется отдельная domain command `BeginInteractionTurn`:

- открывает новый `A2ATaskOpened` с новым task ID;
- меняет только active/latest task pointer в workflow instance/state;
- очищает run-scoped `terminal_task_state`, `terminal_task_error`, `response`, current node/execution transient fields согласно mutation policy;
- сохраняет `ui_document`, accepted `/values`, conversation messages, files и разрешённые durable variables;
- записывает новый input Message с новым task ID;
- materializes flow entry/current nodes для нового run;
- не мутирует status/history/artifacts прошлого Task;
- выполняется одной durable transaction с idempotent submit acceptance.

Точный список preserved/reset fields закрепляется table-driven unit test на `ExecutionState`, чтобы UI persistence не зависела от случайного `model_copy`.

### 7.9. Session continuity: close, reopen и share

#### Reopen/reload

- UI route/session descriptor сохраняет или безопасно резолвит `flowId`, `contextId`, последний известный `taskId`, `documentId` и `revision`.
- На mount renderer сначала показывает neutral skeleton, а не default chat/template.
- Bootstrap загружает authoritative server snapshot и проверяет document/catalog/schema version.
- Snapshot атомарно заменяет local materialized document; только после этого монтируются пользовательские surfaces.
- Если local recovery journal содержит более новые неподтверждённые mutations, они OCC-rebase/apply после server snapshot и отправляются на sync.
- При отсутствии разрешения/удалённой session показывается explicit access/not-found state; нельзя молча создать новый context и показать пустую страницу.

#### Share

- Share URL содержит opaque, revocable, expiring grant; raw company secret/JWT в URL запрещён.
- Grant server-side связан с `{company_id, flow_id, context_id, document_id}` и permission mode `viewer|collaborator`.
- Перед выдачей URL инициатор обязан дождаться autosync acknowledgement текущей revision.
- Открытие URL резолвит **тот же** context/document и выполняет A2A bootstrap под scoped share identity.
- `viewer` получает полный экран/данные, но не может sync/submit/cancel или видеть fields, запрещённые share policy.
- `collaborator` может менять разрешённые `/values`; concurrency использует revision/OCC, idempotent mutations и conflict UX.
- Share не fork/clone. Отдельное действие «Создать копию» должно явно создавать новый context/document с provenance и новой identity.
- Revocation немедленно запрещает новый bootstrap/reconnect; уже открытый клиент теряет право при следующем sync/stream auth check.

#### Что означает «тот же экран»

Durable/shared:

- active page и route внутри Flow UI;
- существующие pages/surfaces/component tree и их ordering;
- `/content`, `/values`, разрешённый `/system` projection;
- selected tabs, opened durable modal/surface, expanded panels, если component manifest помечает state как `session`;
- task order/status, accumulated Artifacts и conversation/feed content;
- Flow-created validation/errors/progress и последняя accepted revision.

Viewer-local и не переносится другому пользователю/устройству:

- hover, current keyboard focus/caret/selection;
- pixel scroll position, если компонент явно не помечен как resumable;
- viewport size, reduced-motion/high-contrast preference;
- editor-only component selection/drag state;
- локальные audio playback и microphone state.

Для того же пользователя на том же устройстве viewer-local scroll/focus может best-effort восстанавливаться из local storage, но он не входит в canonical shared `FlowUIDocument` и не вызывает cross-device UI jumps.

---

## 8. Lossless Artifact accumulator

Одна реализация используется:

- blocking `SendMessage`;
- durable task projector;
- initial/reconnect snapshot;
- frontend A2A reducer;
- push notification verification tests;
- external A2A client parser.

### 8.1. Ключ и ordering

- key: `(taskId, artifactId)`;
- Artifact first-seen order фиксируется `ordinal`;
- Part order сохраняется;
- unknown fields, metadata и extensions сохраняются через protobuf/ProtoJSON codec;
- `artifactId` обязателен; отсутствие — protocol validation error, а не случайный UUID при чтении.

### 8.2. `append=false`

- текущий snapshot Artifact заменяется полным incoming Artifact;
- ordinal остаётся прежним;
- revision увеличивается;
- `lastChunk` обновляется;
- replacement не создаёт второй visual block.

### 8.3. `append=true`

- если Artifact ещё не известен, создаётся initial snapshot с incoming Parts;
- если известен, incoming Parts дописываются к existing Parts;
- identity/name invariants проверяются;
- Artifact metadata/description обновляются только по документированному merge rule;
- conflicting identity/name фиксируется как conformance violation;
- stable emitter обязан использовать тот же `artifactId`.

Перед реализацией merge rule сверяется с pinned A2A 1.0 schema/spec; frontend и backend используют одинаковые golden fixtures.

### 8.4. `lastChunk`

- хранится per artifact;
- запрещает дальнейший append, кроме idempotent duplicate;
- terminal Task может содержать artifacts без `lastChunk=true`, но emitter lint предупреждает;
- для одноразового Artifact emitter сразу выставляет `lastChunk=true`.

### 8.5. Idempotency

- каждому published event назначается monotonic `platformSequence` внутри Task;
- projection имеет unique `(company_id, task_id, sequence)`;
- duplicate sequence с тем же payload hash — no-op;
- duplicate sequence с другим hash — hard error + security log;
- `actionId` submit имеет unique constraint на context/document, чтобы browser retry не запускал flow дважды.

### 8.6. Stable emitter IDs

`BaseEmitter` получает task-scoped registry logical keys:

```text
response                 -> one stable artifactId per Task
reasoning                -> one stable artifactId per Task
operator_reply:<turn>    -> stable per operator turn
tool_call:<call_id>      -> stable per tool call
tool_result:<call_id>    -> stable per tool result
ui_surface:<surface_id>  -> stable per surface
```

Random UUID создаётся один раз при первом emit logical artifact, а не на каждый chunk.

---

## 9. Generic A2A Part → trusted UI projection

### 9.1. Общие правила

- Projection не меняет сохранённый Artifact.
- Каждый render node хранит provenance на оригинальный task/artifact/part.
- Adapter выбирается по explicit MIME/schema/name; unsafe inference запрещён.
- Unknown part всегда имеет безопасный fallback, а не исчезает.
- Policy может скрыть diagnostics визуально, но lossless A2A store продолжает их хранить.

### 9.2. Mapping Parts

| Part | Условие | Trusted component | Fallback |
|---|---|---|---|
| `text` | `text/markdown` или platform response | `Markdown` | escaped `Text` |
| `text` | другой/нет MIME | `Text`/`Preformatted` | escaped `Text` |
| `raw` | image MIME | `Image` с object URL | `FileCard` |
| `raw` | audio/video MIME | `AudioPlayer`/`Video` | `FileCard` |
| `raw` | документ/unknown | `FileCard` | metadata + download |
| `url` | image MIME | sanitized `Image` | `FileCard` |
| `url` | audio/video | player | `FileCard` |
| `url` | document/unknown | `FileCard` | safe external link |
| `data` | MIME `application/a2ui+json` | A2UI codec | isolated invalid-artifact card |
| `data` | known platform schema | named catalog adapter | `JsonInspector` |
| `data` | arbitrary JSON | `JsonInspector` | downloadable JSON |

Browser-originated files по-прежнему загружаются через Files API и отправляются как `Part.url`; `Part.raw` сохраняется для external/conformance clients.

### 9.3. Adapters текущих именованных artifacts

Создаются explicit adapters, а не `if`-ветви в root component:

- `response` → transcript/content slot;
- `reasoning` → collapsible `Reasoning` при разрешённой policy;
- `tool_call_*` + `tool_result_*` → `ToolActivity` с correlation;
- `node_*`/`edge_*` → `RunTrace` и editor canvas events;
- `operator_reply`/`user_message` → conversation feed;
- `operator_files` → `FileList`;
- `artifact` `{content}` → `JsonInspector`/Markdown по explicit metadata;
- browser preview, skill load, reflection, handoff и current custom blocks получают собственные catalog adapters или A2UI effects до удаления `ui_event`.

### 9.4. Artifact grouping

- UI группирует Parts внутри одного Artifact;
- append обновляет существующий block без скачка scroll/duplicate bubble;
- Artifact name/description могут отображаться как header;
- metadata/extensions доступны в developer inspector, но не раскрывают secrets;
- mixed Parts показываются в исходном порядке.

---

## 10. Flow UI domain model

### 10.1. Materialized document

Предлагаемый version-neutral контракт:

```text
FlowUIDocument
  schema_version: 1
  document_id: str
  revision: int
  template_version: str
  catalog_id: str
  active_page_id: str
  session_view_state: object
  last_accepted_client_mutation_id: str | None
  pages: ordered map[page_id, FlowUIPage]
  surfaces: ordered map[surface_id, FlowUISurface]
  global_data_model:
    content: object
    values: object
    system: object
  policy: FlowInterfacePolicySnapshot

FlowUIPage
  page_id: str
  title: LocalizedText
  route: str
  root_surface_id: str
  navigation: PageNavigationPolicy
  default_target_profile_id: str

FlowUISurface
  surface_id: str
  catalog_id: str
  root_component_id: str
  components: ordered map[component_id, FlowUIComponent]
  data_model: {content, values, system}
  owner: agent|platform
  send_data_model: bool

FlowUIComponent
  component_id: str
  type: trusted catalog component type
  properties: typed object
  children: ordered component references
  container_layout: FlowUIContainerLayout | None
  placement: FlowUIResponsivePlacement
  bindings: typed JSON Pointer bindings
  actions: typed local/event actions
  visibility/checks: typed expressions from allowlisted function catalog
  provenance: optional A2A reference
```

### 10.1.1. Layout grid является persisted domain contract

`Grid` в toolbar — не editor-only фон. Layout хранится рядом с component tree, проходит schema validation, semantic delta, durable replay, A2UI codec и renderer. Минимальный version-neutral контракт:

```text
FlowUIContainerLayout
  mode: grid | stack | flex
  grid: FlowUIGridDefinition | None
  stack: FlowUIStackDefinition | None
  flex: FlowUIFlexDefinition | None

FlowUIGridDefinition
  columns_by_band:
    compact: int       # default preset: 4
    medium: int        # default preset: 8
    wide: int          # default preset: 12
  column_gap_token: DesignTokenRef
  row_gap_token: DesignTokenRef
  outer_padding_inline_token: DesignTokenRef
  outer_padding_block_token: DesignTokenRef
  max_content_width: BoundedLength | DesignTokenRef | none
  auto_rows: content | equal | BoundedLength
  auto_flow: row | column
  align_items: start | center | end | stretch
  justify_items: start | center | end | stretch
  baseline_step_token: DesignTokenRef

FlowUIResponsivePlacement
  base: FlowUIPlacement
  overrides: ordered map[container_band, FlowUIPlacementPatch]

FlowUIPlacement
  column_start: auto | positive int
  column_span: positive int | full
  row_start: auto | positive int
  row_span: positive int
  order: int
  align_self: auto | start | center | end | stretch
  justify_self: auto | start | center | end | stretch
  min_inline_size/max_inline_size: BoundedLength | none
```

Инварианты:

- `compact|medium|wide` — semantic container bands из versioned catalog manifest; renderer использует container queries, а не user-agent/device-name sniffing. Начальный platform preset — 4/8/12 колонок; thresholds меняются только versioned manifest migration.
- Toolbar presets `Mobile 390×844`, `Mobile 430×932`, `Tablet`, `Desktop 1440×1024` задают точный inner viewport production frame, но не создают отдельные component trees.
- Вложенные `Grid`/`Section` допустимы; placement ребёнка относится только к его непосредственному container. Validator запрещает span больше числа колонок, циклы, overlap в режимах без явного overlay и несуществующие bands.
- Gaps, padding, typography, radii и shadows выбираются по semantic design-token refs. Свободная CSS-строка, `style`, media query или произвольный pixel literal из flow/editor не проходят schema.
- Absolute positioning запрещён для обычного layout. Если продукту действительно нужен canvas/overlay, это отдельный trusted catalog component с bounded coordinates, clipping, stacking и accessibility policy; он не маскируется под `Grid`.
- Guide/ruler visibility, overlay opacity, selection, editor zoom и snap preferences являются transient `flows/interface_editor` state. Columns/spans/gaps/margins/breakpoint overrides являются document state и поэтому 1:1 доходят до пользователя.
- Editor zoom масштабирует frame снаружи; он не меняет CSS viewport внутри renderer. Геометрическая проверка и `Exact` fingerprint считаются по внутренним CSS pixels, а не по увеличенной картинке.

### 10.2. Почему это не raw A2UI JSON

- A2UI v0.9.1 и v1.0 имеют разные wire messages;
- editor нуждается в normalized pages/layers/selection;
- state delta должен адресовать components/data paths;
- domain validator должен работать без frontend SDK;
- durable replay не должен зависеть от npm package internals.

Codec — единственное место преобразования domain document ↔ official messages.

### 10.3. Runtime state поля

В `ExecutionState` добавляются frozen system fields:

- `ui_document: FlowUIDocument`;
- `ui_interaction: FlowUIInteraction | None` — последняя принятая команда текущего run;
- `ui_effect_cursor: int` — позиция применённых trusted effects;
- `ui_template_version: str`;
- `ui_last_synced_at` и `ui_last_accepted_client_mutation_id` для autosync/idempotent recovery;
- при необходимости `ui_conflict: FlowUIConflict | None` только для controlled interrupt.

Удаляются:

- `ui_events_pending`;
- `PendingUIEvent`;
- любые extra-поля с chat-only blocks.

`content`, `response`, `messages`, `files` сохраняются как execution/A2A compatibility projections. Они не являются canonical UI state:

- ordinary text input продолжает заполнять `content`;
- UI submit получает deterministic textual summary для `content`, только если flow/node ожидает строку;
- original structured interaction остаётся в `ui_interaction`;
- `response` может поддерживать существующие nodes, но transport artifacts строятся не из него задним числом.

### 10.4. UI interaction

```text
FlowUIInteraction
  interaction_id/action_id
  task_id/context_id/message_id
  document_id/base_revision/accepted_revision
  action_name = platform.ui.submit
  surface_id/source_component_id
  form_id/page_id
  values_patch
  validated_values_snapshot
  original_message (lossless A2A reference or ProtoJSON)
  submitted_at
```

Secrets, hidden system data и неразрешённые client paths в interaction не сохраняются.

### 10.5. Revision/OCC

- revision начинается с 1 при materialization template;
- каждый accepted UI command/effect увеличивает revision ровно один раз;
- artifact metadata содержит `baseRevision` и `revision`;
- submit с меньшей revision получает controlled conflict response и current revision patch;
- submit с большей неизвестной revision отклоняется;
- duplicate `actionId` возвращает прежний Task/result;
- чисто viewer-local действия не меняют server revision;
- изменение `/values` или session-owned navigation сначала становится pending local mutation, а после `platform.ui.sync` увеличивает server revision;
- server acknowledgement содержит accepted revision и mutation ID; только эта ревизия считается доступной reopen/share viewers;
- reconnect с pending local journal выполняет OCC rebase, не перетирает более новую server revision.

### 10.6. Semantic UI delta

`ExecutionStateDelta` расширяется:

```text
ui_components_upsert: map[surface_id, map[component_id, component]]
ui_components_delete: map[surface_id, list[component_id]]
ui_component_properties_set/delete
ui_container_layout_set/unset
ui_component_placement_set/unset
ui_data_set: list[{surface_id, path, value}]
ui_data_delete: list[{surface_id, path}]
ui_surfaces_upsert/delete
ui_pages_upsert/delete
ui_active_page_set
ui_session_view_state_set/delete
ui_revision_set
ui_interaction_set/unset
ui_last_client_mutation_set
```

Raw whole `ui_document` через `fields_set` разрешён только при initial materialization/schema migration/snapshot restore. Обычные runtime updates обязаны использовать semantic delta.

### 10.7. Authoritative hydration snapshot

Для bootstrap repository/service формирует `FlowUISessionSnapshot`:

```text
FlowUISessionSnapshot
  flow_id / branch_id / context_id / session_id
  document: полный FlowUIDocument текущей accepted revision
  active_task_id / latest_task_id
  tasks: ordered Task projections according to hydration policy
  artifacts: accumulated exact Artifact projections
  viewer_permissions
  snapshot_sequence / state_hash
  generated_at
```

- Snapshot читается согласованно на одном durable sequence; нельзя смешать document revision N с artifacts N-1.
- UI не собирает current screen повторно из greeting/config/history и не применяет default template поверх snapshot.
- Если task/artifact history слишком велика, snapshot содержит current document целиком и paginated task window + continuation cursor; видимый экран не зависит от загрузки всей старой истории.
- Share policy может redact запрещённые data paths/artifacts, но после redaction выдаётся self-consistent viewer-specific snapshot с отдельным hash.
- Hydration считается завершённой только после schema/catalog validation и atomic store commit.

---

## 11. A2UI codec и message application

### 11.1. Version boundary

Создаётся interface:

```text
A2UICodec
  version_uri
  mime_type
  validate_client_capabilities()
  decode_client_action(part, metadata)
  encode_document_snapshot(document)
  encode_effect_batch(before, after)
  apply_agent_message_batch(document, messages)
```

Первая реализация — `A2UI091Codec`. Registry выбирает codec только по negotiated URI.

### 11.2. Batch application

Согласно A2UI v0.9.1:

- messages внутри DataPart применяются последовательно;
- пакет не является транзакцией «всё или ничего»;
- invalid message логируется и изолируется, следующие сообщения продолжают применяться;
- DOM repaint выполняется один раз после обработки batch;
- `deleteSurface` очищает surface и bindings;
- JSON Pointer обрабатывается по RFC 6901 с тестами `~0`/`~1`.

Durable server-side effect application, напротив, сначала валидирует command batch и фиксирует одну revision; wire codec затем формирует A2UI sequence. Это предотвращает частично сохранённый серверный документ.

### 11.3. Snapshot vs patch

- новый context/reconnect без known revision → full `createSurface + components + data` snapshot;
- обычный ответ → минимальный diff batch;
- gap/stale client → full surface replacement;
- surface Artifact сохраняет один stable ID;
- maximum patch size и maximum component count контролируются policy;
- большие datasets передаются URL/file artifact + paged component, не встраиваются целиком в UI data.

### 11.4. Catalog negotiation

- platform catalog ID versioned и immutable: `https://linnex.io/a2ui/catalog/platform/v1` независимо от текущего brand host;
- basic A2UI component behavior соответствует v0.9.1 guide;
- platform components декларируют JSON Schema properties/bindings/actions;
- persisted `container_layout`/`placement` кодируются как typed properties platform catalog components внутри обычных A2UI `updateComponents`; отдельного layout message/protocol не вводится;
- editor-only guides/zoom/selection никогда не кодируются в A2UI и не попадают в durable document;
- unsupported component не приводит к произвольной загрузке кода: codec выбирает fallback component;
- catalog manifest доступен renderer/editor из одной локальной registry;
- server validation использует сгенерированный из того же manifest schema artifact.

---

## 12. Trusted platform effects вместо `ui_events_pending`

### 12.1. Новый side channel

В `core/capabilities/models.py` вводится discriminated union `PlatformEffect`:

```text
UIApplyEffect
  kind = "ui.apply"
  commands: list[FlowUICommand]
  expected_revision: int | None

UINavigateEffect
  kind = "ui.navigate"
  page_id: str

UIResetEffect
  kind = "ui.reset"
  template_id/version
```

`CapabilityCallResponse` и `CodeExecutionResponse` получают `platform_effects: list[PlatformEffect]`.

### 12.2. Capability API

Вместо `state.push_ui_event`, `state.push_ui_events`, `state.pop_ui_events` публикуются typed capabilities:

- `ui.create_surface`;
- `ui.update_components`;
- `ui.update_data`;
- `ui.delete_surface`;
- `ui.navigate`;
- при необходимости низкоуровневый `ui.apply` только для trusted platform tools.

Каждая capability:

- имеет строгую input JSON Schema;
- возвращает domain command/effect, а не мутированный state;
- не принимает raw HTML/JS;
- не позволяет писать `/system` и чужие surfaces;
- связывает effect с execution token, node/tool ID, task/context и causation ID.

### 12.3. Language runners

Python/Node/Go/C# harness:

1. принимает capability response;
2. возвращает `result/state/interrupt` как сейчас;
3. собирает `platform_effects` отдельно;
4. не помещает effects в user state;
5. подписывает/связывает их с текущим capability request ID;
6. host отвергает effect, которого нет в capability response chain.

### 12.4. Host application

`RemoteCodeRunner` передаёт effects в `UIEffectApplier`, который:

- проверяет manifest permission;
- проверяет task/context/node ownership;
- валидирует schemas, component catalog и bindings;
- проверяет expected revision;
- применяет semantic delta;
- пишет durable `UIDocumentPatched` event;
- отдаёт representation layer A2UI/generic output;
- только после durable commit публикует A2A stream event.

Пользовательский returned state больше не способен подделать UI update.

---

## 13. Durable A2A task/artifact projection

### 13.1. Источник истины

Append-only `workflow_events` остаётся canonical ledger. Добавляются event types:

- `A2ATaskOpened`;
- `A2AMessageAppended` либо расширяется текущий `ConversationMessageAppended` с task identity;
- `A2AArtifactUpdated`;
- `A2ATaskStatusChanged`;
- `UIInteractionAccepted`;
- `UIDocumentPatched`;
- `UIRepresentationSelected`.

Payload `A2AArtifactUpdated` содержит exact ProtoJSON `TaskArtifactUpdateEvent`, sequence и payload hash. Projection tables rebuildable из ledger.

### 13.2. Query projection tables

Новая flows migration создаёт:

#### `a2a_task_projections`

- `company_id`, `flow_id`, `context_id`, `session_id`;
- `task_id` primary/unique in company scope;
- `execution_branch_id`;
- `status_json JSONB`;
- `status_state` indexed;
- `task_metadata JSONB`;
- `negotiated_extensions JSONB`;
- `representation`;
- `latest_sequence`;
- `terminal`, `created_at`, `updated_at`, `completed_at`;
- `input_message_id`, `flow_config_version`, `ui_template_version`.

Indexes:

- unique `(company_id, task_id)`;
- `(company_id, flow_id, context_id, created_at DESC)`;
- `(company_id, flow_id, status_state, updated_at DESC)`;
- `(company_id, session_id, created_at DESC)`.

#### `a2a_task_messages`

- company/task/message ID;
- `ordinal`;
- exact `message_json JSONB`;
- role, created_at;
- unique `(company_id, task_id, message_id)` и `(company_id, task_id, ordinal)`.

#### `a2a_artifact_projections`

- company/task/artifact ID;
- `ordinal`;
- exact accumulated `artifact_json JSONB`;
- `revision`, `last_chunk`, `latest_sequence`;
- `payload_hash`, timestamps;
- unique `(company_id, task_id, artifact_id)` и `(company_id, task_id, ordinal)`.

#### `a2a_task_event_dedup`

Если unique sequence нельзя выразить безопасно в task table, отдельная лёгкая projection/dedup table:

- `(company_id, task_id, sequence)` unique;
- payload hash, workflow event ID.

#### `flow_ui_share_grants`

- `grant_id` primary key;
- `company_id`, `flow_id`, `context_id`, `document_id`;
- `permission` (`viewer|collaborator`);
- `scope_json` для разрешённых pages/data paths/artifact classes;
- `created_by`, `created_at`, `expires_at`, `revoked_at`;
- `minimum_shared_revision` — ревизия, подтверждённая перед созданием ссылки;
- indexes `(company_id, flow_id, context_id)`, `(expires_at)`, `(created_by, created_at)`;
- grant хранит identity/permissions, но не копию document: shared screen остаётся live-проекцией того же context.

### 13.3. Commit/publication order

```text
domain command
  -> append workflow event + state delta
  -> update A2A/UI query projections in same DB transaction
  -> commit
  -> publish exact StreamResponse to Redis/push
```

При падении после commit и до publish reconnect получает snapshot из DB. Для live latency используется transactional outbox либо recovery publisher; нельзя публиковать в Redis до durable commit.

### 13.4. Raw/file size

- exact ordinary `raw` Part поддерживается в пределах A2A request/output limits;
- server-generated крупные blobs должны использовать Files/S3 и `Part.url`;
- migration не преобразует внешний `raw` в `url` незаметно для клиента;
- task JSONB limits, base64 amplification и rejection error тестируются;
- secrets из metadata перед persistence проходят existing redaction policy, но wire-relevant public metadata не удаляется.

### 13.5. Fork/rewind

- UI document участвует в state fork/rewind как любая durable projection;
- уже опубликованный A2A Task immutable: rewind создаёт новую execution branch/new Task, а не переписывает старый terminal Task;
- lineage сохраняется в task metadata (`parentTaskId`, branch ID) как platform extension;
- rebuilt query projections выбирают events активной ветви для нового Task, но исторические Task snapshots не исчезают.

### 13.6. Share grant не является snapshot fork

- Создание grant выполняется после durable `platform.ui.sync` и записывает `minimum_shared_revision`.
- Short-link payload содержит только `grant_id`, не UI data и не постоянный JWT.
- Обмен short-link на scoped session token проверяет expiry/revocation/grant scope и current session existence.
- A2A bootstrap под grant читает current document той же session; последующие изменения owner/collaborators видны после их accepted revisions.
- Если нужен замороженный исторический экран, это отдельная будущая сущность `snapshot share`; она не должна случайно подменять live session sharing.

---

## 14. Backend target structure и file-by-file изменения

Легенда: `CREATE`, `MODIFY`, `MOVE`, `DELETE`, `KEEP`.

### 14.1. Core A2A

| Действие | Файл | Изменение |
|---|---|---|
| CREATE | `core/a2a/artifact_accumulator.py` | Единственный protobuf-aware accumulator append/replace/lastChunk/order/idempotency. |
| CREATE | `core/a2a/extensions.py` | URI/MIME/header constants, parsed activation set, без UI domain imports. |
| CREATE | `core/a2a/task_projection.py` | Typed lossless Task snapshot и helpers для Task construction. |
| CREATE | `core/a2a/representation.py` | Enum/snapshot negotiated representation, не renderer. |
| MODIFY | `core/a2a/codec.py` | Artifact/Task/StreamResponse ProtoJSON helpers; строгий oneof; не добавлять новые wire models. |
| MODIFY | `core/a2a/task_json.py` | Оставить text compatibility helpers; добавить lossless iterators/parser, прекратить использовать text extractor как основной remote result. |
| MODIFY | `core/a2a/__init__.py` | Экспорты новых generic primitives. |
| KEEP | `core/a2a/methods.py` | Методы A2A не меняются. |
| KEEP/MODIFY tests only | official fixtures | Не переписывать; добавить A2UI fixtures рядом, но A2A 1.0 pin остаётся. |

### 14.2. Flow UI domain

| Действие | Файл | Изменение |
|---|---|---|
| CREATE | `core/models/flow_interface.py` | `FlowInterfaceConfig`, policy, template, branch/embed override models и merge/replace semantics. |
| CREATE | `core/state/flow_ui.py` | `FlowUIDocument`, page/surface/component/data model, typed `Grid/Stack/Flex`, responsive placement, interaction, commands, effects, validation. |
| CREATE | `core/state/flow_ui_delta.py` | Semantic data/component/layout delta application, responsive-grid invariants and deterministic replay checks. |
| CREATE | `core/a2ui/codec.py` | Codec protocol/registry. |
| CREATE | `core/a2ui/v0_9_1.py` | Official v0.9.1 encode/decode only. |
| CREATE | `core/a2ui/catalog_identity.py` | Один canonical Linnex catalog URI из `primary_platform_domain`; никогда не из request Host. |
| CREATE | `core/a2ui/schemas/` | Pinned official schema/fixtures + provenance/version checksum. |
| CREATE | `core/a2ui/catalog.py` | Catalog manifest types/validation, container bands, layout capability schemas and checksums; no frontend imports. |
| MODIFY | `core/state/execution_state.py` | Добавить frozen UI fields; удалить `PendingUIEvent/ui_events_pending`; сохранить A2A/messages/files. |
| MODIFY | `core/state/mutation_policy.py` | Новые UI fields frozen; запретить user returned-state mutations. |
| MODIFY | `core/state/__init__.py` | Экспорты; удалить PendingUIEvent. |
| KEEP/USE | `core/platform_brand/resolver.py`, `core/config/base.py` | Runtime URLs/branding остаются multi-domain; `primary_platform_domain=linnex.io` используется только для canonical identity. |
| DELETE | `core/models/flow_chat_settings.py` | После storage/API/frontend migration; не оставлять runtime alias. |
| MODIFY | `core/models/__init__.py` | Экспорт interface models вместо chat models. |

### 14.3. A2A channel/server

| Действие | Файл | Изменение |
|---|---|---|
| CREATE | `apps/flows/src/a2a/negotiation.py` | Parse AgentCard/client capabilities/headers; Task negotiation snapshot. |
| CREATE | `apps/flows/src/a2a/interaction_parser.py` | Ordinary Message или A2UI action → typed `FlowInteraction`; original Message сохраняется. |
| CREATE | `apps/flows/src/a2a/representation_service.py` | UI effects → A2UI Artifact либо generic fallback; current artifacts проходят unchanged. |
| CREATE | `apps/flows/src/a2a/task_projection_service.py` | Durable commit, accumulator, blocking/stream/GetTask parity. |
| MODIFY | `apps/flows/src/channels/a2a.py` | Удалить special `_build_task_from_events`; использовать shared task projector; structured input; negotiation; no text collapse. |
| MODIFY | `apps/flows/src/channels/base.py` | AgentCard extension; Get/List/Cancel/Subscribe через task repository; current workflow lookup отдельно. |
| MODIFY | `apps/flows/src/api/a2a.py` | Header propagation, interface-profile, auth matrices, A2A extension activation. |
| MODIFY | `apps/flows/src/middleware/embed_dynamic_cors.py` | `interface-profile` subpath; allow `A2A-Extensions`; сохранить A2A-Version/Accept/security headers. |
| MODIFY | `apps/flows/src/streaming/base.py` | Stable artifact IDs; generic artifact emit; UI effects через representation service; terminal no-dup policy; удалить `emit_ui_event`; проверить duplicate ping key/metadata. |
| MODIFY | `apps/flows/src/streaming/emitter.py` | Durable-before-publish sink; убрать override `emit_ui_event`. |
| MODIFY | `apps/flows/src/streaming/subscriber.py` | Sequence-aware reconnect/dedup; не менять standard StreamResponse. |
| DELETE | `apps/flows/src/streaming/ui_events.py` | После переноса всех producers на trusted effects. |
| MODIFY | `apps/flows/src/runtime_helpers/state_utils.py` | Удалить `push_ui_event(s)` helpers; оставить unrelated state helpers. |

### 14.4. Durable execution/database

| Действие | Файл | Изменение |
|---|---|---|
| MODIFY | `apps/flows/src/durable_execution/models.py` | Event types/payloads; semantic UI delta; task/artifact payloads. |
| MODIFY | `apps/flows/src/durable_execution/state_delta.py` | Deterministic UI delta apply/hash/replay. |
| MODIFY | durable runtime/service files found by references | Atomic append + projection update + outbox hook. |
| MODIFY | `apps/flows/src/db/models.py` | Task/message/artifact projection ORM models and indexes. |
| CREATE | `apps/flows/src/db/a2a_task_repository.py` | Task CRUD/query projection; no flow execution logic. |
| CREATE | `apps/flows/src/db/a2a_projection_rebuilder.py` | Rebuild projections from ledger for repair/tests. |
| CREATE | `migrations/flows/versions/20260804_0027_flow_ui_and_a2a_task_projection.py` | Проверенный flows head `20260721_0026`; создать task/message/artifact/share tables/indexes и FlowConfig storage transform. |
| CREATE | `migrations/shared/versions/20260804_0029_embed_interface_config.py` | Проверенный shared head `shared_0028` (`20260728_0028_calendar_integration_per_mailbox.py`); миграция `storage` embed configs. |
| MODIFY | `apps/flows/src/container.py` и runtime container | Зарегистрировать repositories/services/codecs без service locator в domain. |

### 14.5. Flow config/API

| Действие | Файл | Изменение |
|---|---|---|
| MODIFY | `apps/flows/src/models/flow_config.py` | `FlowConfig.interface`; `BranchConfig.interface_override`; удалить `chat`. |
| DELETE | `apps/flows/src/models/flow_chat_settings.py` | Удалить re-export после перехода imports. |
| MODIFY | `apps/flows/src/models/__init__.py` | Новые exports. |
| MODIFY | `apps/flows/src/api/v1/flows.py` | Create/update/response schemas для interface; strict validation. |
| MODIFY | `apps/flows/src/clients/flows_client.py` | Typed interface config in DTOs. |
| MODIFY | `apps/flows/src/clients/lara_client.py` | Если читает chat policy/UI events — перейти на interface/A2A artifacts. |
| CREATE | `apps/flows/src/services/flow_interface_service.py` | Template materialization, branch selection, policy resolution, submit invariant. |
| MODIFY | `apps/flows/src/services/embed_target_resolver.py` | `interface_override`, look, capability snapshot. |
| MODIFY | `core/models/embed_models.py` | `EmbedInterfaceOverride`, `EmbedInterfaceLook`; убрать chat types/serializer. |
| MODIFY | `apps/frontend/api/embed_configs.py` | Request/patch/response new names and validation. |
| MODIFY | `core/db/repositories/embed_config_repository.py` | Только model/import; storage prefix и public `embed_id` сохраняются. |
| MODIFY | `docs/openapi/flows.json`, `docs/openapi/frontend.json` | Регенерировать, не редактировать вручную как источник истины. |
| MODIFY | `docs/api/flows/intro.md`, `docs/scenarios/flows/CATALOG.md` | Общий Flow UI/A2A contract. |

### 14.6. External A2A / remote flow

| Действие | Файл | Изменение |
|---|---|---|
| MODIFY | `core/clients/a2a_client.py` | `send_message(Message/Parts)`, AgentCard negotiation, structured `A2ATaskResult` с Task/Artifacts; text — derived convenience only. |
| MODIFY | `apps/flows/src/runtime/nodes.py::RemoteFlowNode` | Сохранить/emit exact remote artifacts; A2UI passthrough/reprojection; не присваивать только `state.response`. |
| MODIFY | `tests/flows/core/clients/test_a2a_client.py` | All Parts/extensions/mixed artifacts/negotiation. |
| MODIFY | `.cursor/rules/integrations.mdc` | Remote Flow structured output и A2UI security/ownership. |

### 14.7. Capability gateway и все language runners

| Действие | Файл | Изменение |
|---|---|---|
| MODIFY | `core/capabilities/models.py` | Добавить strict `PlatformEffect` union и `platform_effects` в capability/code execution responses; определить ordering с interrupt/error. |
| MODIFY | `apps/capability_gateway/services/registry.py` | Удалить `state.push_ui_event(s)/pop_ui_events`; зарегистрировать typed `ui.*` capabilities; handlers возвращают effects, не state mutation. |
| MODIFY | `apps/capability_gateway/services/invoke_helpers.py` | Если helper формирует `CapabilityCallResponse`, сохранить effects/causation и schema validation. |
| MODIFY | `apps/capability_gateway/api/v1/capabilities.py` | Пропустить новое поле без private aliases; обновить OpenAPI/error contract. |
| MODIFY | `apps/code_runner_python/services/executor.py` | Worker harness на каждом capability call отделяет `platform_effects` от `state`, накапливает ordered list и возвращает его при completed/interrupted. |
| MODIFY | `apps/code_runner_node/services/executor.py` | То же; запретить `Object.assign(request.state, payload.platform_effects)`. |
| MODIFY | `apps/code_runner_go/services/executor.py` | То же в generated Go harness с typed JSON envelope. |
| MODIFY | `apps/code_runner_csharp/services/executor.py` | То же в generated C# SDK/worker envelope. |
| MODIFY | `apps/flows/src/runners/remote.py` | Проверять returned effects, causation/manifest/task ownership; передавать в `UIEffectApplier` до merge разрешённых user fields. |
| MODIFY | `apps/flows/src/runners/tool_context_view.py` | Удалить `ui_events_pending`; не раскрывать server-owned `ui_document` как mutable state; дать read-only/minimised UI summary только при необходимости. |
| MODIFY | `apps/flows/src/api/v1/code.py` | Удалить default `ui_events_pending`; обновить execution response/examples. |
| MODIFY | `apps/flows/src/runners/base.py`, `apps/flows/src/runners/__init__.py` | Типы/exports только если меняется abstract contract. |
| MODIFY | capability/code-runner tests | Одинаковые golden effects для Python/Node/Go/C#, forged effect/state attacks и interrupt ordering. |

Ordering rule должен быть один для всех языков:

1. capability effects сохраняются в порядке успешных capability responses;
2. failed capability не добавляет неполный effect;
3. при `interrupt` уже подтверждённые effects либо атомарно применяются до interrupt, либо все отклоняются — выбрать одну policy и закрепить golden tests; рекомендуемая policy: применить подтверждённые effects и interrupt в одном durable command transaction;
4. при runner crash после capability response idempotency key не позволяет применить effect повторно;
5. `state_returned` не влияет на effects.

### 14.8. Точный реестр текущих `ui_event` producers

Каждый файл ниже должен перейти на обычный Artifact либо trusted UI effect до удаления старого пути:

| Файл | Текущая роль | Целевое действие |
|---|---|---|
| `apps/flows/src/runtime/flow.py` | flush pending events после node result | Удалить flush; effects применяются/публикуются в command boundary. |
| `apps/flows/src/runtime/runners/llm_runner.py` | flush после tools/exit | Удалить flush; emitter получает уже committed effect/artifact. |
| `apps/flows/src/runtime_helpers/state_utils.py` | создаёт `PendingUIEvent` | Удалить UI helpers; заменить callers typed service/capability. |
| `apps/flows/src/services/browser_preview.py` | browser preview UI event | `BrowserPreview` effect или schema-marked ordinary artifact. |
| `apps/flows/src/clients/flows_client.py` | flow/node action preview/applied | Typed editor action artifact/effect; host action остаётся explicit. |
| `apps/flows/src/clients/lara_client.py` | CRM action preview/applied | A2UI actions + ordinary data fallback; не special event branch. |
| `apps/flows/tools/agent_skill_tools.py` | skill loaded event | `SkillActivity` artifact/effect. |
| `apps/flows/tools/documents.py` | document UI blocks/events | Catalog document/file artifacts. |
| `apps/flows/tools/files.py` | file UI blocks/events | Standard file Parts/Artifacts прежде всего. |
| `apps/flows/tools/viz.py` | cards/table/chart events | Typed platform catalog components; generic JSON fallback. |
| `apps/flows/tools/flows_editor_tools.py` | returns `ui_events` for patch preview | Переименовать output в typed `platform_effects`/`action_artifacts`; обновить tool descriptions/schema. |
| `apps/flows/src/runtime/nodes.py` | reflection/plan/custom event calls | Typed effects/current named artifacts; remote artifacts lossless. |
| `apps/flows/src/api/v1/code.py` | initial pending field | Полностью удалить field. |

`apps/flows/src/streaming/speakable.py` сохраняется, но whitelist/documentation больше не перечисляет `ui_event`; он классифицирует speakable content по Part/MIME/provenance, а не только artifact name.

`core/websocket/manager.py` не относится к A2A `artifact.name="ui_event"`: это общая platform WebSocket event bus. Его не удалять по совпадению строки; переименование требуется только если отдельный аудит обнаружит реальное смешение контрактов.

### 14.9. Session autosync/recovery/share files

| Действие | Файл | Изменение |
|---|---|---|
| CREATE | `apps/flows/src/services/flow_ui_session_service.py` | Authoritative bootstrap snapshot, `platform.ui.sync`, OCC/idempotency, atomic submit+sync. |
| CREATE | `apps/flows/src/services/flow_ui_share_service.py` | Mint/revoke/resolve scoped live-session grants после revision flush. |
| CREATE | `apps/flows/src/db/flow_ui_share_repository.py` | CRUD/query для `flow_ui_share_grants`; active/expiry/revocation checks. |
| CREATE | `apps/flows/src/api/v1/flow_ui_shares.py` | Control-plane create/list/revoke/exchange endpoints; ни один endpoint не заменяет A2A bootstrap/sync. |
| CREATE | `core/models/flow_ui_share.py` | Strict request/response/grant/scope/permission models. |
| MODIFY | `apps/flows/src/api/v1/flows.py` | Текущий `preview-share` явно оставить share нового preview, а не existing session; подключить/линковать новый live-session share UI/API. |
| MODIFY | `core/short_links/kinds.py` | Новый kind `flow_ui_session_share`. |
| MODIFY | `core/short_links/payloads.py` | Payload только с `grant_id`, без document/JWT. |
| MODIFY | `core/short_links/service.py` | Mint/resolve revocable session share link; expiry обязателен. |
| MODIFY | `apps/frontend/main.py` | Shared-session landing/exchange; после exchange убрать bearer code из address bar/history. |
| CREATE/MODIFY | `apps/frontend/services/flow_ui_shared_session_html.py` либо generalize `flow_preview_guest_html.py` | Mount universal renderer с scoped grant/session token; не встраивать UI snapshot в HTML. |
| MODIFY | auth/embed-session resolution в A2A boundary | Новый scoped identity содержит grant/context/permission и проверяется на каждом bootstrap/sync/submit/subscribe. |
| MODIFY | `apps/flows/src/container.py`, container contracts | Зарегистрировать session/share services/repository. |

Существующий `POST /{flow_id}/preview-share` сейчас создаёт одноразовый guest embed и новую conversation. Он сохраняет отдельную design-preview семантику, но не удовлетворяет live session share. Нельзя молча переиспользовать его так, чтобы одна и та же route иногда клонировала session, а иногда открывала существующую.

---

## 15. Configuration и storage migration

### 15.1. Новый design-time config

`FlowConfig.interface`:

```text
FlowInterfaceConfig
  schema_version: 1
  template: FlowUIDocumentTemplate
  catalog_id
  policy: FlowInterfacePolicy
  submit_action_name: Literal["platform.ui.submit"]
  fallback_policy
```

`BranchConfig.interface_override` не делает ambiguous deep merge:

- `mode="inherit"` — использовать flow interface;
- `mode="replace"` — полная branch template/policy;
- частичный component merge в config запрещён; editor сохраняет complete replacement для branch.

### 15.2. Policy

Policy управляет presentation/permissions, но не удаляет данные из A2A projection:

- reasoning visibility;
- tool activity display;
- execution diagnostics/run trace;
- browser preview;
- file controls;
- cancel permission;
- error detail exposure;
- allowed catalog/functions/actions;
- size/rate limits;
- embed-safe mode.

Greeting и suggested prompts становятся компонентами/initial data chat template, а не policy fields.

### 15.3. Embed

`EmbedConfig` сохраняет identity/security/look:

- `embed_id`, flow/branch, origins, status;
- theme/position/launcher/primary color/title/locale/branding;
- guest limits, voice, landing metadata;
- `interface_override` как partial policy/initial page override.

Embed не получает произвольную отдельную UI template по умолчанию: структура наследуется от выбранного flow/branch, чтобы не создавать второй document source. Если позже нужен embed-specific document, это отдельный versioned `mode=replace` с editor support.

### 15.3.1. `interface-profile` — только control plane

Ответ endpoint имеет узкий контракт:

```text
InterfaceProfile
  viewer: permissions/auth mode
  look: theme/position/title/locale/launcher/branding/voice
  catalog: supported catalog IDs/version hints
  capabilities: cancel/files/voice/bootstrap flags
  flow_identity: safe title/avatar if needed
```

В нём **нет** `FlowUIDocument`, component tree, `/values`, Task artifacts или runtime revision. Эти данные приходят только A2A bootstrap/GetTask/stream. Endpoint не принимает user interaction и не изменяет flow state.

### 15.4. Миграция `FlowChatSettings` → chat template

Для каждой записи `flows` и `flows_versions`:

1. прочитать `chat` либо defaults;
2. создать стандартный chat `FlowUIDocumentTemplate`;
3. `greeting_message` поместить в initial `/content/transcript`;
4. `suggested_prompts` превратить в suggestion components/actions, локально заполняющие composer;
5. `show_reasoning`, `tool_calls_display`, `show_activity`, `show_skill_loads`, `show_reflection`, `errors_display`, `show_run_trace`, `show_trace_actions`, `show_browser_previews`, `show_files_panel`, `allow_cancel` перенести в `interface.policy`/component visibility;
6. добавить обязательный `platform.ui.submit` Button;
7. удалить top-level `chat`;
8. провалидировать новый `FlowConfig`;
9. писать только при полном успехе; malformed row останавливает migration с key в error.

### 15.5. Миграция embed storage

Embed configs лежат в shared `storage` с keys `company:*:embed_config:*`, поэтому нужна отдельная shared migration:

1. найти все embed rows;
2. преобразовать `chat_override` в `interface_override.policy` только для explicitly set fields;
3. сохранить `false`, empty list и explicit overrides;
4. удалить `chat_override`;
5. валидировать `EmbedConfig`;
6. логировать counts `seen/converted/unchanged/failed` без содержимого secrets.

### 15.6. Bundles

Обновить как минимум:

- `apps/flows/bundles/lawyer/flow.json`;
- `apps/flows/bundles/tutor/flow.json`;
- `apps/flows/bundles/coach/flow.json`;
- `apps/flows/bundles/psy/flow.json`;
- `apps/flows/bundles/support_demo/flow.json`;
- `apps/flows/bundles/public_search/flow.json` и любой producer `ui_event`;
- все seed/example/fixture configs, найденные финальным `rg '"chat"\s*:'`.

### 15.7. Hard cut

- Runtime не принимает `chat`/`chat_override` aliases после migrations.
- API не сериализует оба поля.
- Старые DB records обновляются до deploy нового strict model.
- Rollout требует expand/migrate/code-contract sequencing либо maintenance window; нельзя сначала включить strict model на немигрированной DB.
- Downgrade data migration либо явно reconstructs old settings from template/policy, либо помечается irreversible с backup requirement; пустой `downgrade: pass` без документации запрещён.

---

## 16. Frontend target architecture

### 16.1. Новый core tree

```text
core/frontend/static/lib/flow-ui/
  protocol/
    a2a-stream.js
    a2a-codec.js
    a2a-task-accumulator.js
    a2a-extension-negotiation.js
    a2ui-0-9-1-codec.js
    generic-part-projector.js
    current-artifact-adapters.js
  runtime/
    flow-ui-state.js
    flow-ui-controller.js
    flow-ui-profile.js
    flow-ui-session.js
    flow-ui-autosync.js
    flow-ui-recovery-journal.js
    flow-ui-actions.js
    hitl-transport.js
  layout/
    grid-contract.js
    layout-resolver.js
    viewport-profiles.js
  rendering/
    render-context.js
    render-fingerprint.js
    production-render-frame.js
    renderer-inspection-bridge.js
  catalog/
    registry.js
    manifest.js
    basic/
    platform/
  components/
    platform-flow-ui.js
    flow-ui-surface.js
    flow-ui-error-boundary.js
    flow-ui-task-feed.js
    flow-ui-task-controls.js
  templates/
    chat-template.js
    empty-page-template.js
  editor/
    selection-overlay.js
    layout-grid-overlay.js
    rulers-guides-overlay.js
    snap-engine.js
  shell/
    drawer.js
    embed-autoload.js
    preferences.js
    tokens.css
```

`protocol/` не импортирует Lit. `catalog/` не выполняет network requests. `layout/` является общей pure domain→CSS projection для editor и runtime. `platform-flow-ui` только компонует controller/store/surfaces.

### 16.2. Universal component

`<platform-flow-ui>` props/attributes:

- `flow-id`, `branch-id`, `embed-id`;
- `display="page|panel|drawer|inline"`;
- `profile="spa|editor_test|embed_public|operator_handoff"`;
- `context-id`, auth/base URL/company namespace;
- optional initial document для preview;
- host callbacks `getSendMetadata`, action handlers;
- voice/file capability flags.

Host API:

- `runtimeState`;
- `loadContext(snapshot)`;
- `startNewContext()`;
- `submit(surfaceId, componentId)`;
- `cancelActiveTask()`;
- `stopVoice()`;
- `navigate(pageId)`;
- `applyA2AFrame(frame)` для voice relay/tests.

DOM events получают `flow-ui-*` names и frozen detail; platform EventBus integration использует официальные event factories. Embed standalone продолжает использовать DOM host contract без platform bus.

### 16.3. Один store

```text
FlowUIRuntimeState
  contextsById
    document
    hydration: idle|loading|ready|error
    serverRevision / pendingMutations / saveStatus
    taskOrder
    tasksById
      exact Task snapshot
      artifactsById
      status/history
    projectedArtifactsById
    activeTaskId
    connection/revision/conflict
  activeContextId
  profile/viewConfig/look
```

Нет `_uiBlocksByTaskId`, `messagesByContextId` как отдельного truth или chat-only loading state. Chat transcript — selector/projected surface из того же store.

Hydration/autosync invariants:

- до `hydration=ready` root показывает skeleton/error boundary и не монтирует default document;
- full session snapshot применяется одним immutable reducer event;
- input binding немедленно меняет local document и ставит mutation в journal;
- autosync coalesces compatible JSON Pointer changes, но не меняет их causal order;
- `Saved` показывается только после server acknowledgement этой mutation/revision;
- `startNewContext()` вызывается только явным действием пользователя, никогда как fallback ошибки reopen/share;
- смена `flow-id/branch-id/embed-id/share-grant` сначала завершает или сохраняет pending journal предыдущего context;
- task/artifact pagination не блокирует отрисовку уже materialized current document.

### 16.4. Renderer invariants

- keyed render by component ID;
- one render commit per A2UI batch;
- component-level error boundaries;
- unknown catalog component → safe fallback card;
- focus/value selection сохраняются при unrelated patches;
- scroll anchoring только для feed components, не глобально;
- DOM ordering соответствует component tree;
- no arbitrary `unsafeHTML`; существующий markdown path проходит sanitizer;
- CSS только design tokens, responsive container queries, reduced-motion support;
- `Grid`/`Stack`/`Flex` читают только persisted `container_layout` и `placement`, а не editor metadata;
- renderer и editor preview импортируют один `layout-resolver.js`; дублирование CSS grid calculations в `apps/flows/ui/**` запрещено;
- никакой editor wrapper не вставляется между parent layout component и его production child;
- runtime добавляет стабильный непользовательский inspection marker по `componentId`, который не влияет на role, tab order, layout или serialization;
- до готовности catalog, tokens, fonts и authoritative snapshot renderer не выставляет `parity-ready`; screenshot/`Exact` до этого состояния запрещены.

### 16.4.1. Канонический `FlowUIRenderContext`

Renderer не должен неявно читать окружение из разных глобалов. Один frozen context строится общей factory и передаётся одинаково в editor frame, Run, SPA, embed и shared preview:

```text
FlowUIRenderContext
  document_id / document_revision / snapshot_sequence / state_hash
  page_id / surface_id / target_surface_profile_id
  display: page | panel | drawer | inline
  viewport: {css_width, css_height, device_pixel_ratio, safe_area, scrollbar_mode}
  renderer_build_hash
  catalog_id / catalog_manifest_checksum
  design_token_checksum / font_manifest_checksum / asset_manifest_checksum
  brand_id / resolved_host_profile
  theme / contrast / reduced_motion
  locale / timezone / direction
  viewer_permissions / client_capabilities
  data_model_hash / task_projection_sequence
```

- Factory получает значения явно из validated bootstrap/profile; renderer не угадывает их через `window.location`, кроме заранее переданного host bootstrap.
- `target_surface_profile_id` описывает не только ширину: он выбирает реальную production shell composition для `page|panel|drawer|inline`, включая content insets, safe area, scroll container и host chrome, который влияет на доступное место.
- Primary default brand — Linnex; secondary platform domains выбирают свой brand profile, но catalog identity остаётся `https://linnex.io/a2ui/catalog/platform/v1`.
- Hash `FlowUIRenderFingerprint` вычисляется из всех полей, влияющих на DOM/layout/assets. Editor показывает fingerprint и field-level diff с выбранным deployment/target.
- Data values и artifact/task projection входят в context hash: пустой mock и заполненная живая session не могут получить одинаковый `Exact` статус.

### 16.4.2. Production render frame и inspection boundary

- `production-render-frame.js` загружает тот же versioned production entry module/import map/CSS bundle, что пользовательский route. Запрещён editor-only bundle с копиями components.
- Frame изолирует renderer от `flows-interface-editor` styles. Document/state передаются как frozen structured clone через локальный `MessageChannel`; это внутрибраузерный control bridge, не сетевой протокол и не второй ingress flow. Любой flow run внутри Run frame всё равно идёт через A2A.
- `renderer-inspection-bridge.js` возвращает только revision-tagged measurements: `componentId`, `DOMRect`, scroll box, computed grid tracks/gaps, active container band и overflow diagnostics. Он не принимает команды мутации DOM/styles.
- Selection/drag/snap overlay живёт в родительском editor layer. После domain command editor ждёт render commit той же revision и только затем обновляет handles, исключая one-frame drift.
- `Preview` отключает overlay/pointer interception. `Open on device` открывает тот же production frame URL на целевом host с signed immutable draft revision и тем же fingerprint inputs.
- Любое расхождение build/catalog/tokens/fonts/profile/revision переводит badge из `Exact` в blocking для visual sign-off состояние `Context differs`; editor обязан перечислить поля расхождения.

### 16.5. Dependency/build

Перед добавлением пакета:

1. проверить официальный A2UI package/export для v0.9.1 и Lit;
2. pin exact version в lockfile, без плавающего `^` на protocol codec;
3. либо vendor/build через новый `scripts/build_a2ui_bundle.mjs`, либо использовать собственный codec по pinned schemas;
4. не грузить npm/CDN runtime с внешнего домена в production;
5. добавить ESM closure check;
6. добавить assets/import map в app factory, guest preview, design-system preview, test dev server и PWA cache при необходимости.

### 16.6. Import-map consumers

Проверить/изменить:

- `core/app/factory.py`;
- `apps/frontend/services/flow_preview_guest_html.py`;
- design-system preview helpers;
- frontend test middleware/config;
- `core/frontend/pwa/sw.js`;
- `scripts/check_embed_esm_closure.py`;
- root `package.json`/`package-lock.json` и service lock, если используется.

---

## 17. Frontend migration inventory

### 17.1. Runtime files: MOVE/REWRITE then DELETE old paths

| Старый файл | Цель | Действие |
|---|---|---|
| `core/frontend/static/lib/chat/runtime/a2a-stream.js` | `flow-ui/protocol/a2a-stream.js` | MOVE + generalize; exact A2A frames only. |
| `core/frontend/static/lib/chat/a2a-chat-runtime.js` | task accumulator + adapters | REWRITE; удалить chat event verbs. |
| `core/frontend/static/lib/chat/runtime/chat-state.js` | `flow-ui/runtime/flow-ui-state.js` | REWRITE around document/tasks/artifacts. |
| `core/frontend/static/lib/chat/runtime/chat-controller.js` | `flow-ui/runtime/flow-ui-controller.js` | REWRITE; submit/action/session/reconnect. |
| `core/frontend/static/lib/chat/runtime/chat-profile.js` | `flow-ui/runtime/flow-ui-profile.js` | RENAME contract `/interface-profile`. |
| `core/frontend/static/lib/chat/runtime/operator-conversation-transport.js` | `flow-ui/runtime/hitl-transport.js` | MOVE preserving A2A artifacts. |
| `core/frontend/static/lib/chat/runtime/hitl-pause-listener.js` | `flow-ui/runtime/hitl-pause-listener.js` | MOVE/generalize. |
| `core/frontend/static/lib/chat/platform-chat.js` | `flow-ui/components/platform-flow-ui.js` + subcomponents | REPLACE, then DELETE monolith. |
| `core/frontend/static/lib/chat/embed-autoload.js` | `flow-ui/shell/embed-autoload.js` | REWRITE to create `platform-flow-ui`. |
| `core/frontend/static/lib/chat/chat-tokens.css` | `flow-ui/shell/tokens.css` | MOVE/rename variables to `--platform-flow-ui-*`. |
| `core/frontend/static/lib/chat/panel-width-preference.js` | `flow-ui/shell/preferences.js` | MERGE. |
| `core/frontend/static/lib/chat/launcher-position-preference.js` | same | MERGE. |
| `core/frontend/static/lib/chat/chat-window-toggle.js` | flow-ui drawer shell | MERGE. |
| `core/frontend/static/lib/chat/chat-url-params.js` | flow-ui session/profile | MOVE/generalize. |
| `core/frontend/static/lib/chat/flows-url-rewrite.js` | protocol/session transport | MOVE. |
| `core/frontend/static/lib/chat/external-embed-event-contract-v1.json` | flow-ui embed contract | RENAME/version update. |

После переноса imports и зелёных tests директория `core/frontend/static/lib/chat/` удаляется целиком. Не оставлять re-export `platform-chat` внутри приложения.

### 17.2. Presentation files → catalog

| Старый файл | Новая роль |
|---|---|
| `core/frontend/static/lib/chat/chat-message.js` | chat template feed item built from generic catalog components; большой класс декомпозировать. |
| `core/frontend/static/lib/chat/chat-input.js` | `Form` + `TextField` + `FileUpload` + required Submit component. |
| `core/frontend/static/lib/chat/chat-files-panel.js` | platform `FileList/FileUpload` components. |
| `core/frontend/static/lib/chat/chat-run-trace.js` | platform diagnostics `RunTrace`. |
| `core/frontend/static/lib/chat/chat-block-renderer.js`, `block-registry.js`, `chat-builtin-blocks.js` | единый trusted catalog registry; удалить inference registry. |
| `core/frontend/static/lib/chat/blocks/flows-chat-ui-*` | `catalog/platform/*` typed components. |
| `core/frontend/static/lib/chat/tool-result-blocks.js`, `tool-helpers.js` | current Artifact adapters/catalog components. |
| `core/frontend/static/lib/chat/markdown.js`, `citations.js` | reusable `Markdown/Citations` catalog utilities. |
| `core/frontend/static/lib/chat/agent-skill-icon.js`, `chat-author.js` | generic platform Avatar/SkillBadge utilities. |
| `core/frontend/static/lib/chat/chat-default-labels.js` | i18n keys; hardcoded label map удалить. |
| `core/frontend/static/lib/chat/chat-theme.js` | unified profile/look resolver. |
| `core/frontend/static/lib/chat/chat-settings-fields.js` | DELETE; settings replaced Interface editor/policy inspector. |

### 17.3. Host consumers

| Файл | Изменение |
|---|---|
| `apps/flows/ui/pages/chat-page.js` | Использовать `<platform-flow-ui>` с chat template. Route может остаться product route, но runtime общий. |
| `apps/flows/ui/components/editor/flows-execution-panel.js` | Run tab рендерит тот же document/renderer; editor_test policy через profile. |
| `apps/flows/ui/components/editor/flows-node-ai-helper.js` | Universal panel, Lara branch; никаких chat imports. |
| `core/frontend/static/lib/base/PlatformApp.js` | Global assistant drawer → universal renderer; platformAssistant config переименовать осмысленно либо адаптировать. |
| `apps/worktracker/ui/components/work-item-detail-editor.js` | HITL surface/profile через universal renderer. |
| `apps/frontend/ui/components/landing/landing-home-demo-agents.js` | Drawer universal renderer. |
| `apps/frontend/ui/pages/landing-digital-workers-page.js` | То же. |
| `apps/frontend/ui/events/resources/public-search.resource.js` | Удалить custom `ui_event` parser; принимать generic/A2UI projection. |
| `apps/frontend/ui/modals/create-embed-modal.js` | Interface override/policy preview; не chat settings fields. |
| `apps/frontend/ui/events/resources/embed.resource.js` | `interface_override` validation/DTO. |
| `apps/flows/ui/modals/flows-flow-edit-modal.js` | Удалить chat policy form; ссылка/summary Interface workspace. |
| `apps/flows/ui/events/resources/api-console.resource.js` | Импорт generic A2A accumulator, не chat runtime. |
| `apps/flows/ui/events/resources/execution-ui.resource.js` | Общие run events; не владеть composer/transport. |
| CRM/Lara consumers через PlatformApp | A2UI action handlers и context metadata, без отдельного renderer. |

### 17.4. Public CDN compatibility boundary

`core/frontend/static/lib/embed-chat/humanitec-embed-autoload.js` сохраняется, потому что URL уже размещён на внешних сайтах. Он становится однострочным stateless import нового `flow-ui/shell/embed-autoload.js`.

Новый preferred asset не использует старое имя бренда:

- code path: `core/frontend/static/lib/embed-flow-ui/flow-ui-embed-autoload.js`;
- primary public URL формируется brand config и на основном домене публикуется под `cdn.linnex.io`/настроенным Linnex CDN origin;
- тот же asset может обслуживаться с CDN других configured apex, но внутри рекламирует canonical catalog ID `https://linnex.io/a2ui/catalog/platform/v1`;
- ни API origin, ни catalog ID не хардкодятся в autoload: API/assets резолвятся по brand host/config, catalog identity приходит из manifest/AgentCard.

Это допустимый boundary compatibility shim:

- не содержит chat runtime/state/components;
- не экспортирует старые внутренние API;
- имеет deprecation telemetry и documented preferred new URL;
- удаляется только в отдельной major public contract migration.

### 17.5. Остальные frontend/helpers/import consumers

Финальный import audit обязан включать не только root hosts из 17.3:

| Файл/зона | Действие |
|---|---|
| `apps/flows/ui/app/flows-app.js` | Обновить route/global assistant imports и документацию единого компонента. |
| `apps/flows/ui/_helpers/chat-session-messages.js` | Удалить либо заменить lossless `flow-ui-session` selector; message-only hydration запрещена. |
| `apps/flows/ui/_helpers/resolve-flows-chat-task-id.js` | Заменить generic active task selector с явным context/task lifecycle. |
| `apps/flows/ui/_helpers/chat-files.js` | Перенести в generic file/artifact helper либо удалить при использовании catalog File components. |
| `apps/flows/ui/events/resources/editor.resource.js` | Workspace/interface draft/history changes и cleanup duplicate initial keys. |
| `apps/flows/ui/pages/flow-editor-page.js` | Logic/Interface/Run orchestration. |
| `apps/flows/ui/components/editor/flows-editor-header.js` | Workspace switch, preview/publish/problems controls. |
| `apps/flows/ui/components/editor/flows-bottom-toolbar.js` | Показывать controls текущего workspace, не chat-specific execution toggle. |
| `apps/frontend/ui/_helpers/platform-assistant-context.js` | Передавать universal renderer context/data model metadata. |
| `apps/worktracker/ui/_helpers/platform-assistant-context.js` | То же для worktracker; не создавать собственный transport. |
| `core/frontend/static/lib/events/effects/embed-request-helpers.js` | Header/profile/path names, если helper участвует в embed flow. |
| `scripts/check_platform_events_canon.py` | Добавить allowed frozen Flow UI events; не разрешать ad-hoc UI bus events. |
| `scripts/check_ui_canon.sh` | Запретить новые `platform-chat`, chat reducer и custom A2A `ui_event` imports. |
| `scripts/check_files_canon.py` | Проверить, что browser File всё ещё идёт upload → `Part.url`. |
| `core/i18n/translations/ru/flows.json`, `core/i18n/translations/en/flows.json` | Editor/catalog/profile labels. |
| `core/i18n/translations/ru/frontend.json`, `core/i18n/translations/en/frontend.json` | Shared runtime/embed/catalog labels; удалить zero-reference chat keys. |

Все imports проверяются финальным `rg` и `scripts/check_embed_esm_closure.py`; переезд файла без обновления guest preview/import map считается незавершённым.

### 17.6. Frontend engineering constraints

- Lit 3 остаётся базой; второй component framework не добавляется.
- Shared runtime/catalog/renderer живут в `core`, service UI только оркестрирует.
- Platform SPA state/actions используют EventBus, approved factories и frozen events.
- Standalone embed имеет узкий DOM/property host contract и не тянет platform EventBus.
- Нельзя вводить service-owned duplicate reducer, SSE parser, file uploader, modal/toast system или theme tokens.
- Все пользовательские строки идут через RU/EN i18n.
- Все визуальные значения — design-system tokens; editor и runtime используют один catalog manifest и component implementation.
- Большой `platform-flow-ui.js` не должен повторить монолит: protocol, state, controller, catalog и shell остаются отдельными модулями с unit boundaries.

### 17.7. File-by-file layout/WYSIWYG changes

| Действие | Файл | Изменение |
|---|---|---|
| CREATE | `core/frontend/static/lib/flow-ui/layout/grid-contract.js` | JS-side strict schema/assertions для container layout/placement; generated/shared fixtures сверяются с Python domain schema. |
| CREATE | `core/frontend/static/lib/flow-ui/layout/layout-resolver.js` | Единственная pure projection `FlowUIContainerLayout + placement + container band → tokenized CSS vars/grid styles`; editor не имеет копии. |
| CREATE | `core/frontend/static/lib/flow-ui/layout/viewport-profiles.js` | Exact viewport/safe-area presets и versioned container bands из catalog manifest. |
| CREATE | `core/frontend/static/lib/flow-ui/rendering/render-context.js` | Frozen context factory с явными profile/viewport/brand/theme/locale/assets/permissions/data inputs. |
| CREATE | `core/frontend/static/lib/flow-ui/rendering/render-fingerprint.js` | Deterministic canonical hash + field-level comparison; fail closed при отсутствующем input. |
| CREATE | `core/frontend/static/lib/flow-ui/rendering/production-render-frame.js` | Isolated frame, exact production asset loading, revision handshake и `parity-ready`. |
| CREATE | `core/frontend/static/lib/flow-ui/rendering/renderer-inspection-bridge.js` | Read-only revision-tagged geometry/grid/overflow measurements. |
| CREATE | `core/frontend/static/lib/flow-ui/editor/selection-overlay.js` | Selection/resize handles outside frame. |
| CREATE | `core/frontend/static/lib/flow-ui/editor/layout-grid-overlay.js` | Columns/gutters/margins/baseline from renderer measurements, не самостоятельный layout calculation. |
| CREATE | `core/frontend/static/lib/flow-ui/editor/rulers-guides-overlay.js` | Rulers и editor-local guides. |
| CREATE | `core/frontend/static/lib/flow-ui/editor/snap-engine.js` | Deterministic candidates/priority/tie-break и semantic placement proposal. |
| CREATE | `core/frontend/static/lib/flow-ui/editor/overlay-coordinate-space.js` | Frame CSS pixels ↔ parent scroll/zoom coordinates; единственное место transform math. |
| CREATE | `core/frontend/static/lib/flow-ui/editor/layout-domain-commands.js` | Immutable add/move/resize/span/band commands с inverse для undo. |
| MODIFY | `core/frontend/static/lib/flow-ui/components/flow-ui-surface.js` | Рендерить container/child layout только через `layout-resolver`; stable component markers для inspection. |
| MODIFY | `core/frontend/static/lib/flow-ui/components/platform-flow-ui.js` | Принимать один `FlowUIRenderContext`, readiness/fingerprint events и не иметь editor branch. |
| CREATE/MODIFY | `core/frontend/static/lib/flow-ui/catalog/platform/grid.js`, `stack.js`, `section.js`, `page-shell.js` | Typed layout capabilities/defaults, container-query CSS и accessibility constraints. |
| MODIFY | `core/frontend/static/lib/flow-ui/catalog/manifest.js` | Container bands, layout capabilities и renderer/schema checksums. |
| MODIFY | `core/frontend/static/assets/css/tokens.css` | Только недостающие semantic grid/editor-overlay tokens; никаких duplicate colors/spacing в flows app. |
| CREATE | `apps/flows/ui/components/interface-editor/flows-interface-grid-toolbar.js` | Grid/baseline/ruler/guide/snap controls через `flows/interface_editor` slice. |
| CREATE | `apps/flows/ui/components/interface-editor/flows-interface-layout-inspector.js` | Edit persisted grid/placement/band overrides через domain commands. |
| CREATE | `apps/flows/ui/components/interface-editor/flows-interface-render-frame.js` | Service orchestration wrapper без собственной render implementation. |
| CREATE | `apps/flows/ui/components/interface-editor/flows-interface-overlay-host.js` | Монтирование core overlays и revision handshake. |
| CREATE | `apps/flows/ui/components/interface-editor/flows-interface-parity-status.js` | `Loading/Exact/Context differs`, hashes и actionable diff. |
| MODIFY | `apps/flows/ui/components/interface-editor/flows-interface-canvas.js` | Заменить ad-hoc artboard на production frame + overlay coordinate system. |
| MODIFY | `apps/flows/ui/components/interface-editor/flows-interface-toolbar.js` | Surface/viewport/theme/brand/locale/data scenario/zoom/Open-on-device controls. |
| CREATE | `apps/flows/ui/events/resources/interface-editor.resource.js` | Approved `createSlice` для transient overlay/profile state и semantic command dispatch; layout copies запрещены. |
| MODIFY | `apps/flows/ui/events/resources/editor.resource.js` | Persist canonical interface draft/layout and joint logic+interface undo/save/publish transaction. |
| MODIFY | `apps/flows/ui/pages/flow-editor-page.js`, `apps/flows/ui/components/editor/flows-editor-header.js` | Interface workspace, Problems/parity/publish gates. |
| MODIFY | `apps/flows/ui/app/flows-app.js` | Зарегистрировать approved editor factory/slice; никаких direct controllers/fetch в components. |
| MODIFY | `core/app/factory.py`, guest/design-system/test import maps, `core/frontend/pwa/sw.js` | Один и тот же hashed renderer/catalog/token/font/asset set доступен editor frame и user hosts. |
| MODIFY | `scripts/check_core_frontend_canon.py`, `scripts/check_ui_canon.sh` | Запрет editor renderer forks, duplicated grid resolver/CSS и DOM-mutating inspection bridge. |

Все новые Lit classes следуют `PlatformElement/PlatformPage` canon; fields используют `<platform-field>`, actions идут через approved factories/EventBus, RU/EN keys добавляются парно. `flows-interface-*` не выполняют `fetch` и не импортируют factory objects/controllers напрямую.

---

## 18. Interface editor: UX и технический план

### 18.1. Верхний уровень редактора

`flow-editor-page` получает три равноправных workspace:

```text
Logic | Interface | Run
```

- `Logic`: текущий graph canvas/agent focus;
- `Interface`: visual page editor;
- `Run`: full preview, A2A/task/artifact inspector и execution diagnostics.

Текущий `mode: edit|run` заменяется `workspace: logic|interface|run`; layout `canvas|agent` остаётся под `logic`.

### 18.2. Layout Interface workspace

```text
┌────────────────────────────────────────────────────────────────────────────────┐
│ Logic | Interface | Run  Undo Redo | Grid Rulers Guides Snap | Surface | Viewport│
├────────────────┬───────────────────────────────────────┬────────────────────────┤
│ Pages / Layers │ Production render frame               │ Inspector              │
│ + Page         │ ┌───────────────────────────────────┐ │ Layout / Grid          │
│                │ │ exact <platform-flow-ui>          │ │ Placement / Responsive│
│ Components     │ │ + non-layout selection overlay    │ │ Properties / Binding  │
│ Search         │ │ + grid/rulers/guides overlay      │ │ Actions / A11y         │
│                │ └───────────────────────────────────┘ │                        │
├────────────────┴───────────────────────────────────────┴────────────────────────┤
│ Exact/Context differs · fingerprint · data/A2A provenance · problems · revision │
└────────────────────────────────────────────────────────────────────────────────┘
```

Canvas toolbar обязательно содержит:

- target surface: `Page | Panel | Drawer | Inline/Embed`;
- exact viewport presets и произвольный bounded CSS viewport;
- `Grid`, `Baseline`, `Rulers`, `Guides`, `Snap` toggles;
- zoom (`Fit`, `50–200%`, `100%`) отдельно от внутреннего viewport;
- theme/brand/locale/data scenario selectors;
- `Preview`, `Run with flow`, `Open on device`;
- parity badge `Loading assets | Exact | Context differs`.

### 18.3. Editor components to create

В `apps/flows/ui/components/interface-editor/`:

- `flows-interface-editor.js` — orchestration only;
- `flows-interface-toolbar.js`;
- `flows-interface-grid-toolbar.js`;
- `flows-interface-pages-panel.js`;
- `flows-interface-layers-tree.js`;
- `flows-interface-palette.js`;
- `flows-interface-canvas.js`;
- `flows-interface-render-frame.js` — тонкая service wrapper над core production frame;
- `flows-interface-overlay-host.js` — позиционирование core overlays без DOM-мутации frame;
- `flows-interface-inspector.js`;
- `flows-interface-layout-inspector.js` — grid/flex/stack, spans, gaps, sizing и responsive overrides;
- `flows-interface-binding-editor.js`;
- `flows-interface-action-editor.js`;
- `flows-interface-data-model-panel.js`;
- `flows-interface-problems-panel.js`;
- `flows-interface-parity-status.js` — fingerprint/diff/assets readiness;
- `flows-interface-preview.js`.

В `core/frontend/static/lib/flow-ui/editor/` создать reusable primitives:

- `selection-overlay.js`;
- `layout-grid-overlay.js`;
- `rulers-guides-overlay.js`;
- `snap-engine.js`;
- `overlay-coordinate-space.js` — единственное преобразование frame CSS pixels ↔ zoomed editor coordinates;
- `layout-domain-commands.js` — add/move/span/align/reorder без прямой DOM mutation.

В `core/frontend/static/lib/flow-ui/rendering/` создать `production-render-frame.js`, `renderer-inspection-bridge.js`, `render-context.js`, `render-fingerprint.js`. Reusable drag/drop/tree/inspector primitives используют catalog schemas из `core`; editor не дублирует renderer, grid resolver или catalog schema.

### 18.4. State/resource

Предпочтительный clean split:

- `flows/editor` остаётся aggregate flow draft и workspace selection;
- новый UI-only slice `flows/interface_editor` хранит transient selection, target surface/profile, viewport, zoom, grid/baseline/ruler visibility, local guides, snap preferences, drag state, open panels и last measured revision;
- canonical `interfaceDraft` принадлежит aggregate save state и сохраняется вместе с `branchData`;
- `container_layout`, component placement и responsive overrides находятся только в canonical `interfaceDraft`; в UI-only slice их копии запрещены;
- undo/redo command history хранит domain commands с `target=logic|interface`, а не snapshots всего app state;
- один save/publish transaction валидирует graph + interface.

Создать:

- `apps/flows/ui/events/resources/interface-editor.resource.js` как единственный approved `createSlice` contract для `flows/interface_editor`, включая `extraInitial`, `extraEvents`, pure `extraReducer` и actions;
- immutable/frozen events через platform EventBus;
- selectors в отдельном helper, без чтения DOM в reducer.

При этом исправить найденное дублирование initial `nodeRunResults`/`expandedNodeRunKeys` в `editor.resource.js`.

### 18.5. Editing operations

- add/move/copy/delete component;
- nesting с catalog slot constraints;
- multi-select/alignment/distribution;
- keyboard move/reorder/span resize по grid units;
- create/convert nested `Grid|Stack|Flex`, change column count, gap, outer padding, max width и baseline token;
- drag/resize преобразуется в semantic `{column_start,column_span,row_start,row_span}` либо stack/flex order, а не сохраняет `left/top/width/height`;
- responsive override `inherit|override|reset` на каждом container band;
- rulers, draggable local guides и snap к columns/baseline/component edges/centres;
- page create/duplicate/rename/delete;
- binding pick/create and data preview;
- action selection: local function или `platform.ui.submit`;
- responsive props/preview, но один semantic tree;
- component presets/styles from design tokens;
- undo/redo transaction per user gesture;
- clipboard format versioned и sanitised;
- raw JSON advanced editor валидирует ту же schema и не обходит catalog security.

### 18.6. Mandatory Submit validation

Publish validator выдаёт blocking error, если:

- нет ни одного visible reachable `Button` с event action `platform.ui.submit`;
- source component не входит в active surface;
- interactive form page не имеет reachable submit/global submit;
- submit находится только в modal, который невозможно открыть;
- action binding обращается вне `/values`;
- button disabled навсегда static check;
- duplicate reserved actions имеют conflicting form scope.

Editor предлагает quick fix «Добавить Submit» и вставляет tokenized primary Button.

### 18.7. Preview

- использует production `<platform-flow-ui>`, тот же compiled module, import map, catalog, layout resolver, tokens и fonts;
- mock data model явно отделён от saved template;
- Interactive preview local actions работают;
- Flow invocation в design preview выключен до явного «Run with flow»;
- Run mode создаёт настоящий A2A Task и показывает task/artifact inspector;
- preview не имеет отдельного fake chat renderer;
- overlay/rulers/guides полностью отключаются, frame остаётся на том же месте и не перемонтируется другим renderer;
- preview выбирает target shell profile, поэтому developer видит не абстрактный прямоугольник, а реальную `page|panel|drawer|inline/embed` content area;
- `100%` zoom означает один editor screen CSS pixel на один frame CSS pixel; другие zoom levels не меняют layout внутри frame;
- `Exact` доступен только после `document.fonts.ready`, готовности изображений с layout-affecting dimensions, catalog registration, hydration commit и fingerprint match;
- `Open on device` использует immutable draft revision и не сохраняет mock/editor overlay state как пользовательский UI.

### 18.8. Grid authoring: обязательный UX

Для выбранного layout container canvas показывает:

- нумерованные columns, gutters, outer margins и max-content boundary;
- horizontal baseline rows по `baseline_step_token`;
- active container band и точный inline size, на котором он выбран;
- placement/span каждого child; inherited placement визуально отличается от explicit override;
- overflow, overlap, clipped focus ring, min-content violation и unreachable controls прямо на artboard и в Problems panel;
- nested grid breadcrumbs, чтобы было ясно, относительно какой сетки считается placement.

Поведение drag/resize:

1. pointer position переводится из overlay coordinates во внутренние CSS pixels через `overlay-coordinate-space.js`;
2. `snap-engine.js` строит candidates из computed tracks production renderer, baseline и sibling rectangles;
3. editor показывает proposed semantic placement, не меняя production DOM;
4. release создаёт одну undoable `layout-domain-command`;
5. command обновляет `interfaceDraft`, renderer получает новую revision;
6. handles перемещаются только после inspection result для этой же revision.

Keyboard parity:

- arrows меняют order/placement на один grid unit;
- `Shift+arrows` меняет span;
- modifier выбирает baseline step для fine movement только у catalog components, где это допустимо;
- все действия имеют RU/EN accessible announcements и попадают в undo как одна transaction;
- grid можно полностью настроить без pointer.

Responsive model:

- один semantic tree для всех размеров;
- base placement применяется везде, band override содержит только отличающиеся поля;
- editor одновременно может показать несколько read-only comparison frames, но активный edit target всегда один и явно подсвечен;
- publish validator прогоняет **все** catalog viewport presets, container bands и target surface profiles, а не только текущий desktop;
- смена preset не должна менять document; она меняет только `FlowUIRenderContext.viewport`.

### 18.9. Строгий editor → runtime 1:1 contract

Последовательность каждого editor render:

1. aggregate reducer выдаёт immutable `FlowUIDocument` revision `N`;
2. domain/schema/catalog validator принимает ровно revision `N`;
3. общая factory строит `FlowUIRenderContext` для выбранного deployment/host/surface/viewport/data scenario;
4. frame подтверждает точные build/catalog/token/font/asset hashes;
5. production `<platform-flow-ui>` atomically применяет document + data + task/artifact projection;
6. frame ждёт fonts/layout-affecting assets и выдаёт `render-committed(N)`;
7. read-only inspection bridge возвращает geometry с revision `N`;
8. editor overlay рендерится по этой geometry;
9. `flows-interface-parity-status` сравнивает fingerprint с target deployment и только тогда показывает `Exact`.

Нельзя:

- рисовать editor component собственной Lit/HTML реализацией;
- переопределять CSS variables внутри frame «для удобства editor»;
- добавлять padding/border вокруг selectable component внутри production tree;
- вычислять grid tracks повторно по editor state;
- подставлять default/mock values без явного data scenario label;
- считать exact preview до загрузки fonts/images или при несовпавших hashes;
- публиковать при unknown component, invalid placement, unresolved overflow blocking severity или unavailable target assets.

### 18.10. Матрица источников визуальной истины

| Что влияет на экран | Единственный source of truth | Как editor доказывает совпадение |
|---|---|---|
| Component tree/values | `FlowUIDocument` accepted/draft revision | `document_id`, revision, state/data hash |
| Columns/spans/gaps | persisted layout contract + `layout-resolver.js` | computed tracks из inspection bridge |
| Component markup/behavior | production catalog components | renderer build + catalog checksum |
| Colors/type/spacing | production token bundle | design-token checksum |
| Fonts/images/icons | production asset manifest | font/asset checksum + readiness |
| Width/height/safe area | target surface + viewport profile | exact inner frame dimensions |
| Page/panel/drawer/embed chrome | production target shell profile | profile ID/version/hash |
| Brand/domain | host-resolved brand profile | brand ID + resolved profile hash |
| Locale/timezone/direction | render context | explicit context fields |
| Permissions/capabilities | bootstrap/profile | capability/permission hash |
| Tasks/artifacts/live state | A2A accumulator snapshot | task sequence + data model hash |

Итоговый developer contract: зелёный `Exact` означает, что editor показывает тот же production build с теми же inputs; это не субъективное «похоже». Если целевой пользовательский context неизвестен или отличается, editor обязан показать варианты/дифф, а не скрыть неопределённость.

---

## 19. Catalog первого релиза

### 19.1. A2UI Basic Catalog

Обязательные компоненты:

- `Text`;
- `Image`;
- `Icon`;
- `Video`;
- `AudioPlayer`;
- `Row`;
- `Column`;
- `List`;
- `Card`;
- `Tabs`;
- `Divider`;
- `Modal`;
- `Button`;
- `TextField`;
- `CheckBox`;
- `ChoicePicker`;
- `Slider`;
- `DateTimeInput`.

Их properties/actions/bindings соответствуют official v0.9.1 Basic Catalog guide.

### 19.2. Platform trusted catalog

Минимально необходим для parity и «крутых UI»:

- `PageShell`, `Navigation`, `PageLink`, `Section`, `Grid`, `Stack`;
- `Heading`, `Markdown`, `CodeBlock`, `Citations`;
- `Form`, `FieldGroup`, `Select`, `TextArea`, `NumberField`;
- `FileUpload`, `FileCard`, `FileList`;
- `DataTable` с pagination/sort без arbitrary cell HTML;
- `Chart` с declarative allowlisted spec;
- `Metric`, `Badge`, `Status`, `Progress`, `Alert`, `EmptyState`;
- `Avatar`, `AgentIdentity`;
- `ArtifactFeed`, `ArtifactCard`, `JsonInspector`;
- `TaskControls`, `RunTrace`, `ToolActivity`;
- `BrowserPreview` через safe platform session reference;
- `SuggestedPrompts`;
- `ConversationFeed` как chat template composition, не отдельный runtime.

Layout contract каталога:

- `PageShell`, `Section`, `Grid`, `Stack`, `Row` и `Column` явно объявляют `container_layout` capabilities и допустимые child placement fields;
- `Grid` поддерживает versioned 4/8/12 platform preset, nested grids, tokenized gaps/padding/max-width и bounded responsive overrides;
- каждый leaf component декларирует allowed sizing/alignment/min-content behavior, чтобы editor не предлагал невозможные resize operations;
- catalog metadata помечает component как `container`, `leaf` либо `overlay`; произвольный absolute layout не возникает из generic properties;
- `Form`/`Button` placement не может нарушить keyboard/tab/DOM order: визуальный `order` проверяется против accessible reading order и при конфликте блокирует publish.

### 19.3. Catalog manifest

Для каждого component:

- versioned type ID;
- JSON Schema props;
- allowed child slots/types;
- allowed binding value types;
- allowed actions/functions;
- editor metadata/icon/category/default props;
- renderer factory;
- layout capabilities, default container layout/placement и container-band support;
- accessible name/role rules;
- fallback representation;
- security classification;
- migration function per component schema version.

Server и client manifests проверяются checksum в CI; drift запрещён. Manifest checksum вместе с renderer/token/font/asset hashes входит в `FlowUIRenderFingerprint`, поэтому editor не может показать зелёный `Exact` при несовпавшей версии catalog.

### 19.4. Visual direction

- существующий design system и CSS tokens — единственный источник цвета/radii/spacing/type;
- canvas и runtime поддерживают light/dark/auto;
- modern responsive layout через persisted grid/flex/stack + container queries;
- начальный responsive grid preset — 4 columns compact, 8 medium, 12 wide; gutters, margins и baseline берутся только из tokens;
- editor отображает columns, gutters, margins, baseline, rulers, guides, snap и responsive placement, используя computed geometry production renderer;
- micro-interactions используют reduced motion;
- skeletons привязаны к Task/artifact state;
- typography/spacing presets ограничены системой, чтобы generated UI выглядел цельно;
- editor показывает real container bands/viewport profiles, overflow и accessibility issues до publish;
- editor chrome/overlay не переопределяет production CSS и не участвует в screenshot пользователя;
- никаких hardcoded gradients/glass вне approved tokens.

### 19.5. Канонический default chat template

Миграция и новые flows без кастомного interface используют один versioned template:

```text
PageShell(main)
  Header
    AgentIdentity
    TaskControls(cancel/voice/files according to policy)
  ConversationFeed
    ArtifactFeed binding: /system/tasks
  EmptyState/Greeting binding: /content/greeting
  SuggestedPrompts binding: /content/suggestedPrompts
  Form(id=message-form)
    FileUpload binding: /values/files
    TextArea binding: /values/message
    Button action: platform.ui.submit, formId=message-form
```

- `ConversationFeed` — композиция/projector обычных artifacts, не отдельное message store;
- suggestions локально записывают `/values/message` и сами не запускают flow;
- Submit отправляет полный разрешённый data model;
- после accepted submit policy может очистить только `/values/message/files`, сохранив другие page values;
- greeting/suggestions редактируются как обычные components/data;
- владелец flow может полностью заменить layout/pages, сохранив submit invariant;
- chat-like bubble presentation является style preset ArtifactFeed, а не protocol type.

---

## 20. Embed, voice, HITL и специальные поверхности

### 20.1. Embed

- endpoint остаётся `/flows/api/v1/embed/{embed_id}` — это тот же A2A handler;
- profile становится `/interface-profile`;
- CORS разрешает `A2A-Version`, `A2A-Extensions`, `Accept`, auth/platform headers;
- autoload создаёт `<platform-flow-ui display="drawer">`;
- внешний host event contract version bump описывает document/action/task events;
- allowed origins и embed-session method allowlist сохраняются;
- UI document приходит только после auth/target resolution;
- public URL shim сохраняется согласно 17.4.

### 20.1.1. Reopen/share rendering contract

- SPA route, embed drawer и shared-session page передают renderer существующий context/share grant, если пользователь продолжает session.
- Renderer не вызывает `startNewContext()` при mount, пока bootstrap существующего context не вернул definitive not-found и пользователь явно не выбрал новый экран.
- Shared-session HTML содержит только bootstrap configuration/token exchange data; полный UI и values всегда загружаются A2A snapshot.
- Получатель share видит сохранённую active page до первого собственного разрешённого navigation action.
- Read-only viewer всё равно получает live Task/Artifact updates через scoped `SubscribeToTask`.
- Collaborator sync/submit проходит тот же A2A reducer/transport и revision checks.
- Закрытие drawer/route не очищает server state; «Новая сессия» является отдельной явной destructive/navigation action с confirmation при pending unsynced values.

### 20.2. Voice

- voice остаётся вводом/выводом того же A2A interaction;
- распознанный utterance может отправляться ordinary text Message; при UI context к metadata добавляется текущий accepted `a2uiClientDataModel`;
- TTS читает только speakable projection из response text/Markdown artifacts, не озвучивает JSON/UI controls;
- A2UI update не создаёт второй TTS текст, если та же семантика уже озвучена;
- `voice-agent-bridge.js` импортирует generic A2A stream utilities;
- `a2a-result-tts.js` становится generic artifact-to-speakable projector;
- barge-in/cancel/task ID behavior сохраняется.

Изменить:

- `core/frontend/static/lib/voice/voice-agent-bridge.js`;
- `core/frontend/static/lib/voice/a2a-result-tts.js`;
- voice rules/tests и `tests/e2e/voice/test_voice_chat.py` → flow UI naming.

### 20.3. HITL/operator

- takeover replies/files остаются обычными artifacts;
- `ConversationFeed` adapter показывает `operator_reply/user_message/operator_files`;
- закрывающий reply и terminal status дедуплицируются accumulator/provenance, не chat heuristic;
- `SubscribeToTask` snapshot включает уже накопленные artifacts;
- `input-required` surface может быть сгенерирована A2UI, но ordinary client получает standard status message/form fallback;
- Worktracker не получает собственную chat state machine.

### 20.4. Browser preview, skills, reflection, plans

Текущие `push_ui_event` producers переводятся:

- browser preview → typed `BrowserPreview` UI effect либо обычный artifact с explicit schema;
- skill loaded → `SkillBadge/ToolActivity` artifact/effect;
- reflection resolved → `Status/Reflection` adapter;
- agent plan → typed platform component;
- handoff/handback actions → A2UI buttons + ordinary status metadata fallback;
- public search cards/table/viz → A2UI/catalog or existing standard data artifacts.

Только после parity tests удаляется `ui_event` producer/consumer.

---

## 21. Security model

### 21.1. Trust boundaries

| Источник | Trust | Разрешено |
|---|---|---|
| Flow config editor/admin | authenticated design-time | trusted catalog document после schema validation |
| Flow runtime node | agent-owned | domain UI commands через host API |
| Sandbox code | untrusted | requested typed capability; host-issued effects only |
| Browser values | untrusted | allowlisted `/values` paths + revision/action checks |
| External A2A agent | untrusted | standard Parts; A2UI only negotiated/validated/catalog-safe |
| Embed host page | hostile | attributes/events only; Shadow DOM/CSP/origin isolation |

### 21.2. Validation order submit

1. auth/company/embed origin/method permission;
2. A2A version and ProtoJSON parsing;
3. extension/capability schema;
4. context/task ownership;
5. document/revision/action id;
6. surface/source component/reachability;
7. reserved action name;
8. allowed `/values` bindings;
9. per-field schema and server business validation;
10. rate/size limits;
11. durable idempotency write;
12. flow start/resume.

### 21.3. Renderer security

- Shadow DOM where appropriate;
- CSP compatible, no inline script;
- sanitized Markdown/link protocols;
- image/media URL validation;
- raw bytes object URLs revoked;
- no credentials on cross-origin artifact URL fetch unless explicit file service path;
- max recursion/depth/component count/text/data size;
- expression/function allowlist, no JavaScript expressions;
- modal/focus trapping and clickjacking-safe embed;
- production render frame загружает только allowlisted platform entry/assets; editor не принимает произвольный frame URL/import map;
- inspection `MessageChannel` проверяет channel nonce, source frame, revision и schema; bridge read-only и не возвращает secrets/computed content;
- signed open-on-device draft token scoped к flow/document/revision/view, short-lived и не даёт publish/admin permission;
- sensitive metadata redacted in inspector/telemetry.

### 21.4. Surface ownership/subagents

Перед передачей Message удалённому agent/subflow:

- передаются только surfaces/data, которыми он владеет или которые явно delegated;
- platform/system and sibling surfaces удаляются;
- `/values` minimised to declared inputs;
- returned A2UI cannot update surface with чужим owner ID;
- provenance сохраняет source agent/task.

### 21.5. Autosync/share security

- `platform.ui.sync` проходит тот же auth/company/context/grant scope, что Submit.
- Share bearer code не логируется, не кладётся в analytics/referrer и удаляется из URL после token exchange.
- В БД хранится grant identity/state, а не plaintext long-lived token.
- Viewer-specific redaction выполняется server-side до snapshot serialization; CSS hiding не считается permission control.
- `viewer` не может повысить permission через Message metadata.
- `collaborator` имеет explicit path/action scope и не получает owner/admin capabilities.
- Link revoke/expiry проверяется не только при открытии страницы, но и при token refresh, sync, submit, subscribe/reconnect.
- CSRF/origin/audience проверки обязательны для share token exchange; A2A scoped token не применим к другим flows/contexts.
- Concurrent mutation conflict не должен возвращать другому viewer secret values в error diff.
- Local recovery journal шифруется/очищается при logout, grant revoke, company switch и явном удалении session; secrets, raw files и server-only paths туда не записываются.

---

## 22. Observability, performance, accessibility и i18n

### 22.1. Metrics

- `a2a_tasks_opened_total{representation}`;
- `a2a_artifact_updates_total{name_or_class,append}` с controlled cardinality;
- `a2a_projection_lag_seconds`;
- `a2a_reconnect_replayed_events_total`;
- `a2ui_batches_total{version,status}`;
- `a2ui_messages_rejected_total{reason}`;
- `flow_ui_revision_conflicts_total`;
- `flow_ui_submit_total{result}`;
- `flow_ui_sync_total{result}` и `flow_ui_sync_latency_ms`;
- `flow_ui_pending_mutations` histogram;
- `flow_ui_hydration_total{source,result}`;
- `flow_ui_hydration_latency_ms`;
- `flow_ui_share_bootstrap_total{permission,result}`;
- `flow_ui_render_commit_ms`;
- `flow_ui_parity_total{status,reason_class}` для `exact|context_diff|asset_error`, только controlled reason classes;
- `flow_ui_parity_ready_ms` и `flow_ui_layout_measure_ms`;
- `flow_ui_layout_problem_total{kind,severity}` без component IDs;
- `flow_ui_component_count` histogram;
- `generic_part_fallback_total{part_type,mime_class}`;
- `platform_effect_rejected_total{reason}`.

Не использовать raw artifact names/component IDs/action IDs как high-cardinality labels.

### 22.2. Tracing/logging

Trace attributes:

- company/flow/context/task/interaction IDs по privacy policy;
- representation/extension URI/version;
- task sequence/artifact ordinal;
- UI base/new revision;
- render fingerprint/build/catalog/token/font/asset/profile hash prefixes и parity status;
- active container band/viewport/surface profile без пользовательских content/values;
- codec/validation result;
- durable commit → Redis publish latency.

Payload/values/raw bytes в logs не выводятся. Developer inspector доступен только авторизованным пользователям.

### 22.3. Performance budgets

- initial renderer JS gzip budget фиксируется после baseline; target не больше текущего chat bundle + согласованный запас;
- lazy-load editor и тяжёлые Chart/Code/Media components;
- один render commit на A2UI batch;
- inspection выполняется один раз на committed revision и batch-читаeт layout, без layout thrashing на каждый component;
- editor overlay использует `requestAnimationFrame` только при scroll/zoom/drag и не запускает второй component render;
- fonts/assets readiness имеет timeout с явным non-Exact состоянием, не silent fallback;
- virtualization для ArtifactFeed/DataTable > threshold;
- semantic deltas вместо whole document;
- snapshot/patch threshold по bytes/component count;
- task artifact JSONB size alert/limit;
- no unbounded in-memory `_uiBlocksByTaskId`/task maps; context eviction policy;
- Redis reconnect не реплеит весь context без cursor.
- hydration current document имеет отдельный latency/bytes budget; task history догружается после first meaningful paint;
- autosync coalescing имеет upper delay budget, а share/submit всегда выполняют forced flush;
- local recovery journal ограничен по context/bytes/age и очищает acknowledged mutations.

### 22.4. Accessibility

- WCAG 2.2 AA target;
- keyboard DnD/reorder and full editor navigation;
- keyboard-only grid placement/span/band override и accessible announcements semantic layout commands;
- visible focus, skip links, landmark structure;
- accessible labels/errors/help for generated forms;
- submit disabled state объясняется;
- live region только для meaningful task status, не каждого chunk;
- modal focus restore;
- color contrast проверяется для embed primary color, unsafe color корректируется;
- reduced motion/high contrast/browser zoom tests;
- screen reader artifact ordering соответствует wire order;
- CSS visual `order`/grid placement не должен расходиться с DOM/accessibility reading order без blocking validation.

### 22.5. i18n

- все platform-rendered labels в `core/i18n/translations/{ru,en}/frontend.json`;
- content от flow не переводится клиентом;
- editor catalog labels/descriptions локализованы;
- locale входит в client capabilities и profile;
- date/time/input formatting учитывает locale/timezone, wire values остаются canonical;
- удалить chat-only keys после zero-reference check;
- RU и EN visual/e2e coverage обязательны.

---

## 23. Порядок реализации с блокирующими gates

### Phase 0. Заморозить контракт и baseline

Работы:

- принять этот документ;
- снять golden A2A outputs текущих artifacts, HITL, files, voice, public search;
- инвентаризировать все runtime imports/string literals `chat`, `ui_event`, `ui_events_pending`;
- зафиксировать visual/a11y/performance baseline current chat surfaces;
- зафиксировать canonical viewport/surface profiles, container-band thresholds, token/font/asset manifests и deterministic Chromium visual environment;
- проверить фактические Alembic heads перед созданием migrations;
- pin A2UI official schemas/checksum/package decision.

Gate:

- compatibility matrix превращена в executable test matrix;
- нет неизвестных producers/consumers `ui_event`;
- baseline содержит geometry/screenshot fixtures для page/panel/drawer/embed на desktop/mobile;
- пользователь подтвердил target contract.

### Phase 1. Исправить A2A artifact correctness без UI cutover

Работы:

- shared accumulator;
- stable artifact IDs;
- lossless blocking Task construction;
- durable task/message/artifact projections;
- Get/List/Subscribe/push parity;
- external A2A client structured result;
- current frontend всё ещё может работать поверх тех же artifacts.

Gate:

- all four Parts round-trip во всех A2A modes;
- arbitrary artifacts survive restart/GetTask;
- current artifacts tests green;
- no A2UI code required for ordinary A2A correctness.

### Phase 2. Flow UI domain + A2UI codec

Работы:

- domain models/delta/revision;
- versioned `Grid/Stack/Flex`, responsive placement, target surface profiles и layout validation;
- A2UI v0.9.1 codec and fixtures;
- AgentCard/headers/negotiation;
- representation selector/fallback;
- state materialization from default chat template;
- authoritative session snapshot, `platform.ui.bootstrap` и `platform.ui.sync` commands;
- share grant model/repository и revision-flush contract.

Gate:

- official A2UI examples encode/decode;
- non-A2UI client unaffected;
- same logical UI effect produces exactly one representation per Task;
- durable replay hash stable;
- layout document round-trip/replay сохраняет columns/spans/gaps/bands без editor-only state;
- close/reopen/bootstrap возвращает ту же document revision и values;
- share grant не создаёт новый context и не выдаётся до sync acknowledgement.

### Phase 3. Trusted effects

Работы:

- platform effects contracts;
- all four runner harnesses;
- capability registry `ui.*`;
- host validator/applier;
- migrate every `push_ui_event` producer.

Gate:

- sandbox state mutation cannot alter UI;
- effects survive all languages/retry/replay;
- no remaining producer of `ui_events_pending` except migration test fixtures.

### Phase 4. Universal frontend runtime/renderer

Работы:

- protocol accumulator/projectors;
- catalog and components;
- shared layout resolver, render context/fingerprint и production render frame;
- `<platform-flow-ui>`;
- chat template parity;
- voice/files/HITL/embed integration;
- reconnect/full-state hydration;
- autosync/save status/local recovery journal;
- shared-session page для viewer/collaborator.

Gate:

- SPA/editor/embed/landing/Lara/HITL use universal renderer in test environment;
- ordinary unknown artifacts render safely;
- current chat UX parity tests and new multi-page tests green;
- no separate reducer/transport in hosts;
- reload/new tab/new device/share screenshot и data-model snapshot совпадают с последней server-acknowledged revision;
- default template ни на один frame не затирает restored screen;
- production renderer одинаково вычисляет grid tracks во всех hosts; ни один host не содержит своей grid CSS implementation.

### Phase 5. Interface editor

Работы:

- workspace/state/components;
- palette/layers/inspector/bindings/actions;
- grid/baseline/rulers/guides/snap, semantic drag/resize и responsive layout inspector;
- isolated production frame, read-only inspection bridge, overlay coordinate space и parity status;
- mandatory Submit validator;
- responsive/a11y preview и target surface/brand/locale/data scenarios;
- atomic save/publish with graph.

Gate:

- user can build and publish multi-page UI without raw JSON;
- editor preview and production load the identical renderer module, catalog, layout resolver, tokens, fonts and target shell profile;
- selection/grid overlays do not mutate DOM/computed layout, а overlay geometry относится к той же document revision;
- default 4/8/12 grid, nested grids, responsive spans, rulers/guides/snap и keyboard authoring проходят browser tests;
- `Exact` появляется только при полном fingerprint match; intentional mismatch показывается как `Context differs` с field-level diff;
- editor-frame и production-route geometry/screenshot parity matrix зелёная для обязательных viewport/surface/theme/brand/locale scenarios;
- undo/redo/save/reload preserves stable IDs and values;
- invalid/no-submit UI cannot publish.

### Phase 6. Storage/API hard cut

Работы:

- deploy code supporting read of new schema in migration-compatible sequence;
- run flows and shared migrations;
- update bundles/OpenAPI/docs/i18n;
- switch `/interface-profile` and clients;
- remove runtime chat aliases.

Gate:

- zero DB rows with top-level `chat`/`chat_override`;
- old/new version rows validate;
- no API exposes both contracts;
- rollback/backup procedure tested.

### Phase 7. Delete old chat/UI-event architecture

Работы:

- delete `core/frontend/static/lib/chat/` after moved functionality;
- delete chat models/settings form/profile handlers;
- delete `ui_events_pending` path;
- delete old tests/stubs only after equivalent new coverage;
- retain only public CDN autoload shim.

Gate:

- `rg` zero-reference checks from 27.4;
- full tests, type/lint/OpenAPI/ESM closure green;
- visual/a11y/performance budgets pass;
- artifact compatibility suite remains green.

### Phase 8. Production rollout

- feature flag controls renderer selection only during pre-production canary; не два protocol contracts;
- canary by internal company/flow;
- shadow-compare task projections and frontend reducer state;
- monitor conflict/reject/fallback/latency/error rates;
- expand gradually;
- remove flag and old renderer in same release window after gate;
- no permanent dual write/dual emit.

---

## 24. Database/API rollout sequence

Чтобы strict hard cut не сломал deployment:

1. Backup `flows`, `flows_versions`, shared `storage` embed rows, workflow/task/UI/share tables.
2. Deploy migration-capable binary/tooling, не включающее new-only reads в live path.
3. Run preflight validator и dry-run report.
4. Apply flows migration and indexes concurrently where supported.
5. Apply shared embed migration.
6. Rebuild/verify task projections for active sessions if Phase 1 introduced tables earlier.
7. Deploy new strict runtime/API/frontend atomically совместимой версией.
8. Purge/version frontend static cache and service worker.
9. Validate AgentCard, profile, ordinary SendMessage, A2UI stream, GetTask, embed CORS.
10. Remove temporary migration reader/feature flag after observation window.

Нельзя оставлять бесконечный dual-read `chat ?? interface` или dual-write обеих схем.

---

## 25. Полный тестовый план

### 25.1. Core A2A unit

Создать/расширить:

- `tests/core/a2a/test_artifact_accumulator.py`;
- `tests/core/a2a/test_task_projection.py`;
- `tests/core/a2a/test_codec.py`;
- `tests/core/a2a/test_task_json.py`.

Cases:

- each `text/raw/url/data`;
- mixed parts/order;
- arbitrary JSON scalar/list/object in data;
- metadata, filename, mediaType, description, extensions;
- append replace/append/lastChunk;
- stable artifact ID;
- duplicate sequence same/different hash;
- invalid oneof/kind/artifact ID;
- unknown artifacts;
- plain response does not disappear;
- no status/artifact duplicate.

### 25.2. A2A conformance

Расширить `tests/flows/a2a_conformance/`:

- blocking/stream/GetTask/ListTasks/Cancel/Subscribe/push parity;
- ordinary client without A2UI extension;
- optional AgentCard extension `required=false`;
- headers/version/CORS;
- all output Part types, not только input acceptance;
- restart/reconnect durability;
- multiple Tasks in one context;
- input-required resume same Task;
- next turn after terminal new Task;
- historyLength semantics;
- stable pagination;
- malformed optional A2UI Part does not poison unrelated artifacts.

Existing official A2A fixtures remain unchanged.

### 25.3. A2UI codec/domain

Создать:

- `tests/core/a2ui/test_v0_9_1_codec.py`;
- `tests/core/a2ui/test_message_batches.py`;
- `tests/core/a2ui/test_catalog_identity.py`;
- `tests/core/state/test_flow_ui_delta.py`;
- `tests/core/state/test_flow_ui_revision.py`;
- official/golden fixtures directory.

Cases:

- create/update/data/delete surface;
- sequential non-transactional wire apply;
- repaint batch signal;
- JSON Pointer escaping;
- binding roundtrip;
- Grid/Stack/Flex schema roundtrip;
- compact/medium/wide placement inheritance/override/reset;
- invalid column/span/row/nested-container constraints;
- layout semantic delta and snapshot equivalence;
- all catalog components;
- unsupported catalog/component fallback;
- v0.9.1 URI/MIME exactness;
- wire has no `kind`;
- domain state independent of wire version;
- snapshot vs minimal patch equivalence;
- exact catalog ID `https://linnex.io/a2ui/catalog/platform/v1`;
- primary и secondary configured Host дают одинаковый catalog ID, но разные корректные brand-aware API/embed origins;
- request Host не может подменить catalog identity;
- официальный A2UI extension URI остаётся на `a2ui.org`.

### 25.4. Interaction/security

- submit full data model;
- autosync `/values` до Submit без запуска graph;
- forced sync + Submit в одной atomic revision chain;
- accept only `/values`;
- stale/future revision;
- duplicate action ID;
- spoofed component/surface/task/context;
- hidden/unbound value injection;
- server revalidation despite client check;
- local action never invokes flow;
- only `platform.ui.submit` invokes flow;
- ordinary text A2A still invokes flow;
- subagent surface stripping/ownership;
- malicious markdown/URL/component depth/large payload;
- unauthorized embed origin/method.

### 25.4.1. Session continuity/share

Создать:

- `tests/flows/integration/test_flow_ui_session_continuity.py`;
- `tests/flows/api/test_flow_ui_shares.py`;
- `tests/frontend_core/unit/flow-ui/flow-ui-autosync.spec.js`;
- `tests/frontend_core/unit/flow-ui/flow-ui-recovery-journal.spec.js`;
- `tests/ui/e2e/test_flow_ui_reopen_and_share.py`.

Обязательные scenarios:

1. Заполнить несколько fields, дождаться `Saved`, закрыть страницу, открыть снова — те же values/component/page/revision.
2. Перезагрузить во время terminal, working и input-required Task — current document и accumulated artifacts не теряются.
3. Открыть новую вкладку с тем же context — authoritative snapshot тот же; default template не мелькает и не перезаписывает state.
4. Перейти на другую page/tab, открыть durable modal, reopen — тот же session-owned view state.
5. Изменить значение без Submit — flow invocation count остаётся нулём, reopen значение сохраняет.
6. Нажать Share при pending mutation — share API ждёт sync acknowledgement; получатель видит именно эту revision.
7. Share viewer получает тот же `contextId/documentId`, active page, values, tasks и artifacts, а не новую session.
8. Viewer не может sync/submit/cancel; collaborator может только разрешённые paths/actions.
9. Owner и collaborator одновременно меняют одно поле — deterministic revision conflict/rebase, без silent last-write-wins.
10. Revoke/expiry блокирует bootstrap, reconnect, sync и token refresh.
11. Abrupt offline close: тот же browser восстанавливает pending local journal; другой browser видит последнюю server-acknowledged revision; после reconnect mutation корректно rebased/synced.
12. Explicit «Создать копию» создаёт новый context/document; обычный Share этого не делает.
13. Template новой Flow version не сбрасывает уже существующий session document без explicit migration.
14. Большая история догружается pagination, но current screen сразу совпадает с snapshot.
15. Share redaction выдаёт согласованный экран без forbidden data/artifacts.

### 25.5. Durable execution

- UI delta replay from zero/snapshot;
- state hash determinism;
- restart while streaming;
- commit-before-publish recovery;
- fork/rewind/new Task immutability;
- task projection rebuild;
- artifact projection order/revision;
- concurrent submits/OCC;
- long context with multiple tasks;
- cleanup/retention does not break active GetTask.

### 25.6. Capability runners

Для Python/Node/Go/C#:

- platform effects collected separately;
- state cannot forge effects;
- manifest permission;
- invalid effect rejected;
- interrupt + effect ordering policy;
- retries/idempotency;
- UI command parity across languages;
- removal of `state.push_ui_event(s)/pop_ui_events`.

### 25.7. Frontend unit

Новая структура:

- `tests/frontend_core/unit/flow-ui/a2a-task-accumulator.spec.js`;
- `generic-part-projector.spec.js`;
- `a2ui-codec.spec.js`;
- `flow-ui-state.spec.js`;
- `flow-ui-controller.spec.js`;
- `flow-ui-profile.spec.js`;
- `layout-resolver.spec.js`;
- `render-context.spec.js`;
- `render-fingerprint.spec.js`;
- `production-render-frame.spec.js`;
- `snap-engine.spec.js`;
- `flow-ui-autosync.spec.js`;
- `flow-ui-recovery-journal.spec.js`;
- `embed-autoload.spec.js`;
- `hitl-transport.spec.js`;
- `voice-projection.spec.js`.

Cases повторяют backend golden fixtures; fixture drift запрещён.

### 25.8. Browser/component

- every catalog component contract;
- mixed ordinary Artifact render;
- append updates in place;
- multi-page navigation;
- form bindings/validation/submit;
- unknown component/invalid A2UI isolation;
- reconnect/hydration;
- atomic server snapshot hydration without default-template flash;
- `Saving/Saved/Offline` states and forced share/submit flush;
- same-session reopen and share viewer/collaborator permissions;
- drawer/page/panel/inline;
- light/dark/auto/custom primary color;
- keyboard/screen reader/focus/modal;
- responsive viewports;
- 4/8/12 column grid, nested grids, gaps/margins/max-width/baseline and responsive placements;
- grid/ruler/guide visibility never changes renderer DOMRect/computed styles;
- drag/resize produces semantic placement, not absolute CSS;
- selection overlay alignment at scroll, nested scroll, 50/100/200% editor zoom and device pixel ratios;
- target `page|panel|drawer|inline/embed` frame dimensions and shell insets;
- parity badge readiness/hash mismatch diagnostics;
- no arbitrary script execution;
- editor drag/drop/layers/inspector/undo/redo.

### 25.8.1. Обязательная editor/runtime WYSIWYG parity suite

Создать:

- `tests/frontend_core/browser/flow-ui/layout-grid.spec.js`;
- `tests/frontend_core/browser/flow-ui/production-render-frame.spec.js`;
- `tests/frontend_core/browser/flow-ui/renderer-inspection-bridge.spec.js`;
- `tests/frontend_core/browser/flow-ui/interface-editor-overlays.spec.js`;
- `tests/ui/e2e/test_flow_ui_grid_editor.py`;
- `tests/ui/e2e/test_flow_ui_editor_runtime_parity.py`;
- `tests/ui/e2e/fixtures/flow_ui_parity/` с immutable documents/data/task projections и manifest hashes.

Для каждой golden fixture один test запускает две стороны:

1. Interface editor production frame с overlay выключенным;
2. реальный user route/embed surface с тем же immutable document/state/render context.

После `parity-ready` сравниваются:

- exact component ID set, parent/child DOM order и accessible order;
- `getBoundingClientRect()`/scroll boxes каждого component;
- computed grid track list, gaps, paddings, container band, visibility, overflow и z-order;
- selected layout-affecting computed styles и CSS custom-property values;
- renderer build/catalog/token/font/asset/profile/context hashes;
- screenshot только внутренней production surface, без editor chrome.

Gates:

- в pinned Chromium CI при одинаковых viewport/DPR/fonts/assets screenshot diff должен быть **0 pixels**; generic percentage tolerance запрещён;
- маски допускаются только для явно перечисленных nondeterministic external pixels (например, remote video), не для текста, component geometry, shadows, focus или grid;
- geometry/layout snapshot должен быть byte-equivalent; rounding normalizer общий для обеих сторон и не может скрывать отличие больше `0.01 CSS px`;
- отдельная cross-browser suite (Chromium/WebKit/Firefox, supported versions) допускает различия rasterization, но требует одинаковых container bands, component order/visibility/values и geometry в documented `≤0.5 CSS px` browser tolerance;
- MutationObserver/DOM snapshot доказывает, что editor overlay не вставил wrapper/style/class в production tree;
- test намеренно меняет каждый fingerprint input и проверяет `Context differs`, затем выравнивает context и получает `Exact`;
- caret, active animation, current time и random content выключаются deterministic test context, а не скрываются широкой screenshot mask.

Обязательная scenario matrix:

- viewport: `390×844`, `430×932`, canonical tablet, `1440×1024`, custom bounded width на каждом container threshold ±1 px;
- surface: `page`, `panel`, `drawer`, `inline/embed`;
- layout: root/nested Grid, Stack/Flex conversion, 4/8/12 columns, full/span/start overrides, long/min-content/overflow;
- data: empty, filled form values, long RU/EN text, files, tables, charts, ordinary mixed A2A Artifacts и live Task state;
- look: light/dark/high-contrast/reduced-motion, primary Linnex brand и минимум один secondary configured domain profile;
- navigation: multi-page, active page, modal, session-restored view state;
- assets: bundled fonts/icons/images loaded, deliberately missing asset produces non-Exact/error state;
- permissions: owner/collaborator/viewer capability-dependent controls.

### 25.9. E2E migrations/renames

Переписать, не просто удалить, текущие suites:

- `tests/ui/e2e/test_flows_chat_page.py` → default chat template on Flow UI;
- `tests/ui/e2e/flows_chat_e2e_coverage_matrix.md` → Flow UI matrix;
- `tests/ui/e2e/test_embed_autoload_browser.py`;
- `tests/ui/e2e/test_landing_demo_chat_drawer.py`;
- `tests/ui/e2e/test_worktracker_hitl_chat.py`;
- `tests/e2e/voice/test_voice_chat.py`;
- frontend browser tests с `platform-chat` names;
- `tests/core/models/test_flow_chat_settings.py` → interface config/template migration tests;
- `tests/flows/api/test_chat_profile.py` → interface profile;
- `tests/frontend/api/test_embed_configs_api.py` → interface override;
- add new full Interface editor E2E.
- add `test_flow_ui_reopen_and_share.py` to the required release matrix, including cross-browser contexts.

### 25.10. Visual/performance/a11y

- screenshot matrix RU/EN × light/dark × page/panel/drawer × desktop/mobile;
- editor-frame ↔ real-user-route zero-pixel golden comparison в deterministic Chromium;
- grid overlay on/off DOMRect invariance и layout snapshot regression;
- axe/WCAG checks;
- keyboard-only authoring and submit;
- bundle size gate;
- render 100/1000 artifacts benchmark;
- patch frequency/frame budget;
- large table/file/mixed artifact memory test;
- embed host CSS isolation.

---

## 26. Rule/documentation changes before/with code

### 26.1. Replace the chat canon

- CREATE `.cursor/rules/flow_ui.mdc` — единственный новый UI canon, включая persisted grid/layout schema, render context/fingerprint и strict editor/runtime parity.
- DELETE `.cursor/rules/flows_chat.mdc` после обновления ссылок.
- UPDATE `.cursor/rules/main.mdc` index/domain names; удалить `ui_events_pending` canon.

### 26.2. Update related rules

Обязательные изменения:

- `.cursor/rules/a2a.mdc` — optional A2UI extension, lossless Artifact/task projections, headers;
- `streaming.mdc` — stable IDs, durable-before-publish, no custom `ui_event`;
- `flows.mdc` — universal renderer/editor/interaction;
- `execution_state.mdc` — full `ui_document`, interaction, frozen fields;
- `durable_execution.mdc` — UI/task events/projections/replay;
- `session.mdc` — context vs multiple tasks, authoritative reopen, A2A autosync и same-context share grants;
- `frontend.mdc` — `<platform-flow-ui>`, production render frame, overlay isolation and host contract;
- `ui_components.mdc` — trusted catalog/editor primitives, 4/8/12 grid, container bands и layout capabilities;
- `ui_factories.mdc` — new editor slices/events;
- `files.mdc` — Part projection and UI File components;
- `voice.mdc` — renderer-independent A2A/TTS;
- `handoff.mdc` — universal HITL surface;
- `agent_skills.mdc` — no `ui_event`;
- `integrations.mdc` — structured remote artifacts/A2UI ownership;
- `events.mdc` — durable A2A/UI events vs platform bus;
- `testing.mdc`, `testing_invariants.mdc` — new suites/gates, zero-pixel deterministic editor/runtime parity и cross-browser geometry contract;
- `architecture.mdc` — Flow UI layer/dependencies;
- `domain_naming.mdc` — component/surface/document/task/artifact terms.

### 26.3. API/docs

- regenerate both OpenAPI JSON files;
- update flow intro/catalog scenarios;
- add `docs/api/flows/flow-ui.md` with ordinary A2A and A2UI examples;
- add migration guide for embed consumers/new autoload URL;
- document public shim lifecycle;
- document catalog authoring and security.

---

## 27. Delete/keep manifest и zero-reference gates

### 27.1. DELETE after parity

- `core/models/flow_chat_settings.py`;
- `apps/flows/src/models/flow_chat_settings.py`;
- `apps/flows/src/streaming/ui_events.py`;
- `PendingUIEvent` and `ui_events_pending` definitions/serializers;
- capability `state.push_ui_event`, `push_ui_events`, `pop_ui_events`;
- `BaseEmitter.emit_ui_event` and overrides;
- весь `core/frontend/static/lib/chat/` после реального переноса функциональности;
- `<platform-chat-settings-fields>`;
- `/chat-profile` handlers/models/tests;
- custom `ui_event` branches in public search/run trace/runtime;
- transient `_uiBlocksByTaskId`;
- chat-only reducers/controllers/stubs;
- old i18n keys only after reference check.

### 27.2. KEEP as standard compatibility

- all A2A JSON-RPC/SSE methods;
- A2A SDK protobuf types;
- all four standard Part variants;
- arbitrary Artifact names and mixed Parts;
- Artifact/Part metadata/extensions;
- current named artifacts listed in 1.2;
- Files API → `Part.url` browser path and external `Part.raw` support;
- HITL ordinary artifacts/status;
- A2A protocol version 1.0 fixture pin;
- context/session semantics;
- public embed endpoint and auth/origin controls;
- existing public CDN script path as stateless import shim only.

### 27.3. MOVE, not lose

- markdown/citations/file/voice/HITL/run-trace behavior;
- current chat display modes;
- cancel, file upload, suggestions, greeting;
- tool/node/edge visualization;
- browser preview;
- host action hooks/Lara apply behavior;
- namespace headers;
- panel/launcher preferences;
- embed theming and voice flags.

### 27.4. Zero-reference commands at cutover

Команды выполняются read-only как gates; допустимы только intentional docs/migration fixture hits:

```bash
rg -n "FlowChatSettings|EmbedChatPolicyOverride|resolve_effective_flow_chat" core apps tests .cursor/rules
rg -n "chat_override|chat-profile|platform-chat|a2a-chat-runtime" core apps tests .cursor/rules
rg -n "ui_events_pending|PendingUIEvent|push_ui_event|emit_ui_event|artifact.name === 'ui_event'" core apps tests .cursor/rules
rg -n '"chat"\s*:' apps/flows/bundles tests/fixtures
rg -n -i "humanitec\.ai/a2ui|supportedCatalogIds.*humanitec" core apps tests .cursor/rules docs
```

Публичный `embed-chat/humanitec-embed-autoload.js` и историческая data migration могут быть единственными заранее перечисленными исключениями; каждое исключение документируется.

---

## 28. Acceptance criteria

Работа завершена только если одновременно истинно всё ниже.

### Protocol

- [ ] На wire используется только A2A 1.0 JSON-RPC/SSE.
- [ ] A2UI находится только в стандартном `Part.data` и optional extension.
- [ ] AgentCard объявляет A2UI `required=false`.
- [ ] AgentCard на всех configured platform domains объявляет canonical catalog `https://linnex.io/a2ui/catalog/platform/v1`.
- [ ] Runtime/API/embed/share origins остаются multi-domain и резолвятся по brand Host/config, а не подменяют catalog ID.
- [ ] Ordinary A2A client без extension вызывает flow и получает валидный результат.
- [ ] `text/raw/url/data`, mixed Parts, metadata/extensions round-trip без потерь.
- [ ] `SendMessage`, stream, push, Subscribe и GetTask согласованы.
- [ ] Artifact append использует постоянный ID.
- [ ] Один logical UI output не dual-emitted.

### State/durability

- [ ] Полный UI + values находится в `ExecutionState.ui_document`.
- [ ] UI semantic delta детерминированно replayable.
- [ ] Restart/reconnect восстанавливает document/tasks/artifacts.
- [ ] Reload, закрытие/повторное открытие, новая вкладка и другое устройство отрисовывают последнюю server-acknowledged revision с теми же active page, surfaces и values.
- [ ] Изменённые поля autosync через A2A до Submit; autosync не запускает flow.
- [ ] Pending offline mutations восстанавливаются локально и OCC-rebase после reconnect.
- [ ] Share-link ждёт forced sync и открывает тот же context/document, а не новый пустой template.
- [ ] Read-only/collaborator grants, expiry/revoke/redaction проверены end-to-end.
- [ ] Один context содержит много immutable Tasks.
- [ ] Fork/rewind не переписывает старые A2A Tasks.
- [ ] Stale revision и duplicate submit обрабатываются корректно.

### Security

- [ ] Browser не может менять `/content`/`/system`.
- [ ] Sandbox не может подделать platform effects через state.
- [ ] Нет arbitrary HTML/JS/catalog loading.
- [ ] Surface ownership работает для remote/subflows.
- [ ] Embed origin/auth/CORS включают новый header без ослабления.

### UI/editor

- [ ] `<platform-flow-ui>` — единственный renderer/runtime.
- [ ] Default chat — редактируемый template.
- [ ] Работает multi-page UI.
- [ ] Editor имеет Logic/Interface/Run, palette/layers/canvas/inspector/bindings.
- [ ] `Grid/Stack/Flex`, responsive placement, columns/spans/gaps/margins/max-width находятся в `FlowUIDocument` и durable replay, а не в editor-only state.
- [ ] Default grid preset 4/8/12, nested grids, baseline, rulers, guides, snap и keyboard authoring работают на всех обязательных viewport/container bands.
- [ ] Published interactive UI имеет `platform.ui.submit`.
- [ ] Preview загружает тот же compiled production renderer/catalog/layout resolver/tokens/fonts/assets и реальный target shell profile.
- [ ] Selection/grid overlays находятся вне production tree и не меняют его DOM, CSS, accessibility tree или geometry.
- [ ] `FlowUIRenderContext` явно фиксирует revision/state, viewport/DPR/surface, brand, theme, locale, assets, permissions и live data.
- [ ] `Exact` показывается только после asset readiness и полного fingerprint match; любое отличие даёт объяснимый `Context differs`.
- [ ] Editor frame и user route дают нулевой pixel diff в pinned deterministic Chromium и одинаковый layout contract в supported browsers.
- [ ] `Open on device` открывает immutable draft тем же production route, без отдельного preview implementation.
- [ ] SPA/embed/landing/Lara/HITL/voice используют общий runtime.
- [ ] Ordinary/unknown artifacts красиво и безопасно отображаются.
- [ ] RU/EN, light/dark, mobile/desktop, keyboard/screen reader gates пройдены.

### Clean cut

- [ ] Нет внутренних `FlowChatSettings`, `/chat-profile`, `platform-chat` runtime.
- [ ] Нет `ui_events_pending` и `ui_event` protocol branch.
- [ ] Нет permanent dual read/write/emit.
- [ ] Старые файлы удалены только после переноса поведения и тестов.
- [ ] Public CDN shim не содержит реализации.
- [ ] OpenAPI/docs/rules отражают один контракт.

---

## 29. Risk register

| Риск | Проявление | Митигация | Gate |
|---|---|---|---|
| A2UI v1 меняет schema | domain зависит от v0.9 JSON | version-neutral model + codec registry | codec fixture tests |
| Потеря ordinary artifacts | special response builder | shared lossless accumulator first | Phase 1 conformance |
| Dual output | text + A2UI duplicates | Task representation snapshot + no-dup invariant | golden stream tests |
| DB bloat chunks/raw | huge workflow/task JSONB | limits, URL for generated blobs, metrics, compaction | load/size tests |
| Redis/DB race | reconnect misses frame | commit/outbox before publish, sequence replay | crash tests |
| Stale UI overwrites | concurrent tabs/actions | revision/OCC + action idempotency | concurrency tests |
| Sandbox UI spoofing | returned state contains event | separate signed/caused effects | multi-language security tests |
| Editor/runtime drift | preview «похож», но собран другим кодом/CSS | один production frame/module + catalog/layout/token/font/asset hashes | zero-pixel parity E2E |
| Editor overlay искажает layout | wrapper/border/transform меняет размер component | overlay вне frame + read-only inspection bridge + DOM mutation assertions | overlay invariance tests |
| Неверный target context | editor ширина верна, но drawer/brand/locale/data отличаются | полный `FlowUIRenderContext`, target shell profiles и field-level fingerprint diff | context matrix E2E |
| Font/browser rasterization выдаётся за 1:1 | pixel diff между OS скрывает geometry bug | bundled font manifest, pinned Chromium zero diff, отдельный documented cross-browser geometry gate | visual/browser matrix |
| Responsive grid расходится | editor хранит coordinates отдельно от document | persisted Grid/placement + один layout resolver + semantic drag commands | grid roundtrip/browser tests |
| Existing integrations break | current artifact names removed | explicit KEEP list/adapters | compatibility matrix |
| Big-bang frontend regression | 15k lines chat behavior | extract by slices, parity suite, final delete gate | Phase 4/7 |
| Embed cache old JS | stale custom element contract | versioned asset/cache purge/public shim | embed E2E |
| Accessibility regression | generated layouts invalid | catalog constraints + editor problems + axe | a11y gate |
| External malicious A2UI | foreign surface/control | negotiation, catalog validation, ownership | security suite |
| Migration malformed row | strict model deploy fails | dry-run/preflight/fail-fast/backup | Phase 6 |
| Reopen показывает пустой default UI | hydration строится из template/history | authoritative full snapshot + skeleton + atomic store commit | continuity E2E |
| Закрытие до Submit теряет поля | values существуют только в DOM | debounced A2A autosync + forced flush + local recovery journal | autosync/crash tests |
| Share открывает новую conversation | reuse preview-share semantics | отдельный live grant, same context/document identity | share E2E |
| Share выдаётся до сохранения | pending mutation race | await mutation acknowledgement/minimum revision before mint | API concurrency tests |
| Два collaborator затирают данные | last-write-wins | revision/OCC, idempotent mutation IDs, conflict UX | multi-browser tests |
| Один catalog получает разные IDs на разных apex | ID строится из request Host | canonical `linnex.io` identity из primary domain + host-aware только runtime URLs | multi-domain AgentCard tests |

---

## 30. Implementation checklist by commit boundary

Рекомендуемые reviewable commit boundaries; каждый commit компилируется и тестируется:

1. `test(a2a): add lossless artifact parity fixtures`.
2. `feat(a2a): add shared artifact accumulator and stable emitter ids`.
3. `feat(durable): add task/message/artifact query projections`.
4. `refactor(a2a): unify blocking stream get subscribe task building`.
5. `refactor(a2a-client): preserve structured remote results`.
6. `feat(flow-ui-domain): add document interaction delta revision models`.
7. `feat(a2ui): add pinned v0.9.1 codec and optional negotiation`.
8. `feat(flow-ui): add representation selector and generic fallback`.
9. `feat(flow-ui-session): add A2A bootstrap autosync and authoritative snapshots`.
10. `feat(flow-ui-share): add same-context scoped live-session grants`.
11. `feat(capabilities): add trusted platform effects contracts`.
12. `refactor(runners): propagate platform effects in Python/Node/Go/C#`.
13. `refactor(flows): replace ui_events producers with typed UI effects/artifacts`.
14. `feat(frontend): add A2A accumulator and generic Part projector`.
15. `feat(flow-ui-layout): add versioned Grid Stack Flex and responsive placement`.
16. `feat(frontend): add trusted catalog, shared layout resolver and universal renderer`.
17. `feat(frontend): add render context fingerprint and production render frame`.
18. `feat(frontend): add atomic hydration autosync and recovery journal`.
19. `feat(frontend): implement default chat template parity`.
20. `refactor(frontend): migrate SPA/embed/Lara/landing/HITL/voice hosts`.
21. `feat(frontend): add viewer/collaborator shared-session surface`.
22. `feat(editor): add Interface workspace and semantic authoring commands`.
23. `feat(editor): add grid rulers guides snap overlays and layout inspector`.
24. `feat(editor): add fingerprint status exact target profiles and open-on-device preview`.
25. `feat(editor): add submit/binding/catalog/layout validation and publish gate`.
26. `migrate(config): FlowInterfaceConfig and EmbedInterfaceOverride storage`.
27. `docs(api): regenerate OpenAPI and replace chat canon rules`.
28. `refactor(clean): delete chat runtime, settings, ui_event paths`.
29. `test(e2e): final compatibility, continuity/share, editor/runtime zero-pixel, a11y and performance gates`.

Commits 26–28 могут быть squashed/reordered для deployment sequencing, но не должны создавать permanent compatibility code.

---

## 31. Финальная архитектурная формула

```text
ONE WIRE PROTOCOL
  A2A 1.0 Message / Task / Artifact / StreamResponse

ONE OPTIONAL UI REPRESENTATION
  A2UI v0.9.1 inside ordinary A2A data Parts, negotiated and required=false

ONE LOSSLESS TASK MODEL
  every text/raw/url/data Part and every current/unknown Artifact survives

ONE DURABLE UI STATE
  full FlowUIDocument + values in ExecutionState, ledger-backed and revisioned

ONE CONTINUOUS SESSION
  close / reload / another device / share -> the same acknowledged screen and data

ONE NON-INVOKING AUTOSYNC
  platform.ui.sync -> A2A control message -> durable values/view state, no flow run

ONE USER INVOCATION
  platform.ui.submit -> ordinary A2A Message -> new/resumed A2A Task

ONE CLIENT REDUCER
  A2A frame -> Task/Artifact accumulator -> A2UI or generic projection -> UI store

ONE RENDERER
  <platform-flow-ui>

ONE LAYOUT CONTRACT
  persisted Grid/Stack/Flex + responsive placement -> one shared layout resolver

ONE VISUAL TRUTH
  editor production frame == user production frame; overlays outside; fingerprint-proven Exact

ONE EDITOR
  Logic | Interface | Run

CHAT
  only the default editable Flow UI template
```

Главное следствие: появление A2UI не создаёт второй протокол и не отменяет обычные A2A artifacts. Оно добавляет стандартизированное декларативное представление UI в уже существующий A2A envelope. Все клиенты, включая не-UI клиенты, остаются частью одной архитектуры; различается только выбранная проекция результата.
