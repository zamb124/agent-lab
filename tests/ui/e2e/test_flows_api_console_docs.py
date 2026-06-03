"""Документационный сценарий API Console для Flows."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_flow,
    flows_click_platform_button,
    flows_doc_flow_id,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

INTRO_DETAILS_RU = """
API Console открывается из редактора flow кнопкой `API` в верхней панели. Это не отдельный тестовый
стенд и не пример "примерно как надо": модалка строит endpoint, branch, JSON body, headers и code
samples из текущего `flow_id`, активной ветки и текущих переменных flow.

Кнопки в шапке модалки:

- `Инструкция` открывает эту страницу документации в `/documentation/scenarios/flows/api-console/`.
- `Копировать JSON body` копирует текущий A2A JSON-RPC body для выбранного режима.
- `Fullscreen` разворачивает модалку, когда нужно читать большие JSON/SSE ответы.
- `Close` закрывает модалку и возвращает в редактор.

Левая колонка всегда остается навигацией: карточка endpoint показывает, куда отправлять POST,
какой `branch_id` выбран, какой протокол используется и какой режим активен. Ниже четыре вкладки:
`Старт`, `Примеры`, `Поля A2A`, `Запуск`.
"""

INTRO_DETAILS_EN = """
API Console opens from the flow editor through the `API` button in the top bar. It is not a detached
static sample: the modal builds endpoint, branch, JSON body, headers, and code samples from the
current `flow_id`, active branch, and current flow variables.

Header buttons:

- `Guide` opens this documentation page at `/documentation/scenarios/flows/api-console/`.
- `Copy JSON body` copies the current A2A JSON-RPC body for the selected mode.
- `Fullscreen` expands the modal when you need to inspect large JSON/SSE responses.
- `Close` returns to the editor.

The left column is persistent navigation: the endpoint card shows where to send POST requests,
which `branch_id` is selected, which protocol is used, and which mode is active. The tabs are:
`Start`, `Examples`, `A2A fields`, and `Run`.
"""

START_DETAILS_RU = """
Вкладка `Старт` отвечает на вопрос "что мне отправить самым первым запросом".

В верхнем блоке:

- `flow_id` показывает точный ID агента из URL и endpoint.
- `branch_id` показывает ветку выполнения. Для базовой ветки UI показывает `default`.
- `contextId` показывает пример ID диалога. Повторяйте один и тот же `contextId`, чтобы продолжать
  разговор; создавайте новый, чтобы начать чистую сессию.
- счетчик переменных показывает, сколько flow variables есть у текущей ветки.

Переключатель режима меняет весь пример сразу:

- `Streaming` использует `method: "message/stream"` и `Accept: text/event-stream`.
- `Sync` использует `method: "message/send"` и `Accept: application/json`.
- `Async` использует `method: "message/send"` плюс `metadata.execution_mode: "async"`.

Ниже карточки режимов и таблица методов A2A. В обычной интеграции чаще всего нужны
`message/stream`, `message/send` и `tasks/get`; остальные методы нужны для отмены, resubscribe,
Agent Card и push notification config.
"""

START_DETAILS_EN = """
The `Start` tab answers "what should I send first".

Top metrics:

- `flow_id` is the exact agent id from the URL and endpoint.
- `branch_id` is the execution branch. The base branch is exposed as `default`.
- `contextId` is a sample conversation id. Reuse the same `contextId` to continue a conversation;
  generate a new one for a clean session.
- the variables counter shows how many flow variables exist in the active branch.

The mode selector updates the whole example:

- `Streaming` uses `method: "message/stream"` and `Accept: text/event-stream`.
- `Sync` uses `method: "message/send"` and `Accept: application/json`.
- `Async` uses `method: "message/send"` plus `metadata.execution_mode: "async"`.

The cards and method table explain A2A methods. Most integrations need `message/stream`,
`message/send`, and `tasks/get`; the other methods cover cancel, resubscribe, Agent Card, and
push notification config.
"""

EXAMPLES_DETAILS_RU = """
Вкладка `Примеры` дает готовые варианты для внешнего клиента.

Что здесь есть:

