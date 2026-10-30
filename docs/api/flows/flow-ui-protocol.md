---
title: Flow UI поверх A2A
---

Интерфейс flow — это обычный A2A 1.0 без расширений. Дизайн-время описывает `FlowUIDocument` (страницы и блоки грамматики), рантайм идёт в Task: агент отправляет вниз артефакты `state`, текст и `ui`, клиент отправляет вверх обычное `Message`. Всё, что нужно клиенту, — четыре `mediaType` вниз, одно `Message` вверх и три `GET`.

Примеры JSON на этой странице совпадают с conformance-фикстурами `tests/fixtures/flow_ui/*.json`; их читают и pytest, и JS unit-тесты, поэтому браузерный рантайм, Python SDK и сервер видят протокол одинаково.

## Вниз: артефакты Task

Каждый артефакт различается по `artifactId` (системные `state`, `ui`) или по `name` (текстовые потоки). Клиент разбирает Part по `mediaType`.

| `artifactId` / `name` | `mediaType` Part | Что несёт |
|---|---|---|
| `state` | `application/json` | Снимок проекции state — первый Part артефакта в Task |
| `state` | `application/json-patch+json` | RFC 6902 `add`/`replace`/`remove` поверх предыдущего снимка |
| `ui` | `application/vnd.platform.ui+json` | Событие `render` (блоки в `slot_id`) или `navigate` (`page_id`) |
| `response`, `reasoning`, авторское имя | текстовый Part | Поток текста; чанки одного имени склеиваются |

Проекция `state` содержит только пути, на которые ссылается документ: `{path}` в шаблонах, `field` input-блоков, `path` условий `visible_when`, `fields` и `data-bind`/`data-show` блока `html`, а также пути блоков, отрисованных в ленту `conversation`. Системные поля `ExecutionState` в проекцию не попадают и в документе запрещены — их список отдаёт `GET /flow-ui/schema` в `x-flow-ui-frozen-state-fields`.

Parts артефакта `state` для одного Task в порядке появления, затем два события `ui` и текст:

```json title="tests/fixtures/flow_ui/ui_artifacts.json#parts"
[
  {"data": {"email": "a@b.c", "total": 1200}, "mediaType": "application/json"},
  {"data": [{"op": "replace", "path": "/total", "value": 1500}], "mediaType": "application/json-patch+json"},
  {"data": {"kind": "render", "slot_id": "result", "blocks": [{"block_id": "summary", "type": "text", "markdown": "Заявка **{email}** принята"}]}, "mediaType": "application/vnd.platform.ui+json"},
  {"data": {"kind": "navigate", "page_id": "done"}, "mediaType": "application/vnd.platform.ui+json"},
  {"text": "Готово"}
]
```

Событие `render` в `slot` страницы заменяет содержимое слота; `render` в `conversation` добавляет карточку в ленту. Любой другой `kind` или `mediaType` у `data` Part — ошибка протокола на обеих сторонах.

Патч state всегда выражается через add/replace/remove по JSON Pointer; сегменты с `/` и `~` экранируются как `~1` и `~0`:

```json title="tests/fixtures/flow_ui/state_patch.json#cases[0].operations"
[
  {"op": "replace", "path": "/status", "value": "sent"},
  {"op": "remove", "path": "/customer/phone"},
  {"op": "add", "path": "/customer/email", "value": "a@b.c"},
  {"op": "replace", "path": "/items", "value": [1, 2, 3]}
]
```

## Вверх: одно Message

Ход пользователя — обычное `Message` с `role: ROLE_USER`, `contextId` и, при продолжении Task, `taskId`. Вариантов два:

- `text` Part (плюс файлы `raw`/`url` Parts) — реплика в ленту;
- ровно один `data` Part `application/vnd.platform.ui-action+json` — действие интерактивного блока.

```json title="tests/fixtures/flow_ui/ui_action_message.json#part"
{
  "data": {
    "action": "submit",
    "source": "send_button",
    "fields": {"email": "a@b.c", "agree": true},
    "payload": {"plan": "pro"}
  },
  "mediaType": "application/vnd.platform.ui-action+json"
}
```

