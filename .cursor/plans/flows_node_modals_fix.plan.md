---
name: Flows node modals fix
overview: "Принцип: инструмент внутри LLM-ноды по настройкам не отличается от той же сущности как отдельной ноды на канве — UI редактирования тот же класс (те же flows-*-node-editor / тот же контракт), не параллельные «tool»-модалки. Плюс починка code_tool_source для code-ноды (function mode)."
todos:
  - id: fix-code-tool-source
    content: "codeToolSourceOp: query tool_path; editor читает lastResult.source; restMirror/CI при необходимости"
    status: completed
  - id: tool-equals-node-ui
    content: "Клик по tool chip / edit в LLM: открывать тот же тип UI, что и для standalone ноды этого типа (те же компоненты модалки/панели, без отдельного flows.tool_create как единственный путь)"
    status: completed
  - id: map-toolref-to-node
    content: Явно описать в коде маппинг ToolReference → node type + тот же редактор (в т.ч. node-in-flow vs registry); убрать дублирование настроек между tool_create и code/llm редакторами где это одно и то же
    status: completed
  - id: tests
    content: "Тесты: tool-source; при наличии — pure helper маппинга ref→редактор"
    status: completed
  - id: i18n-base-node-editor
    content: "Сырые ключи base_node_editor.* в модалке: static i18nNamespace=flows на flows-base-node-editor (и при необходимости дочерних), проверка портала platform-modal-stack"
    status: pending
  - id: code-editor-ux-data
    content: "Пустой inline-код: проверить цепочку nodeConfig.code → flows-code-editor; при необходимости init CodeMirror в firstUpdated; опционально UX как у prompt-editor (fullscreen) в рамках flows-code-editor + канон emit/фабрики"
    status: pending
isProject: false
---

# План: модалки / редакторы tools в LLM и code-нода

## Принцип (зафиксировано)

**Любой тип может быть инструментом внутри LLM-ноды, но по смыслу настроек он ничем не отличается от той же сущности, если бы она стояла на канве отдельной нодой.**

Следствие для UI:

- **Показывать и редактировать** такой instrument **теми же средствами**, что и standalone-ноду того же типа: те же [`flows-*-node-editor`](apps/flows/ui/components/nodes/) (и при необходимости те же обёртки/модалки, что уже используются для этого `node.type` в [`flows-property-panel.js`](apps/flows/ui/components/editor/flows-property-panel.js)), а не отдельную параллельную «тульную» форму, которая дублирует поля и расходится с канвой.
- Отдельные модалки вроде [`flows-tool-create-modal.js`](apps/flows/ui/modals/flows-tool-create-modal.js) имеют смысл **только** там, где речь именно о **сущности реестра** inline tools (API `/flows/api/v1/tools`), а не как универсальный редактор «любой tool в LLM».

Практически: при клике с канваса / из списка tools **решать, какой `NodeConfig`+`type` за этим стоит**, и вести в **тот же** редактор, что в `switch (node.type)` property panel (модалка с вложенным `flows-code-node-editor` / `flows-llm-node-editor` / … — по одному канону с канвой).

## Проблема: broken UX сейчас

- Ветка «edit tool» уводит в `flows.tool_create` с пустыми полями — это **другой** UI, чем у ноды того же типа на канве.
- Для code-ноды в function mode: сломана связка [`codeToolSourceOp`](apps/flows/ui/events/resources/code.resource.js) / [`get_tool_source`](apps/flows/src/api/v1/code.py) (query `tool_path`, поле ответа `source`) — см. деталь в предыдущей версии плана.

## Направление работ (без прежнего «универсального tool modal»)

1. **Карта соответствия** `ToolReference` / ссылок на ноды графа / registry → `NodeType` + **тот же** компонент редактора, что для standalone (возможен wrapper: тот же editor, другой `nodeId`/`context=embedded` при необходимости, но не другая схема полей).
2. **Deprecate / сузить** использование `flows.tool_create` только к операциям **реестра** tools, если они остаются отдельно от нод; при совпадении с формой code-ноды — **не** дублировать, а открывать code-редактор.
3. **Исправить** `code_tool_source` (путь запроса + `source` в UI) для [`flows-code-node-editor.js`](apps/flows/ui/components/nodes/flows-code-node-editor.js).