- языки `curl`, `Python`, `JS`; переключение меняет только код, но не смысл запроса;
- кнопка `Копировать` копирует текущий пример целиком;
- блок `Текущий JSON body` показывает тот же payload, который уйдет в live-run;
- блок `Файлы` показывает A2A `file` part. URI-файл передается с `name` и `mimeType`, а backend
  нормализует его в `state.files`; audio-file дополнительно проходит STT, если voice runtime настроен.

Минимальный JSON-RPC body:

- `jsonrpc: "2.0"` всегда фиксирован.
- `id` нужен клиенту, чтобы сопоставить ответ с запросом.
- `method` зависит от режима.
- `params.message.messageId` уникален для входного сообщения.
- `params.message.role` обычно `user`.
- `params.message.parts` содержит `text`, `file` или `data`.
- `params.message.contextId` связывает сообщения в один диалог.
- `params.metadata.branch` выбирает ветку выполнения.
- `params.metadata.variables` передает runtime variables только для этого запуска.
"""

EXAMPLES_DETAILS_EN = """
The `Examples` tab provides ready-to-use external client snippets.

It contains:

- `curl`, `Python`, and `JS` tabs; switching tabs changes code syntax, not the request meaning;
- a `Copy` button that copies the current example;
- `Current JSON body`, which is the same payload used by live-run;
- `Files`, which shows an A2A `file` part. URI files include `name` and `mimeType`; the backend
  normalizes them into `state.files`. Audio files also go through STT when voice runtime is configured.

Minimal JSON-RPC body:

- `jsonrpc: "2.0"` is fixed.
- `id` lets the client match response to request.
- `method` depends on the selected mode.
- `params.message.messageId` is unique for this input message.
- `params.message.role` is usually `user`.
- `params.message.parts` contains `text`, `file`, or `data`.
- `params.message.contextId` ties messages into one conversation.
- `params.metadata.branch` selects the execution branch.
- `params.metadata.variables` sends runtime variables for this run only.
"""

FIELDS_DETAILS_RU = """
Вкладка `Поля A2A` нужна, когда непонятно, зачем конкретное поле существует.

Главные нюансы:

- `metadata.branch` выбирает ветку графа. Если выбрать base в UI, API получает `default`.
- `metadata.variables.branch_id` не выбирает ветку. Это обычная runtime-переменная; backend только
  копирует ее в `target_branch_id`, если `target_branch_id` не был передан явно.
- `metadata.version` выбирает версию flow, но query `?v=...` имеет приоритет.
- `metadata.execution_mode` в `message/send` со значением `async` или `background` включает
  асинхронный запуск.
- `metadata.breakpoints` и `metadata.triggers` нужны редактору/debug/trigger runtime; обычному
  публичному клиенту они чаще всего не нужны.

Переменные:

- `metadata.variables` перекрывают flow variables только на время одного запуска.
- Значение может быть примитивом, объектом или массивом.
- Строки с `@var:key` резолвятся через company VariablesService; поддерживается вложенный JSON и
  рекурсивные ссылки вроде `@var:api_endpoint`, если сама переменная содержит `@var:base_url`.
- Если передать объект формата flow variable (`value`, `secret`, `public`, `title`, `description`),
  runtime использует `value`, а остальные поля служат для UI/документации.
- `secret` скрывает значение в UI, но не меняет поведение runtime.
- `public` показывает переменную в Agent Card как параметр, который должен заполнить внешний клиент.

Системные переменные (`user_id`, `company_id`, `active_namespace` и другие) добавляет backend из
авторизованного HTTP-контекста после клиентских variables, поэтому внешний клиент не может подделать
пользователя или компанию через `metadata.variables`.
"""

FIELDS_DETAILS_EN = """
The `A2A fields` tab explains why each field exists.

Important details:

- `metadata.branch` selects the graph branch. When the UI is on base, the API receives `default`.
- `metadata.variables.branch_id` does not select the branch. It is a normal runtime variable; the
  backend only copies it to `target_branch_id` when `target_branch_id` is absent.