`action` — имя действия из `action.name` блока, `source` — `block_id` блока-источника, `fields` — значения input-блоков страницы по их `field`, `payload` — данные действия. Сервер проверяет `fields` по документу (обязательность, `pattern`, варианты `select`), записывает их в state по тем же путям и кладёт действие в `state.ui_action`:

```json title="tests/fixtures/flow_ui/ui_action_message.json#state_action"
{"name": "submit", "source": "send_button", "payload": {"plan": "pro"}}
```

Message с двумя `ui-action` Parts или с `ui-action` рядом с текстом отклоняется.

## Три GET

| Метод и путь | Что возвращает |
|---|---|
| `GET /flows/api/v1/{flow_id}/interface?branch_id=default` | `FlowInterfaceResponse`: `document`, `viewer` (права), `capabilities` (`cancel`/`files`/`voice`), `flow_identity`, `look` для embed. Для встраивания — `GET /flows/api/v1/embed/{embed_id}/interface` |
| `GET /flows/api/v1/flow-ui/schema` | JSON Schema `FlowUIDocument` (палитра и свойства редактора, structured output LLM) плюс `x-flow-ui-frozen-state-fields` |
| `GET /flows/api/v1/flow-ui/templates` | Галерея стартовых документов (`OffsetPage[FlowUITemplate]`) |

A2A JSON-RPC (`SendMessage`, `SendStreamingMessage`, `GetTask`, `ListTasks`, `SubscribeToTask`, `CancelTask`) принимается на `POST /flows/api/v1/{flow_id}`; ветка выбирается `metadata.branch`, переменные запуска — `metadata.variables`. Подробности A2A — на странице [Flows A2A API](index.md).

## Грамматика блоков

Единственная спецификация — Pydantic-модели `core/ui_document/document.py`; JSON Schema из `GET /flow-ui/schema` — их проекция. Документ:

```json title="tests/fixtures/flow_ui/ui_artifacts.json#document"
{
  "start_page_id": "main",
  "pages": [
    {
      "page_id": "main",
      "title": "Заявка",
      "blocks": [
        {"block_id": "title", "type": "heading", "text": "Заявка {?customer.name}", "level": 2},
        {"block_id": "email", "type": "text_input", "field": "email", "label": "Email", "required": true},
        {"block_id": "send_button", "type": "button", "label": "Отправить", "action": {"name": "submit", "payload": {"plan": "pro"}}},
        {"block_id": "result", "type": "slot", "title": "Результат"}
      ]
    },
    {"page_id": "done", "title": "Готово", "blocks": [{"block_id": "done_text", "type": "text", "markdown": "Спасибо, {email}"}]}
  ]
}
```

Группы блоков (поле `type`):

- раскладка — `section`, `columns`, `tabs`;
- контент — `heading`, `text`, `image`, `video`, `audio`, `code`, `badge`, `alert`, `metric`, `progress`, `status`, `empty_state`, `divider`;
- ввод — `text_input`, `number_input`, `select`, `checkbox`, `switch`, `slider`, `date_input`, `datetime_input`, `file_upload`, `voice_input`; у каждого `field` — путь state, `required`, `error_message`, опциональное `action`;
- действия — `button` (`action`), `link` (`page_id` или `url`);
- данные — `data_table`, `chart`, `json_view`, `file_card`, `file_list`;
- платформенные — `conversation`, `slot`, `agent_identity`, `avatar`, `run_trace`, `tool_activity`, `browser_preview`, `skill_activity`, `action_preview`, `action_result`, `reflection`, `activity`, `suggested_prompts`;
- свой код — `html`.

У любого блока есть `block_id` и `visible_when: {path, equals}` — блок показывается, когда значение по `path` равно `equals`; без `equals` — когда значение непустое (не `null`, `""`, `false`, `0` и не пустой массив).

### Шаблоны `{path}`

Текстовые свойства блоков — шаблоны над state: `{path}` подставляет значение (объекты и массивы — как JSON), `{?path}` даёт пустую строку вместо отсутствующего значения, `{path|запасной текст}` подставляет запасной текст, когда значение отсутствует или равно пустой строке; запасной текст сам может быть шаблоном, `\{` — литеральная скобка. Пути — `snake_case` с точками: `customer.name`. Шаблон с отсутствующим обязательным `{path}` не рендерится, пока значение не появится.