## Тесты

- Минимум: HTTP/контракт `code/tool-source` + при наличии — тест маппинга ref → тип редактора (pure).

## Бэкенд-реальность

Как `tools[]` в `llm_node` [инлайнится](apps/flows/src/api/v1/flows.py) и как `NodeAsToolWrapper` [резолвит](apps/flows/src/runtime/) ноды, нужно сверить при реализации, чтобы **один** источник правды в JSON и один UI — без расхождений.

---

## Итерация: «крутой редактор в core», пустой код, сырые i18n (скриншот)

### Что показал git (~4 дня назад и ветка UI Events)

- **Общий CodeMirror** лежит в репозитории: [`core/frontend/static/assets/codemirror/codemirror-bundle.js`](core/frontend/static/assets/codemirror/codemirror-bundle.js) (vendored bundle).
- Им пользуются:
  - [`core/frontend/static/lib/components/prompt-editor.js`](core/frontend/static/lib/components/prompt-editor.js) — «богатый» редактор промптов (CodeMirror, режимы, подсветка шаблонов).
  - [`apps/flows/ui/components/editors/flows-code-editor.js`](apps/flows/ui/components/editors/flows-code-editor.js) — обёртка для Python/JSON/text, `useOp('flows/code_completions')`, `select` темы.
- В коммитах UI Events **удалён** [`apps/flows/ui/components/editors/flows-prompt-editor.js`](apps/flows/ui/components/editors/flows-prompt-editor.js) — это был **textarea** с `@var:`, не CodeMirror; не замена «крутого» редактора кода.
- **Отдельного** «потерянного» файла `core/.../code-editor.js` под flow code node в истории не видно: канон для Python в flows — [`flows-code-editor`](apps/flows/ui/components/editors/flows-code-editor.js).

### Сырые строки `base_node_editor.*` / `BASE_NODE_EDITOR.*` в UI

- В коде используется `this.t('base_node_editor.section_basic')` и т.д. ([`flows-base-node-editor.js`](apps/flows/ui/components/nodes/flows-base-node-editor.js)); при **неудачном резолве** namespace [`translate`](core/frontend/static/lib/events/effects/i18n.effect.js) возвращает **сам ключ**.
- У `FlowsBaseNodeEditor` **нет** `static i18nNamespace = 'flows'`, полагаемся на `defaultI18nNamespace` `PlatformApp`. В модалке/портале контекст может отличаться — **плановая правка**: явно задать `static i18nNamespace = 'flows'` на базе (и при необходимости на других flows-редакторах, где только `t()` без ns).

### Пустая область кода (inline), хотя ожидается «код есть»

- Возможные линии:
  1. **Данные**: `nodeConfig.code` в flow реально пустая строка (новая нода / не сохранили).
  2. **Связка**: вложенный редактор/модалка не прокидывает `code` в `nodeConfig` до первого рендера.
  3. **Жизненный цикл CodeMirror**: `_init` в `connectedCallback` + `querySelector('#cm-host')` — при гонке host может отсутствовать (стоит **проверить** и при необходимости инициализировать в `firstUpdated` / повторный `_init`, без фолбеков в данных).
- **Опционально (UX)**: не переносить `flows-code-editor` в `core` с `useOp('flows/...')` — нарушает границу core/apps. Вместо этого **усилить** [`flows-code-editor.js`](apps/flows/ui/components/editors/flows-code-editor.js) паттернами из [`prompt-editor.js`](core/frontend/static/lib/components/prompt-editor.js) (fullscreen, панель действий), с сохранением канона: **только** `emit('change'|'save')`, completions через существующую фабрику `flows/code_completions`.

### Соответствие правилам (frontend / ui_events / ui_factories / ui_components)

- Не вводить HTTP в pages/modals/components вне `events/resources`.
- Presentsational в core без bus; **flows-code-editor** остаётся в `apps/flows` как контейнер с `useOp`/`select`, либо выделить **тонкий** presentational слой в core без импорта `apps/`.
- Ключи i18n — парно ru/en, `make check-i18n`.