- `metadata.version` selects a flow version, but query `?v=...` wins.
- `metadata.execution_mode` on `message/send`, with `async` or `background`, enables asynchronous run.
- `metadata.breakpoints` and `metadata.triggers` are for editor/debug/trigger runtime; most public
  clients do not need them.

Variables:

- `metadata.variables` override flow variables only for this run.
- Values can be primitives, objects, or arrays.
- Strings containing `@var:key` resolve through the company VariablesService; nested JSON and
  recursive references are supported, for example `@var:api_endpoint` whose stored value contains
  `@var:base_url`.
- If you pass a flow-variable object (`value`, `secret`, `public`, `title`, `description`), runtime
  uses `value`; the other fields are for UI/docs.
- `secret` masks the value in UI, but does not change runtime behavior.
- `public` exposes the variable in the Agent Card as a parameter external clients should fill.

System variables (`user_id`, `company_id`, `active_namespace`, and others) are appended by the backend
from the authorized HTTP context after client variables, so external clients cannot spoof user or
company identity through `metadata.variables`.
"""

RUN_STREAM_DETAILS_RU = """
Вкладка `Запуск` — рабочий стол тестирования реального API.

Левая колонка:

- `Режим` выбирает Streaming/Sync/Async и сразу перестраивает method, Accept header и JSON body.
- `contextId` задает диалог. Оставьте его тем же для продолжения, нажмите `Новый contextId` для
  чистой сессии.
- `Сообщение` становится `params.message.parts[0].text`.
- `metadata.variables JSON` попадает в `params.metadata.variables`.
- `Run` отправляет настоящий запрос в текущий `/flows/api/v1/{flow_id}` с текущей browser-сессией.
- `Предпросмотр запроса` показывает HTTP method, Accept, Content-Type, credentials и полный body.

Для Streaming UI отправляет `message/stream`, читает реальные SSE frames и собирает ответ агента из
этих событий. Это режим по умолчанию для чатового UX: пользователь видит ответ по мере генерации,
а разработчик может смотреть каждое событие отдельно.
"""

RUN_STREAM_DETAILS_EN = """
The `Run` tab is the real API testing workbench.

Left column:

- `Mode` selects Streaming/Sync/Async and immediately updates method, Accept header, and JSON body.
- `contextId` sets the conversation. Keep it to continue, or click `New contextId` for a clean session.
- `Message` becomes `params.message.parts[0].text`.
- `metadata.variables JSON` becomes `params.metadata.variables`.
- `Run` sends a real request to the current `/flows/api/v1/{flow_id}` using the browser session.
- `Request preview` shows HTTP method, Accept, Content-Type, credentials, and the full body.

For Streaming the UI sends `message/stream`, reads real SSE frames, and assembles the agent response
from those events. This is the default chat UX mode: the user sees generation progress, while the
developer can inspect every event.
"""

INSPECTOR_DETAILS_RU = """
Инспектор ответа показывает не только итоговый текст, но весь API-ответ.

Верхняя полоска статуса:

- `HTTP status` и `Content-Type` приходят из реального HTTP response.
- `task_id` создается backend и нужен для `tasks/get`, `tasks/cancel`, `tasks/resubscribe`.
- `context_id` подтверждает, в какой диалог попал запрос.
- `Состояние A2A` показывает `submitted`, `working`, `input-required`, `completed`, `failed` и другие
  состояния task.
- `SSE события` показывает количество stream frames.

Вкладки инспектора:

- `JSON-ответ` — нормализованный JSON body для текущего режима.
- `SSE события` — массив реальных stream events: status updates, artifact updates, final states.
- `Заголовки` — HTTP headers ответа.
- `Raw-ответ` — исходный текст ответа без нормализации.
- `Async опросы` — запросы/ответы `tasks/get`, которые UI делал после async-submit.
- `Полный result` — полный объект, который вернул frontend resource: request envelope, response
  envelope, parsed body, raw text, frames, polls, extracted text и ошибки.
"""

INSPECTOR_DETAILS_EN = """
The response inspector shows more than the final text: it exposes the whole API response.

Status strip:

