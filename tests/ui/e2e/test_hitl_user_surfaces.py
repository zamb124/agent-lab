"""HITL на поверхностях покупателя: SPA takeover, embed, Test Run."""

from __future__ import annotations

import os

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_chat_send_message,
    flows_execution_send_message,
    flows_open_chat_page,
    flows_open_editor,
    flows_open_execution_panel,
)
from tests.ui.e2e.hitl_e2e_bridge import (
    EXAMPLE_GRAPH_ID,
    GREEN_GARDEN_HITL_MESSAGE,
    GREEN_GARDEN_TAKEOVER_MESSAGE,
    hitl_api_assert_turn_role,
    hitl_assert_composer_editable,
    hitl_assert_composer_readonly,
    hitl_assert_work_item_open,
    hitl_create_chat_hitl_flow,
    hitl_embed_opened,
    hitl_host_send,
    hitl_trigger_deterministic,
    hitl_user_flow_ui,
    hitl_wait_host_input_required,
)
from tests.ui.e2e.worktracker_e2e_helpers import (
    flows_user_chat_wait_text,
    worktracker_api_get_work_item,
    worktracker_claim_task,
    worktracker_hitl_chat_send,
    worktracker_open_task_page,
)
from tests.ui.e2e_worker import ui_e2e_company_id
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_ = os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="operators",
    timeout_seconds=60,
    doc_slug="hitl-customer-writes-during-takeover",
    title="Покупатель пишет, пока оператор ведёт диалог",
    description=(
        "**Для чего:** эта инструкция покажет, что в режиме перехвата диалога "
        "покупатель может продолжать писать в чат агента, не дожидаясь закрытия задачи.\n\n"
        "**Какие проблемы решает:** спорный возврат требует уточнений с обеих сторон — "
        "если поле ввода у покупателя блокируется, оператор не получает номер заказа "
        "и фото вовремя.\n\n"
        "**Результат:** после передачи оператору покупатель отправляет сообщение, "
        "оно появляется в ленте, задача остаётся открытой."
    ),
    title_en="Customer writes during dialog takeover",
    description_en=(
        "**What for:** this guide shows that in dialog takeover the customer can keep "
        "writing in the agent chat without waiting for the task to close.\n\n"
        "**Problems it solves:** a disputed return needs details from both sides — if "
        "the customer input is locked, the operator never gets the order number in time.\n\n"
        "**Result:** after handoff the customer sends a message, it appears in the "
        "thread, and the task stays open."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_user_takeover_append(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
    unique_id: str,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    followup = f"номер заказа {unique_id}"
    page = ui_page_system
    await flows_open_chat_page(page, flows_ui, EXAMPLE_GRAPH_ID)
    await scenario.step(
        "Откройте чат агента",
        page,
        screenshot_name="customer-chat-open",
        label_en="Open the agent chat",
        details=(
            "В Flows откройте чат демо-агента. Это тот же экран, с которого покупатель "
            "пишет в магазин."
        ),
        details_en=(
            "In Flows open the demo agent chat. This is the same screen the customer "
            "uses to write to the store."
        ),
    )
    work_item_id = await hitl_trigger_deterministic(page, GREEN_GARDEN_TAKEOVER_MESSAGE)
    host = hitl_user_flow_ui(page, surface="spa")
    await hitl_assert_composer_editable(host)
    await scenario.step(
        "Доведите диалог до перехвата",
        page,
        screenshot_name="takeover-banner",
        label_en="Take the dialog to takeover",
        details=(
            "Напишите про спорный возврат с перехватом. Появится плашка ожидания "
            "оператора, но поле ввода останется доступным — это режим перехвата, "
            "а не одного ответа."
        ),
        details_en=(
            "Write about a disputed return that needs takeover. A waiting banner "
            "appears, but the input stays enabled — this is takeover, not single-reply."
        ),
    )
    await flows_chat_send_message(page, followup)
    await hitl_api_assert_turn_role(
        flows_ui.origin,
        auth_token_system,
        work_item_id,
        followup,
        "user",
    )
    await hitl_assert_work_item_open(flows_ui.origin, auth_token_system, work_item_id)
    await scenario.step(
        "Напишите уточнение, пока задача открыта",
        page,
        screenshot_name="customer-followup-sent",
        label_en="Send a follow-up while the task is open",
        details=(
            "Введите номер заказа и отправьте. Сообщение сразу видно в ленте чата."
        ),
        details_en=(
            "Type the order number and send. The message appears in the chat thread."
        ),
    )
    await flows_user_chat_wait_text(page, followup)
    await scenario.step(
        "Проверьте, что задача не закрылась",
        page,
        screenshot_name="takeover-still-open",
        label_en="Confirm the task is still open",
        details=(
            "**Демонстрация результата.** Плашка ожидания на месте, задача оператора "
            "ещё открыта: покупатель дополнил диалог, не завершив передачу.\n\n"
            "**Итог.** В режиме перехвата вы умеете писать из чата покупателя, пока "
            "оператор разбирает обращение."
        ),
        details_en=(
            "**Result demonstration.** The waiting banner is still there and the "
            "operator task is still open: the customer added to the dialog without "
            "closing the handoff.\n\n"
            "**Summary.** In takeover you can write from the customer chat while the "
            "operator handles the case."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="operators",
    timeout_seconds=60,
    doc_slug="hitl-embed-waiting-banner",
    title="Ожидание оператора в виджете на сайте",
    description=(
        "**Для чего:** эта инструкция покажет, как покупатель на сайте магазина видит "
        "ожидание оператора в том же виджете, что и обычный чат агента.\n\n"
        "**Какие проблемы решает:** спорный возврат с внешнего сайта не должен "
        "выглядеть как «чат сломался» — нужна понятная плашка и заблокированный ввод "
        "в режиме одного ответа.\n\n"
        "**Результат:** в embed-виджете видна плашка ожидания, поле ввода только "
        "для чтения."
    ),
    title_en="Operator wait in the on-site widget",
    description_en=(
        "**What for:** this guide shows how a customer on the store site sees operator "
        "wait in the same widget as regular agent chat.\n\n"
        "**Problems it solves:** a disputed return from an external site must not look "
        "like a broken chat — they need a clear banner and a locked input in "
        "single-reply mode.\n\n"
        "**Result:** the embed widget shows the waiting banner and a read-only composer."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_embed_single_reply_wait(
    scenario: ScenarioRecorder,
    page: Page,
    embed_browser_http_stack_ready,
    frontend_ui: AppUI,
    flows_ui: AppUI,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    hitl_demo_ready: str,
    taskiq_worker,
    unique_id: str,
) -> None:
    _ = embed_browser_http_stack_ready, hitl_demo_ready, taskiq_worker
    company_id = ui_e2e_company_id()
    flow_id = f"hitl_embed_sr_{unique_id}"
    await hitl_create_chat_hitl_flow(
        flows_ui.origin,
        auth_token_system,
        flow_id=flow_id,
        mode="single_reply",
        title=f"HITL embed {unique_id}",
    )
    async with hitl_embed_opened(
        page,
        frontend_ui=frontend_ui,
        flows_ui=flows_ui,
        auth_headers=auth_headers_system,
        company_id=company_id,
        unique_id=unique_id,
        flow_id=flow_id,
    ) as host:
        await scenario.step(
            "Откройте виджет чата на сайте",
            page,
            screenshot_name="embed-widget-open",
            label_en="Open the chat widget on the site",
            details=(
                "На внешней странице магазина нажмите кнопку виджета. Откроется тот же "
                "чат агента, что в Flows, только встроенный в сайт."
            ),
            details_en=(
                "On the store page click the widget button. The same agent chat as in "
                "Flows opens, embedded on the site."
            ),
        )
        await hitl_host_send(host, GREEN_GARDEN_HITL_MESSAGE)
        await hitl_wait_host_input_required(host)
        await scenario.step(
            "Опишите спорный возврат",
            page,
            screenshot_name="embed-hitl-sent",
            label_en="Describe the disputed return",
            details=(
                "Напишите, что нужен оператор по возврату без чека. Агент передаёт "
                "обращение в очередь поддержки."
            ),
            details_en=(
                "Write that you need an operator for a return without a receipt. The "
                "agent routes the case to the support queue."
            ),
        )
        await expect(host.locator(".input-required-banner").first).to_be_visible()
        await scenario.step(
            "Дождитесь плашки ожидания",
            page,
            screenshot_name="embed-waiting-banner",
            label_en="Wait for the waiting banner",
            details=(
                "В виджете появляется плашка, что запрос у оператора. Это тот же сигнал, "
                "что в чате Flows."
            ),
            details_en=(
                "The widget shows a banner that an operator has the request. This is "
                "the same signal as in the Flows chat."
            ),
        )
        await hitl_assert_composer_readonly(host)
        await scenario.step(
            "Проверьте, что поле ввода недоступно",
            page,
            screenshot_name="embed-composer-readonly",
            label_en="Confirm the input is read-only",
            details=(
                "**Демонстрация результата.** В режиме одного ответа покупатель не "
                "может отправить ещё одно сообщение из виджета — диалог ждёт оператора.\n\n"
                "**Итог.** На сайте магазина HITL выглядит так же, как в кабинете: "
                "плашка ожидания и заблокированный ввод."
            ),
            details_en=(
                "**Result demonstration.** In single-reply the customer cannot send "
                "another message from the widget — the dialog waits for the operator.\n\n"
                "**Summary.** On the store site HITL looks the same as in the product: "
                "a waiting banner and a locked composer."
            ),
        )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_embed_takeover_user_and_operator(
    page: Page,
    ui_page_system: Page,
    embed_browser_http_stack_ready,
    frontend_ui: AppUI,
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    hitl_demo_ready: str,
    taskiq_worker,
    worktracker_http_service,
    unique_id: str,
) -> None:
    _ = (
        embed_browser_http_stack_ready,
        hitl_demo_ready,
        taskiq_worker,
        worktracker_http_service,
    )
    followup = f"заказ {unique_id}"
    operator_reply = f"Марина из поддержки: приняла заказ {unique_id}"
    company_id = ui_e2e_company_id()
    flow_id = f"hitl_embed_to_{unique_id}"
    await hitl_create_chat_hitl_flow(
        flows_ui.origin,
        auth_token_system,
        flow_id=flow_id,
        mode="takeover",
        title=f"HITL embed takeover {unique_id}",
    )
    async with hitl_embed_opened(
        page,
        frontend_ui=frontend_ui,
        flows_ui=flows_ui,
        auth_headers=auth_headers_system,
        company_id=company_id,
        unique_id=unique_id,
        flow_id=flow_id,
    ) as host:
        await hitl_host_send(host, GREEN_GARDEN_TAKEOVER_MESSAGE)
        work_item_id = await hitl_wait_host_input_required(host)
        await hitl_assert_composer_editable(host)
        await hitl_host_send(host, followup)
        await hitl_api_assert_turn_role(
            flows_ui.origin,
            auth_token_system,
            work_item_id,
            followup,
            "user",
        )
        wt_page = await ui_page_system.context.new_page()
        try:
            editor = await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
            await worktracker_claim_task(wt_page, editor)
            await worktracker_hitl_chat_send(editor, operator_reply)
            await hitl_api_assert_turn_role(
                flows_ui.origin,
                auth_token_system,
                work_item_id,
                operator_reply,
                "operator",
            )
        finally:
            await wt_page.close()
        await expect(host.get_by_text(operator_reply).first).to_be_visible(timeout=120_000)
        await hitl_assert_work_item_open(flows_ui.origin, auth_token_system, work_item_id)


@pytest.mark.scenario(
    service="flows",
    tag="operators",
    timeout_seconds=60,
    doc_slug="hitl-test-run-waiting",
    title="Ожидание оператора в тестовом запуске",
    description=(
        "**Для чего:** эта инструкция покажет, как проверить передачу оператору прямо "
        "в редакторе агента, не выходя на публичный чат.\n\n"
        "**Какие проблемы решает:** легко отладить HITL на канве и не понять, что "
        "покупатель уже ждёт — Test Run должен показать ту же плашку и тот же "
        "заблокированный ввод.\n\n"
        "**Результат:** в панели запуска видна плашка ожидания, поле ввода только "
        "для чтения."
    ),
    title_en="Operator wait in Test Run",
    description_en=(
        "**What for:** this guide shows how to verify operator handoff inside the "
        "agent editor without opening the public chat.\n\n"
        "**Problems it solves:** it is easy to debug HITL on the canvas and miss that "
        "the customer is already waiting — Test Run must show the same banner and "
        "locked input.\n\n"
        "**Result:** the run panel shows the waiting banner and a read-only composer."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_test_run_single_reply_wait(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    page = ui_page_system
    await flows_open_editor(page, flows_ui, EXAMPLE_GRAPH_ID)
    await scenario.step(
        "Откройте редактор агента",
        page,
        screenshot_name="editor-open",
        label_en="Open the agent editor",
        details=(
            "В списке агентов откройте демо-агента «Зелёный сад». На канве виден граф "
            "с передачей оператору."
        ),
        details_en=(
            "From the agent list open the Green Garden demo agent. The canvas shows "
            "the graph with operator handoff."
        ),
    )
    await flows_open_execution_panel(page)
    await scenario.step(
        "Переключитесь в тестовый запуск",
        page,
        screenshot_name="test-run-open",
        label_en="Switch to Test Run",
        details=(
            "В шапке редактора выберите режим запуска. Справа открывается панель "
            "с тем же чатом, что у покупателя."
        ),
        details_en=(
            "In the editor header choose Run. The right-hand panel opens with the "
            "same chat the customer sees."
        ),
    )
    await flows_execution_send_message(page, GREEN_GARDEN_HITL_MESSAGE)
    host = hitl_user_flow_ui(page, surface="run")
    await hitl_wait_host_input_required(host)
    await scenario.step(
        "Отправьте спорный возврат из панели",
        page,
        screenshot_name="test-run-hitl-sent",
        label_en="Send the disputed return from the panel",
        details=(
            "В панели запуска напишите про возврат без чека. Агент ставит диалог "
            "на паузу до ответа оператора."
        ),
        details_en=(
            "In the run panel write about a return without a receipt. The agent "
            "pauses the dialog until an operator replies."
        ),
    )
    await hitl_assert_composer_readonly(host)
    await scenario.step(
        "Проверьте плашку и заблокированный ввод",
        page,
        screenshot_name="test-run-readonly",
        label_en="Check the banner and locked input",
        details=(
            "**Демонстрация результата.** Внутри панели запуска — та же плашка "
            "ожидания и поле только для чтения, что у покупателя в чате.\n\n"
            "**Итог.** HITL можно проверить в Test Run, не открывая отдельную "
            "вкладку чата."
        ),
        details_en=(
            "**Result demonstration.** Inside the run panel you see the same waiting "
            "banner and read-only field as the customer chat.\n\n"
            "**Summary.** You can verify HITL in Test Run without opening a separate "
            "chat tab."
        ),
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_test_run_takeover_user_send(
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
    unique_id: str,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    followup = f"run-{unique_id}"
    page = ui_page_system
    await flows_open_editor(page, flows_ui, EXAMPLE_GRAPH_ID)
    await flows_execution_send_message(page, GREEN_GARDEN_TAKEOVER_MESSAGE)
    host = hitl_user_flow_ui(page, surface="run")
    work_item_id = await hitl_wait_host_input_required(host)
    await hitl_assert_composer_editable(host)
    await hitl_host_send(host, followup)
    await hitl_api_assert_turn_role(
        flows_ui.origin,
        auth_token_system,
        work_item_id,
        followup,
        "user",
    )
    item = await worktracker_api_get_work_item(
        flows_ui.origin, auth_token_system, work_item_id
    )
    if str(item.get("state") or "") in {"done", "cancelled", "failed"}:
        raise AssertionError("takeover Test Run must keep the work item open")