```json title="tests/fixtures/flow_ui/templating.json#cases[0]"
{"name": "nested_path", "template": "Привет, {customer.name}!", "state": {"customer": {"name": "Анна"}}, "paths": ["customer.name"], "text": "Привет, Анна!"}
```

### Блок `html`

`source` — HTML/CSS/JS автора, исполняется в iframe с opaque origin: атрибут `sandbox="allow-scripts"` и фиксированный CSP в `srcdoc`:

```text
default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: https:; font-src data: https:; media-src https:
```

Внутрь приходит проекция state только по `fields` блока и путям `data-bind`/`data-show` из разметки; наружу уходят сообщения моста. API `window.flowUi`:

| Вызов | Действие |
|---|---|
| `flowUi.state` | Текущая проекция state |
| `flowUi.onChange(cb)` | Подписка на новые проекции; возвращает функцию отписки |
| `flowUi.send(action, payload)` | Ход `ui-action` во flow от имени блока (`source` = `block_id`) |
| `flowUi.setValue(value)` | Локальное значение поля `field` блока — уйдёт в `fields` следующего действия |
| `flowUi.resize()` | Пересчёт высоты при `height: "auto"` |
| `flowUi.openUrl(url)` | Открыть `http(s)` ссылку в новой вкладке |

Путь, который читает только скрипт (без `data-bind`/`data-show`), перечисляется в `fields` блока — иначе его нет в проекции. Тема хоста приходит CSS-переменными `--flow-ui-*` (`text`, `heading`, `muted`, `border`, `panel`, `surface`, `input`, `accent`, `accent-hover`, `on-accent`, `accent-muted`, `radius`, `radius-md`, `page-background`) и обновляется без перезагрузки iframe. Новый блок в редакторе создаётся со стартовым исходником, где каждый приём (`data-bind`, `data-show`, `flowUi.onChange`, `flowUi.send`, `flowUi.setValue`, `flowUi.openUrl`, токены темы) показан и прокомментирован; полноэкранный редактор блока держит рядом живой sandbox-предпросмотр с тестовым state, журнал моста и шпаргалку API.

Элементы с `data-bind="path"` получают текст значения, `data-show="path"` скрывает элемент при пустом значении:

```json title="tests/fixtures/flow_ui/html_sandbox.json#bound_paths_cases[0]"
{"name": "bind_and_show_in_order", "source": "<section data-show=\"order\"><b data-bind=\"order.total\"></b><i data-bind='customer.name'></i></section>", "paths": ["order", "order.total", "customer.name"]}
```

## Как агент меняет интерфейс

В `llm_node` доступны тулы `ui_render(slot_id, blocks)`, `ui_navigate(page_id)` и `state_set(path, value)`; code-ноды меняют state напрямую. Runtime после каждого шага публикует накопленные события `ui`, затем разницу проекции state — клиенту не нужно ничего запрашивать.

## SDK

Браузер — `core/frontend/static/lib/flow-ui/runtime/flow-ui-client.js` (тот же модуль использует `<platform-flow-ui>`):

```javascript
import { FlowUIClient } from '/static/core/lib/flow-ui/runtime/flow-ui-client.js';

const client = new FlowUIClient({ baseUrl: 'https://acme.linnex.io/flows', flowId: 'lead_form' });
client.on('state', (state) => console.log(state.total));
client.on('ui', (event) => console.log(event.kind));
await client.open();
await client.send({ action: { action: 'submit', source: 'send_button', fields: { email: 'a@b.c' }, payload: {} } });
```

Python — `core.clients.flow_ui_client.FlowUIClient` поверх `A2AClient`:

```python
from core.clients.flow_ui_client import FlowUIClient
from core.ui_document.protocol import FlowUIActionMessage

client = FlowUIClient("https://acme.linnex.io/flows", flow_id="lead_form")
interface = await client.open()
result = await client.send(action=FlowUIActionMessage(action="submit", source="send_button", fields={"email": "a@b.c"}))
print(client.state["total"], [event.kind for event in client.events()])
```