- `HTTP status` and `Content-Type` come from the real HTTP response.
- `task_id` is created by the backend and is used by `tasks/get`, `tasks/cancel`, and `tasks/resubscribe`.
- `context_id` confirms which conversation handled the request.
- `A2A state` shows task states such as `submitted`, `working`, `input-required`, `completed`, and
  `failed`.
- `SSE events` shows the number of stream frames.

Inspector tabs:

- `JSON response` is the normalized JSON body for the current mode.
- `SSE events` is the array of real stream events: status updates, artifact updates, final states.
- `Headers` are HTTP response headers.
- `Raw` is the unnormalized response text.
- `Async polls` shows `tasks/get` request/response pairs performed after async submit.
- `Full result` is the complete frontend resource result: request envelope, response envelope, parsed
  body, raw text, frames, polls, extracted text, and errors.
"""

SYNC_DETAILS_RU = """
Sync нужен, когда внешний клиент хочет один HTTP response без чтения SSE.

UI отправляет:

- `method: "message/send"`;
- `Accept: application/json`;
- без `metadata.execution_mode: "async"`.

HTTP-запрос ждет завершения flow и возвращает JSON-RPC response с финальным A2A Task. Этот режим
проще для backend-to-backend интеграций, cron jobs и коротких deterministic flow. Если flow может
работать долго, лучше использовать Streaming или Async, чтобы не держать HTTP request открытым.
"""

SYNC_DETAILS_EN = """
Sync is for clients that want one HTTP response without reading SSE.

The UI sends:

- `method: "message/send"`;
- `Accept: application/json`;
- no `metadata.execution_mode: "async"`.

The HTTP request waits for the flow to finish and returns a JSON-RPC response with the final A2A Task.
This is simpler for backend-to-backend calls, cron jobs, and short deterministic flows. If the flow can
take a long time, use Streaming or Async instead of keeping the HTTP request open.
"""

ASYNC_DETAILS_RU = """
Async нужен для долгих задач и фоновых запусков.

UI отправляет:

- `method: "message/send"`;
- `Accept: application/json`;
- `metadata.execution_mode: "async"`.

Первый ответ должен вернуться быстро со state `submitted` и `task_id`. После этого результат получают
через `tasks/get` по `task_id` или `contextId`. В этой модалке `Async опросы` показывает, какие
`tasks/get` запросы были сделаны и какой финальный Task вернулся.

Типовые сценарии:

- Первый запрос: создайте новый `contextId`, заполните сообщение и нажмите `Run`.
- Продолжение диалога: оставьте прежний `contextId`, отправьте следующее сообщение.
- Ветка: меняйте ветку в редакторе; API использует `metadata.branch`.
- Runtime variables: заполните `metadata.variables JSON`, например `{"customer_name":"Anna"}`.
- Переменные-секреты: передавайте `@var:secret_key`, если значение лежит в VariablesService.
- Ошибка `failed`: смотрите `JSON-ответ`, `Raw-ответ` и `Полный result`.
- Ошибка `input-required`: task ждет пользовательский ввод; отправьте следующее сообщение с тем же
  `contextId`.
"""

ASYNC_DETAILS_EN = """
Async is for long-running and background tasks.

The UI sends:

- `method: "message/send"`;
- `Accept: application/json`;
- `metadata.execution_mode: "async"`.

The first response should return quickly with state `submitted` and `task_id`. Then fetch the result
through `tasks/get` using `task_id` or `contextId`. In this modal, `Async polls` shows which
`tasks/get` requests were made and what final Task was returned.

Typical scenarios:

