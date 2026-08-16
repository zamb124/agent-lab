"""HITL матрица оператора: доступ, complete click, комментарии, panel, файлы, CRM."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import flows_open_chat_page
from tests.ui.e2e.hitl_e2e_bridge import (
    EXAMPLE_GRAPH_ID,
    GREEN_GARDEN_HITL_MESSAGE,
    GREEN_GARDEN_TAKEOVER_MESSAGE,
    hitl_api_assert_conversation_lacks_text,
    hitl_api_assert_turn_has_files,
    hitl_api_assert_turn_role,
    hitl_api_wait_conversation_text,
    hitl_assert_composer_readonly,
    hitl_assert_work_item_open,
    hitl_trigger_deterministic,
    hitl_wait_work_item_terminal,
)
from tests.ui.e2e.worktracker_e2e_helpers import (
    crm_open_work_item_page,
    flows_user_chat_wait_text,
    worktracker_add_comment,
    worktracker_api_complete_work_item_response,
    worktracker_claim_task,
    worktracker_hitl_assert_complete_hidden,
    worktracker_hitl_attach_file,
    worktracker_hitl_chat_send,
    worktracker_hitl_embedded_chat,
    worktracker_inbox_open_panel,
    worktracker_open_task_page,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_ = os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_operator_without_queue_access(
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    ui_page_system: Page,
    ui_page_system_member: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service, auth_token_system
    await flows_open_chat_page(ui_page_system, flows_ui, EXAMPLE_GRAPH_ID)
    work_item_id = await hitl_trigger_deterministic(
        ui_page_system, GREEN_GARDEN_TAKEOVER_MESSAGE
    )
    editor = await worktracker_open_task_page(
        ui_page_system_member, worktracker_ui, work_item_id
    )
    await expect(editor.locator(".wt-hitl-hint").first).to_be_visible(timeout=30_000)
    await expect(
        editor.get_by_text(re.compile(r"Нужен доступ к очереди|You need queue access"))
    ).to_be_visible()
    chat = await worktracker_hitl_embedded_chat(editor)
    await hitl_assert_composer_readonly(chat)
    await worktracker_hitl_assert_complete_hidden(editor)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_single_reply_empty_complete_rejected(
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    await flows_open_chat_page(ui_page_system, flows_ui, EXAMPLE_GRAPH_ID)
    work_item_id = await hitl_trigger_deterministic(
        ui_page_system, GREEN_GARDEN_HITL_MESSAGE
    )
    wt_page = await ui_page_system.context.new_page()
    try:
        editor = await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
        await worktracker_claim_task(wt_page, editor)
        await worktracker_hitl_assert_complete_hidden(editor)
    finally:
        await wt_page.close()
    response = await worktracker_api_complete_work_item_response(
        worktracker_ui.origin,
        auth_token_system,
        work_item_id,
        resolution_text="",
    )
    if response.status_code < 400:
        raise AssertionError(
            f"empty single_reply complete must fail, got {response.status_code} {response.text}"
        )
    await hitl_assert_work_item_open(worktracker_ui.origin, auth_token_system, work_item_id)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_activity_comment_not_in_customer_feed(
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
    unique_id: str,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    internal = f"внутренняя заметка {unique_id}"
    await flows_open_chat_page(ui_page_system, flows_ui, EXAMPLE_GRAPH_ID)
    work_item_id = await hitl_trigger_deterministic(
        ui_page_system, GREEN_GARDEN_TAKEOVER_MESSAGE
    )
    wt_page = await ui_page_system.context.new_page()
    try:
        editor = await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
        await worktracker_claim_task(wt_page, editor)
        await worktracker_add_comment(wt_page, editor, internal)
        await expect(editor.get_by_text(internal).first).to_be_visible(timeout=15_000)
    finally:
        await wt_page.close()
    await hitl_api_assert_conversation_lacks_text(
        flows_ui.origin, auth_token_system, work_item_id, internal
    )
    customer_text = await ui_page_system.locator("chat-page").inner_text()
    if internal in customer_text:
        raise AssertionError("activity comment leaked into customer chat")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_inbox_panel_takeover_send(
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
    unique_id: str,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    operator_reply = f"Марина из панели: уточню возврат ({unique_id})"
    await flows_open_chat_page(ui_page_system, flows_ui, EXAMPLE_GRAPH_ID)
    work_item_id = await hitl_trigger_deterministic(
        ui_page_system, GREEN_GARDEN_TAKEOVER_MESSAGE
    )
    wt_page = await ui_page_system.context.new_page()
    try:
        editor = await worktracker_inbox_open_panel(wt_page, worktracker_ui, work_item_id)
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
    await flows_user_chat_wait_text(ui_page_system, operator_reply)
    await hitl_assert_work_item_open(flows_ui.origin, auth_token_system, work_item_id)


@pytest.mark.scenario(
    service="worktracker",
    tag="operators",
    timeout_seconds=60,
    doc_slug="hitl-attach-file-in-chat",
    title="Оператор прикрепляет файл в ответ покупателю",
    description=(
        "**Для чего:** эта инструкция покажет, как отправить покупателю вложение "
        "из встроенного чата задачи, а не через внутренние комментарии.\n\n"
        "**Какие проблемы решает:** фото товара или бланк возврата легко положить "
        "в «Активность», и покупатель его не увидит.\n\n"
        "**Результат:** файл уходит в диалог HITL, покупатель видит вложение в своём чате."
    ),
    title_en="Operator attaches a file in the customer reply",
    description_en=(
        "**What for:** this guide shows how to send the customer an attachment from "
        "the embedded task chat, not via internal comments.\n\n"
        "**Problems it solves:** a product photo is easy to drop into Activity, and "
        "the customer never sees it.\n\n"
        "**Result:** the file goes into the HITL dialog and the customer sees the "
        "attachment in their chat."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_operator_attach_file(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
    unique_id: str,
    tmp_path: Path,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    caption = f"фото товара {unique_id}"
    png_path = tmp_path / f"hitl-{unique_id}.png"
    png_path.write_bytes(_MIN_PNG)
    await flows_open_chat_page(ui_page_system, flows_ui, EXAMPLE_GRAPH_ID)
    work_item_id = await hitl_trigger_deterministic(
        ui_page_system, GREEN_GARDEN_TAKEOVER_MESSAGE
    )
    await scenario.step(
        "Доведите чат до задачи оператора",
        ui_page_system,
        screenshot_name="file-hitl-triggered",
        label_en="Take the chat to an operator task",
        details=(
            "Покупатель пишет про спорный возврат. Появляется задача в очереди "
            "поддержки — туда оператор и отвечает."
        ),
        details_en=(
            "The customer writes about a disputed return. A support-queue task "
            "appears — that is where the operator replies."
        ),
    )
    wt_page = await ui_page_system.context.new_page()
    try:
        editor = await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
        await worktracker_claim_task(wt_page, editor)
        await scenario.step(
            "Откройте задачу и возьмите её в работу",
            wt_page,
            screenshot_name="file-task-claimed",
            label_en="Open the task and claim it",
            details=(
                "В разделе задач откройте карточку и нажмите «Взять себе». Внизу чата "
                "есть поле ввода и кнопка вложения."
            ),
            details_en=(
                "In Tasks open the card and claim it. The chat shows the input and "
                "an attach control."
            ),
        )
        await worktracker_hitl_attach_file(editor, str(png_path))
        await worktracker_hitl_chat_send(editor, caption)
        await scenario.step(
            "Прикрепите фото и отправьте ответ",
            wt_page,
            screenshot_name="file-sent",
            label_en="Attach the photo and send the reply",
            details=(
                "Выберите файл в композере чата и напишите подпись. Сообщение с "
                "вложением уходит покупателю, не в ленту активности."
            ),
            details_en=(
                "Pick a file in the chat composer and add a caption. The message with "
                "the attachment goes to the customer, not to Activity."
            ),
        )
    finally:
        await wt_page.close()
    await hitl_api_assert_turn_has_files(
        flows_ui.origin, auth_token_system, work_item_id, caption
    )
    await flows_user_chat_wait_text(ui_page_system, caption)
    await scenario.step(
        "Проверьте вложение у покупателя",
        ui_page_system,
        screenshot_name="file-in-customer-chat",
        label_en="Check the attachment in the customer chat",
        details=(
            "**Демонстрация результата.** В чате покупателя видна подпись к фото. "
            "Файл пришёл тем же диалогом, что текстовый ответ оператора.\n\n"
            "**Итог.** Вы умеете слать вложения покупателю из встроенного чата задачи."
        ),
        details_en=(
            "**Result demonstration.** The customer chat shows the photo caption. "
            "The file arrived in the same dialog as the operator text.\n\n"
            "**Summary.** You can send attachments to the customer from the embedded "
            "task chat."
        ),
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_composer_readonly_after_done(
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
    unique_id: str,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    operator_reply = f"Марина: закрываем возврат {unique_id}"
    await flows_open_chat_page(ui_page_system, flows_ui, EXAMPLE_GRAPH_ID)
    work_item_id = await hitl_trigger_deterministic(
        ui_page_system, GREEN_GARDEN_HITL_MESSAGE
    )
    wt_page = await ui_page_system.context.new_page()
    try:
        editor = await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
        await worktracker_claim_task(wt_page, editor)
        await worktracker_hitl_chat_send(editor, operator_reply)
        await hitl_wait_work_item_terminal(
            worktracker_ui.origin, auth_token_system, work_item_id
        )
        chat = await worktracker_hitl_embedded_chat(editor)
        await hitl_assert_composer_readonly(chat)
    finally:
        await wt_page.close()


@pytest.mark.scenario(
    service="crm",
    tag="tasks",
    timeout_seconds=60,
    doc_slug="hitl-open-from-crm",
    title="Открыть HITL-задачу из CRM в разделе задач",
    description=(
        "**Для чего:** эта инструкция покажет, как из карточки задачи в CRM перейти "
        "в полноценный диалог оператора в разделе задач.\n\n"
        "**Какие проблемы решает:** в CRM нет чата с покупателем — если ответить "
        "там комментарием, покупатель ничего не увидит.\n\n"
        "**Результат:** кнопка «Открыть в задачах» ведёт на карточку HITL со "
        "встроенным чатом."
    ),
    title_en="Open an HITL task from CRM in Tasks",
    description_en=(
        "**What for:** this guide shows how to leave a CRM task card and open the "
        "full operator dialog in Tasks.\n\n"
        "**Problems it solves:** CRM has no customer chat — a comment there never "
        "reaches the buyer.\n\n"
        "**Result:** Open in Tasks takes you to the HITL card with the embedded chat."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_hitl_crm_open_in_tasks(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    crm_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
    crm_service,
) -> None:
    _ = (
        hitl_demo_ready,
        flows_service,
        taskiq_worker,
        worktracker_http_service,
        crm_service,
        auth_token_system,
    )
    await flows_open_chat_page(ui_page_system, flows_ui, EXAMPLE_GRAPH_ID)
    work_item_id = await hitl_trigger_deterministic(
        ui_page_system, GREEN_GARDEN_TAKEOVER_MESSAGE
    )
    await hitl_api_wait_conversation_text(
        flows_ui.origin,
        auth_token_system,
        work_item_id,
        GREEN_GARDEN_TAKEOVER_MESSAGE,
    )
    crm_page = await ui_page_system.context.new_page()
    try:
        detail = await crm_open_work_item_page(crm_page, crm_ui, work_item_id)
        await expect(detail.locator("platform-flow-ui")).to_have_count(0)
        cta = detail.get_by_role(
            "button", name=re.compile(r"Открыть в задачах|Open in Tasks")
        )
        await expect(cta).to_be_visible(timeout=15_000)
        await scenario.step(
            "Откройте карточку HITL в CRM",
            crm_page,
            screenshot_name="crm-hitl-card",
            label_en="Open the HITL card in CRM",
            details=(
                "По прямой ссылке откройте задачу передачи оператору в CRM. Здесь "
                "нет чата с покупателем — только свойства задачи и кнопка перехода."
            ),
            details_en=(
                "Open the operator-handoff task in CRM via a direct link. There is "
                "no customer chat here — only task properties and a jump button."
            ),
        )
        await cta.click()
        await scenario.step(
            "Нажмите «Открыть в задачах»",
            crm_page,
            screenshot_name="crm-open-in-tasks-click",
            label_en="Click Open in Tasks",
            details=(
                "Кнопка ведёт в раздел задач, где живёт диалог с покупателем. "
                "В CRM композера HITL нет — отвечать нужно там."
            ),
            details_en=(
                "The button takes you to Tasks, where the customer dialog lives. "
                "CRM has no HITL composer — reply there."
            ),
        )
    finally:
        await crm_page.close()
    wt_page = await ui_page_system.context.new_page()
    try:
        editor = await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
        await worktracker_hitl_embedded_chat(editor)
        await scenario.step(
            "Проверьте чат в разделе задач",
            wt_page,
            screenshot_name="worktracker-hitl-from-crm",
            label_en="Check the chat in Tasks",
            details=(
                "Карточка в задачах показывает встроенный диалог с покупателем — "
                "это место, откуда оператор отвечает."
            ),
            details_en=(
                "The Tasks card shows the embedded customer dialog — this is where "
                "the operator replies."
            ),
        )
        await worktracker_claim_task(wt_page, editor)
        await expect(
            editor.locator("section.wt-hitl platform-flow-ui").first
        ).to_be_visible()
        await scenario.step(
            "Убедитесь, что композер только здесь",
            wt_page,
            screenshot_name="hitl-composer-in-tasks",
            label_en="Confirm the composer lives here",
            details=(
                "**Демонстрация результата.** После «Взять себе» в карточке задач "
                "появляется поле ответа покупателю. В CRM его не было.\n\n"
                "**Итог.** Из CRM вы умеете перейти в HITL-задачу и отвечать "
                "покупателю в разделе задач."
            ),
            details_en=(
                "**Result demonstration.** After claim, the Tasks card shows the "
                "customer reply field. CRM did not have it.\n\n"
                "**Summary.** From CRM you can jump to the HITL task and reply to "
                "the customer in Tasks."
            ),
        )
    finally:
        await wt_page.close()
