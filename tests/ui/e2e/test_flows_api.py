"""UI E2E сценарии Flows: API Console и гостевой доступ."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_api_doc_constants import (
    ASYNC_DETAILS_EN,
    ASYNC_DETAILS_RU,
    START_DETAILS_EN,
    START_DETAILS_RU,
    SYNC_DETAILS_EN,
    SYNC_DETAILS_RU,
)
from tests.ui.e2e.flows_api_e2e_helpers import (
    flows_api_console_click_mode,
    flows_api_console_click_nav,
    flows_api_console_docs_payload,
    flows_api_console_run_and_wait,
    flows_api_console_set_run_variables,
    flows_open_api_console_modal,
    flows_seed_company_secret_var,
)
from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_flow,
    flows_click_platform_button,
    flows_doc_flow_id,
    flows_llm_payload,
    flows_open_editor,
    flows_open_preview_share_modal,
    flows_publish_editor,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="api",
    doc_slug="api-first-request",
    title="Первый запрос к агенту через API Console",
    description=(
        "**Для чего:** эта инструкция поможет отправить первый рабочий запрос к агенту "
        "из редактора Flows и увидеть реальный ответ API.\n\n"
        "**Какие проблемы решает:** разработчику непонятно, куда слать запрос, какой JSON "
        "нужен и как проверить ответ без отдельного клиента.\n\n"
        "**Результат:** вы отправите потоковый запрос из API Console и увидите ответ агента."
    ),
    title_en="First agent request through API Console",
    description_en=(
        "**What for:** this guide helps you send the first working request to an agent "
        "from the Flows editor and see a real API response.\n\n"
        "**Problems it solves:** developers are unsure where to send the request, which JSON "
        "body is required, and how to verify the response without a separate client.\n\n"
        "**Result:** you will send a streaming request from API Console and see the agent reply."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.real_taskiq
@pytest.mark.timeout(240)
async def test_flows_api_first_request(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    auth_headers_system: dict[str, str],
    secrets_service,
    taskiq_worker,
    unique_id: str,
) -> None:
    _ = secrets_service, taskiq_worker
    flow_id = flows_doc_flow_id("api_first", unique_id)
    await flows_seed_company_secret_var(
        auth_headers_system,
        "external_api_token",
        "e2e-api-console-token",
    )
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_api_console_docs_payload(flow_id),
    )

    page = ui_page_system
    modal = await flows_open_api_console_modal(page, flows_ui, flow_id)
    await scenario.step(
        "Откройте API Console в редакторе",
        page,
        screenshot_name="api-console-opened",
        label_en="Open API Console in the editor",
        details=(
            "В меню редактора выберите «API и A2A». Откроется модальное окно с адресом "
            "агента, вкладками подсказок и рабочей зоной запуска — это главная точка "
            "интеграции без отдельного Postman."
        ),
        details_en=(
            "In the editor menu, choose API and A2A. A modal opens with the agent endpoint, "
            "guide tabs, and a run workbench — the main integration entry point without a "
            "separate Postman collection."
        ),
    )

    await expect(modal.get_by_text(re.compile(r"flow_id|branch_id", re.I)).first).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Изучите вкладку «Старт»",
        page,
        screenshot_name="api-start-tab",
        label_en="Review the Start tab",
        details=START_DETAILS_RU,
        details_en=START_DETAILS_EN,
    )

    await flows_api_console_click_nav(modal, r"Запуск|Run")
    await expect(modal.get_by_text(re.compile(r"Запуск|Run", re.I)).first).to_be_visible(
        timeout=15_000
    )
    await scenario.step(
        "Перейдите на вкладку «Запуск»",
        page,
        screenshot_name="api-run-tab-opened",
        label_en="Switch to the Run tab",
        details=(
            "Откройте вкладку «Запуск». Здесь задаются текст сообщения, переменные и режим "
            "вызова перед отправкой запроса к агенту."
        ),
        details_en=(
            "Open the Run tab. Here you set the message text, variables, and call mode "
            "before sending a request to the agent."
        ),
    )

    await flows_api_console_set_run_variables(
        modal,
        {
            "customer_name": "Maria",
            "branch_id": "runtime-doc-branch",
            "extra": "client-extra",
        },
    )
    await flows_api_console_run_and_wait(modal)
    await expect(modal.get_by_text(re.compile(r"API_DOC_OK"))).to_be_visible(timeout=120_000)
    await scenario.step(
        "Запустите потоковый запрос и проверьте ответ",
        page,
        screenshot_name="api-streaming-result",
        label_en="Run a streaming request and check the reply",
        details=(
            "**Демонстрация результата.** На вкладке «Запуск» отправьте сообщение и дождитесь "
            "ответа с текстом проверки — это подтверждает, что API Console отправила реальный "
            "запрос к агенту.\n\n"
            "**Итог.** Теперь вы знаете, где открыть API Console, что смотреть на вкладке "
            "«Старт» и как выполнить первый потоковый запрос."
        ),
        details_en=(
            "**Result demonstration.** On the Run tab, send a message and wait for a reply "
            "with the verification text — this confirms API Console sent a real request to "
            "the agent.\n\n"
            "**Summary.** You now know where to open API Console, what to read on the Start "
            "tab, and how to run your first streaming request."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="api",
    doc_slug="api-sync-async",
    title="Синхронный и асинхронный вызов через API Console",
    description=(
        "**Для чего:** эта инструкция покажет, как вызывать агента одним HTTP-ответом "
        "или в фоновом режиме.\n\n"
        "**Какие проблемы решает:** неочевидно, когда нужен Sync вместо Streaming и как "
        "дождаться результата длинной задачи.\n\n"
        "**Результат:** вы проверите оба режима SendMessage в одной модалке API Console."
    ),
    title_en="Sync and async calls through API Console",
    description_en=(
        "**What for:** this guide shows how to call an agent with one HTTP response or in "
        "the background.\n\n"
        "**Problems it solves:** it is unclear when Sync is better than Streaming and how to "
        "wait for a long-running task result.\n\n"
        "**Result:** you will verify both SendMessage modes in the same API Console modal."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.real_taskiq
@pytest.mark.timeout(240)
async def test_flows_api_sync_async(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    auth_headers_system: dict[str, str],
    secrets_service,
    taskiq_worker,
    unique_id: str,
) -> None:
    _ = secrets_service, taskiq_worker
    flow_id = flows_doc_flow_id("api_modes", unique_id)
    await flows_seed_company_secret_var(
        auth_headers_system,
        "external_api_token",
        "e2e-api-console-token",
    )
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_api_console_docs_payload(flow_id),
    )

    page = ui_page_system
    modal = await flows_open_api_console_modal(page, flows_ui, flow_id)
    await flows_api_console_click_nav(modal, r"Запуск|Run")
    await scenario.step(
        "Откройте вкладку «Запуск»",
        page,
        screenshot_name="api-run-tab",
        label_en="Open the Run tab",
        details=(
            "Перейдите на вкладку «Запуск». Здесь можно менять режим, текст сообщения и "
            "переменные, а затем отправлять настоящий запрос к текущему агенту."
        ),
        details_en=(
            "Switch to the Run tab. Here you can change mode, message text, and variables, "
            "then send a real request to the current agent."
        ),
    )

    await flows_api_console_click_mode(modal, r"Sync")
    await flows_api_console_set_run_variables(
        modal,
        {"customer_name": "Anna", "extra": "sync-mode"},
    )
    await flows_api_console_run_and_wait(modal)
    await expect(modal.get_by_text(re.compile(r"API_DOC_OK|completed|заверш", re.I)).first).to_be_visible(
        timeout=120_000
    )
    await scenario.step(
        "Проверьте синхронный режим",
        page,
        screenshot_name="api-sync-result",
        label_en="Test sync mode",
        details=SYNC_DETAILS_RU,
        details_en=SYNC_DETAILS_EN,
    )

    await expect(modal).to_be_visible(timeout=15_000)
    await flows_api_console_click_mode(modal, r"Async")
    await expect(modal.get_by_text(re.compile(r"Async|Асинх", re.I)).first).to_be_visible(
        timeout=15_000
    )
    await scenario.step(
        "Переключитесь на асинхронный режим",
        page,
        screenshot_name="api-async-mode-selected",
        label_en="Switch to async mode",
        details=(
            "Выберите режим Async. В этом режиме API сразу возвращает задачу, а итоговый "
            "ответ можно получить отдельным опросом статуса."
        ),
        details_en=(
            "Choose Async mode. The API returns a task immediately and you fetch the final "
            "reply with a separate status poll."
        ),
    )
    if not await modal.is_visible():
        modal = await flows_open_api_console_modal(page, flows_ui, flow_id)
        await flows_api_console_click_nav(modal, r"Запуск|Run")
        await flows_api_console_click_mode(modal, r"Async")
    await flows_api_console_run_and_wait(modal)
    polls_tab = modal.locator(".response-tabs button").filter(
        has_text=re.compile(r"Async опросы|Async polls")
    ).first
    if await polls_tab.count() > 0:
        await polls_tab.click()
    await scenario.step(
        "Проверьте асинхронный режим",
        page,
        screenshot_name="api-async-result",
        label_en="Test async mode",
        details=(
            f"{ASYNC_DETAILS_RU}\n\n"
            "**Демонстрация результата.** В режиме Async виден быстрый ответ с задачей и "
            "итоговый результат после опроса статуса — значит, оба способа вызова работают.\n\n"
            "**Итог.** Теперь вы умеете переключать Sync и Async в API Console и понимаете, "
            "когда использовать каждый режим."
        ),
        details_en=(
            f"{ASYNC_DETAILS_EN}\n\n"
            "**Result demonstration.** In Async mode you see a quick task response and the "
            "final result after status polling — both call styles work.\n\n"
            "**Summary.** You can now switch Sync and Async in API Console and understand "
            "when to use each mode."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="api",
    doc_slug="share-demo-link",
    title="Делимся демо агента по ссылке",
    description=(
        "**Для чего:** эта инструкция поможет показать агента коллеге или заказчику без "
        "доступа в аккаунт.\n\n"
        "**Какие проблемы решает:** непонятно, как быстро выдать гостевой доступ к чату "
        "и ограничить число сообщений.\n\n"
        "**Результат:** создана гостевая ссылка на демо-чат текущего агента."
    ),
    title_en="Share an agent demo link",
    description_en=(
        "**What for:** this guide helps you show an agent to a colleague or stakeholder "
        "without account access.\n\n"
        "**Problems it solves:** it is unclear how to quickly grant guest chat access and "
        "limit the number of messages.\n\n"
        "**Result:** a guest link to the current agent demo chat is created."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_share_demo_link(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("share_demo", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(flow_id, name="Demo share agent", prompt="Отвечай кратко."),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_publish_editor(page)
    await scenario.step(
        "Откройте редактора опубликованного агента",
        page,
        screenshot_name="editor-before-share",
        label_en="Open the published agent editor",
        details=(
            "Сначала опубликуйте агента, чтобы гостевая ссылка вела на актуальную версию "
            "графа и настроек."
        ),
        details_en=(
            "Publish the agent first so the guest link points to the current graph and "
            "settings."
        ),
    )

    modal = await flows_open_preview_share_modal(page)
    await scenario.step(
        "Откройте гостевой просмотр",
        page,
        screenshot_name="share-modal-opened",
        label_en="Open guest preview",
        details=(
            "В меню редактора выберите «Гостевой просмотр». Здесь задаётся лимит сообщений "
            "гостя и создаётся одноразовая ссылка на чат."
        ),
        details_en=(
            "In the editor menu, choose Guest preview. Here you set a guest message limit "
            "and create a one-time chat link."
        ),
    )

    guest_limit = modal.locator("platform-field").first
    await guest_limit.evaluate(
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
        5,
    )
    await scenario.step(
        "Задайте лимит сообщений для гостя",
        page,
        screenshot_name="share-guest-limit-set",
        label_en="Set the guest message limit",
        details=(
            "Укажите, сколько сообщений может отправить гость по ссылке — например 5. "
            "Так вы ограничиваете демо-чат без выдачи полного доступа к аккаунту."
        ),
        details_en=(
            "Set how many messages a guest may send via the link — for example 5. "
            "This limits the demo chat without granting full account access."
        ),
    )

    await flows_click_platform_button(modal, "Create link", "Создать ссылку")
    share_url = modal.get_by_text(re.compile(r"https?://")).first
    await expect(share_url).to_be_visible(timeout=60_000)
    await scenario.step(
        "Создайте и скопируйте гостевую ссылку",
        page,
        screenshot_name="share-link-created",
        label_en="Create and copy the guest link",
        details=(
            "**Демонстрация результата.** После создания на экране появляется готовая ссылка "
            "— её можно отправить гостю для проверки агента.\n\n"
            "**Итог.** Теперь вы умеете выпускать гостевую демо-ссылку с лимитом сообщений "
            "прямо из редактора."
        ),
        details_en=(
            "**Result demonstration.** After creation, a ready link appears on screen — "
            "you can send it to a guest to try the agent.\n\n"
            "**Summary.** You can now issue a guest demo link with a message limit directly "
            "from the editor."
        ),
    )