- First request: create a new `contextId`, fill the message, and click `Run`.
- Continue conversation: keep the same `contextId` and send the next message.
- Branch: change branch in the editor; the API uses `metadata.branch`.
- Runtime variables: fill `metadata.variables JSON`, for example `{"customer_name":"Anna"}`.
- Secret variables: send `@var:secret_key` when the value is stored in VariablesService.
- `failed` error: inspect `JSON response`, `Raw`, and `Full result`.
- `input-required`: the task waits for user input; send the next message with the same `contextId`.
"""


def _api_docs_flow_payload(flow_id: str) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": "API Console docs flow",
        "description": "Deterministic flow for API Console documentation screenshots.",
        "entry": "compose",
        "nodes": {
            "compose": {
                "type": "code",
                "name": "Compose API response",
                "code": (
                    "async def run(args, state):\n"
                    "    state['response'] = "
                    "f\"API_DOC_OK:{args['salutation']}|"
                    "{args['target_branch_id']}|{args['customer_name']}|{args['extra']}\"\n"
                    "    return state\n"
                ),
                "input_mapping": {
                    "salutation": "@var:salutation",
                    "target_branch_id": "@var:target_branch_id",
                    "customer_name": "@var:customer_name",
                    "extra": "@var:extra",
                },
                "pos_x": 520,
                "pos_y": 280,
            }
        },
        "edges": [{"from_node": "compose", "to_node": None}],
        "variables": {
            "salutation": {
                "value": "hello-from-flow",
                "public": True,
                "title": "Greeting",
                "description": "Greeting text used by the deterministic docs flow.",
                "order": 1,
            },
            "customer_name": {
                "value": "Anna",
                "public": True,
                "title": "Customer name",
                "description": "Name supplied by the external API client.",
                "order": 2,
            },
            "target_branch_id": {
                "value": "flow-default-target",
                "public": False,
                "title": "Target branch variable",
                "description": "Demonstrates metadata.variables.branch_id -> target_branch_id copy.",
                "order": 3,
            },
            "extra": {
                "value": "flow-extra",
                "public": True,
                "title": "Extra payload",
                "description": "Small extra value used in screenshots.",
                "order": 4,
            },
            "api_secret": {
                "value": "@var:external_api_token",
                "secret": True,
                "public": False,
                "title": "External API token",
                "description": "Example of a secret company variable reference.",
                "order": 5,
            },
        },
        "tags": ["docs", "scenario", "api"],
        "branches": {},
        "triggers": {},
        "resources": {},
    }


async def _open_api_console(page: Page, flow_id: str, flows_ui: AppUI) -> Any:
    await page.set_viewport_size({"width": 1600, "height": 920})
    await page.goto(f"{flows_ui.origin}/flows/{flow_id}/editor", wait_until="domcontentloaded")
    await expect(page.locator("flow-editor-page")).to_be_visible(timeout=30_000)
    api_button = page.locator("flows-editor-header button.header-btn").filter(has_text=re.compile(r"API")).first
    await expect(api_button).to_be_visible(timeout=30_000)
    await api_button.click()
    modal = page.locator("flows-api-console-modal[open]").first
    await expect(modal).to_be_visible(timeout=30_000)
    await expect(modal.locator("a.docs-link")).to_have_attribute(
        "href",
        re.compile(r"/documentation/scenarios/flows/api-console/$"),
        timeout=30_000,
    )
    return modal


async def _click_nav(modal: Any, label_pattern: str) -> None:
    button = modal.locator(".api-nav button").filter(has_text=re.compile(label_pattern)).first
    await expect(button).to_be_visible(timeout=30_000)
    await button.click()


async def _click_mode(modal: Any, label_pattern: str) -> None:
    button = modal.locator(".mode-tabs button").filter(has_text=re.compile(label_pattern)).first
    await expect(button).to_be_visible(timeout=30_000)
    await button.click()


async def _set_run_variables(modal: Any, variables: dict[str, Any]) -> None:
    value = json.dumps(variables, ensure_ascii=False, indent=2)
    editor = modal.locator("flows-code-editor.api-json-editor.compact").first
    await expect(editor).to_be_visible(timeout=30_000)
    await editor.evaluate(
        """
        (el, value) => {
            el.value = value;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        value,
    )


async def _run_and_wait(modal: Any) -> None:
    await flows_click_platform_button(modal, "Run", "Запустить", timeout=30_000)
    result = modal.get_by_text(re.compile(r"API_DOC_OK|Task submitted|completed|submitted")).first
    await expect(result).to_be_visible(timeout=60_000)


@pytest.mark.scenario(
    service="flows",
    tag="api",
    doc_slug="api-console",
    title="Flows: API Console и A2A запуск",
    description=(
        "Полная инструкция по модалке API Console в редакторе Flows: где взять endpoint, "
        "как читать A2A JSON-RPC body, как запускать Streaming/Sync/Async и как разбирать "
        "реальные ответы API."
    ),
    title_en="Flows: API Console and A2A run",
    description_en=(
        "Complete guide for the API Console modal in the Flows editor: where to get the endpoint, "
        "how to read the A2A JSON-RPC body, how to run Streaming/Sync/Async, and how to inspect "
        "real API responses."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.real_taskiq
@pytest.mark.timeout(240)
async def test_flows_api_console_documentation_scenario(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    taskiq_worker: object,
    unique_id: str,
) -> None:
    _ = taskiq_worker
    flow_id = flows_doc_flow_id("doc_api_console", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        _api_docs_flow_payload(flow_id),
    )

    page = ui_page_system
    modal = await _open_api_console(page, flow_id, flows_ui)

    await scenario.step(
        "Открываем API Console из редактора flow",
        page,
        label_en="Open API Console from the flow editor",
        details=INTRO_DETAILS_RU,
        details_en=INTRO_DETAILS_EN,
    )

    await scenario.step(
        "Разбираем вкладку Старт и режимы A2A",
        page,
        label_en="Read the Start tab and A2A modes",
        details=START_DETAILS_RU,
        details_en=START_DETAILS_EN,
    )

    await _click_nav(modal, r"Примеры|Examples")
    await expect(modal.locator("flows-code-editor.api-code-editor").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Берем готовые curl, Python и JS примеры",
        page,
        label_en="Use ready curl, Python, and JS examples",
        details=EXAMPLES_DETAILS_RU,
        details_en=EXAMPLES_DETAILS_EN,
    )

    await _click_nav(modal, r"Поля A2A|A2A fields")
    await expect(modal.get_by_text(re.compile(r"Runtime-переменные|Runtime variables"))).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Проверяем каждое поле A2A и правила variables",
        page,
        label_en="Check every A2A field and variables rule",
        details=FIELDS_DETAILS_RU,
        details_en=FIELDS_DETAILS_EN,
    )

    await _click_nav(modal, r"Запуск|Run")
    await _set_run_variables(
        modal,
        {
            "customer_name": "Maria",
            "branch_id": "runtime-doc-branch",
            "extra": "client-extra",
        },
    )
    await _run_and_wait(modal)
    await scenario.step(
        "Запускаем Streaming и видим настоящий ответ API",
        page,
        label_en="Run Streaming and inspect the real API response",
        details=RUN_STREAM_DETAILS_RU,
        details_en=RUN_STREAM_DETAILS_EN,
    )

    events_tab = modal.locator(".response-tabs button").filter(has_text=re.compile(r"SSE события|SSE events")).first
    await expect(events_tab).to_be_visible(timeout=30_000)
    await events_tab.click()
    await expect(modal.locator("flows-code-editor.api-json-editor.tall").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открываем инспектор ответа: JSON, SSE, headers, raw и полный result",
        page,
        label_en="Open the response inspector: JSON, SSE, headers, raw, and full result",
        details=INSPECTOR_DETAILS_RU,
        details_en=INSPECTOR_DETAILS_EN,
    )

    await _click_mode(modal, r"Sync")
    await _run_and_wait(modal)
    await scenario.step(
        "Проверяем синхронный режим message/send",
        page,
        label_en="Test synchronous message/send mode",
        details=SYNC_DETAILS_RU,
        details_en=SYNC_DETAILS_EN,
    )

    await _click_mode(modal, r"Async")
    await _run_and_wait(modal)
    polls_tab = modal.locator(".response-tabs button").filter(has_text=re.compile(r"Async опросы|Async polls")).first
    if await polls_tab.count() > 0:
        await polls_tab.click()
    await scenario.step(
        "Проверяем async submit и последующие tasks/get опросы",
        page,
        label_en="Test async submit and subsequent tasks/get polls",
        details=ASYNC_DETAILS_RU,
        details_en=ASYNC_DETAILS_EN,
    )
