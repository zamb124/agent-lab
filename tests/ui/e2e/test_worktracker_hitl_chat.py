"""UI E2E: встроенный `<platform-flow-ui>` в карточке WorkItem(operator_handoff).

Оператор видит тот же диалог сессии, что и покупатель, отвечает тем же композером,
что в Flows/Embed; покупатель получает ответ в своём чате в реальном времени.
"""

from __future__ import annotations

import os

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import flows_open_chat_page
from tests.ui.e2e.hitl_e2e_bridge import (
    EXAMPLE_GRAPH_ID,
    GREEN_GARDEN_HITL_MESSAGE,
    GREEN_GARDEN_TAKEOVER_MESSAGE,
    hitl_api_assert_turn_role,
    hitl_api_wait_conversation_text,
    hitl_trigger_deterministic,
)
from tests.ui.e2e.worktracker_e2e_helpers import (
    flows_user_chat_wait_text,
    worktracker_claim_task,
    worktracker_hitl_assert_chat_height,
    worktracker_hitl_chat_send,
    worktracker_hitl_chat_wait_text,
    worktracker_hitl_embedded_chat,
    worktracker_hitl_single_reply_complete,
    worktracker_open_task_page,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_ = os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="worktracker",
    tag="operators",
    timeout_seconds=60,
    doc_slug="hitl-embedded-operator-chat",
    title="Встроенный чат оператора в задаче HITL",
    description=(
        "**Для чего:** эта инструкция покажет, как оператор в разделе задач видит "
        "тот же диалог с покупателем, что и в чате агента, и отвечает из карточки "
        "задачи — тем же интерфейсом чата, что в Flows.\n\n"
        "**Какие проблемы решает:** без встроенного чата оператору приходится "
        "переключаться между сервисами и не видит полную переписку покупателя "
        "с агентом в одном месте.\n\n"
        "**Результат:** оператор читает историю, отправляет ответ из карточки "
        "задачи, а покупатель сразу видит сообщение в своём чате."
    ),
    title_en="Embedded operator chat in an HITL task",
    description_en=(
        "**What for:** this guide shows how an operator in Tasks sees the same "
        "customer dialog as in the agent chat and replies from the task card "
        "using the same chat UI as in Flows.\n\n"
        "**Problems it solves:** without an embedded chat, operators switch between "
        "services and cannot see the full customer–agent conversation in one place.\n\n"
        "**Result:** the operator reads history, sends a reply from the task card, "
        "and the customer immediately sees the message in their chat."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_worktracker_hitl_embedded_operator_chat(
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
) -> None:
    _ = auth_token_system, hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    operator_reply = f"Марина из поддержки: уточню детали возврата ({unique_id})"

    user_page = ui_page_system
    await flows_open_chat_page(user_page, flows_ui, EXAMPLE_GRAPH_ID)
    work_item_id = await hitl_trigger_deterministic(user_page, GREEN_GARDEN_TAKEOVER_MESSAGE)
    await hitl_api_wait_conversation_text(
        flows_ui.origin,
        auth_token_system,
        work_item_id,
        GREEN_GARDEN_TAKEOVER_MESSAGE,
    )

    wt_page = await user_page.context.new_page()
    try:
        editor = await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
        await worktracker_hitl_embedded_chat(editor)
        await worktracker_hitl_assert_chat_height(editor)
        await worktracker_hitl_chat_wait_text(editor, GREEN_GARDEN_TAKEOVER_MESSAGE)
        await scenario.step(
            "Откройте задачу оператора с встроенным чатом",
            wt_page,
            screenshot_name="embedded-chat-opened",
            label_en="Open the operator task with embedded chat",
            details=(
                "В разделе задач откройте карточку передачи оператору. В центре — "
                "блок «Диалог с пользователем»: тот же чат, что у покупателя в Flows, "
                "с историей переписки до передачи человеку."
            ),
            details_en=(
                "In Tasks, open the operator handoff card. The center shows "
                "Conversation with user: the same chat the customer has in Flows, "
                "including history before the handoff."
            ),
        )

        await worktracker_claim_task(wt_page, editor)
        chat = await worktracker_hitl_embedded_chat(editor)
        await expect(
            chat.locator('textarea[data-canon="composer"]').first
        ).to_be_visible(timeout=30_000)
        await scenario.step(
            "Возьмите задачу и проверьте композер",
            wt_page,
            screenshot_name="embedded-chat-composer",
            label_en="Claim the task and check the composer",
            details=(
                "Нажмите «Взять себе» в карточке. Внизу чата появляется поле ввода "
                "и кнопка отправки — тот же композер, что в чате Flows и на сайте "
                "с виджетом. Так оператор пишет покупателю напрямую."
            ),
            details_en=(
                "Click claim on the task card. The chat shows the input field and send "
                "button — the same composer as in Flows and embed chat. The operator "
                "messages the customer directly."
            ),
        )

        await worktracker_hitl_chat_send(editor, operator_reply)
        await hitl_api_assert_turn_role(
            flows_ui.origin,
            auth_token_system,
            work_item_id,
            operator_reply,
            "operator",
        )
        await scenario.step(
            "Отправьте ответ покупателю",
            wt_page,
            screenshot_name="operator-reply-sent",
            label_en="Send a reply to the customer",
            details=(
                "Введите текст и нажмите отправку. Сообщение появляется в ленте чата "
                "карточки задачи как ответ оператора — без отдельного окна и без "
                "копирования из другого сервиса."
            ),
            details_en=(
                "Type your message and send. It appears in the task chat as an operator "
                "reply — no separate window and no copying from another service."
            ),
        )
    finally:
        await wt_page.close()

    await flows_user_chat_wait_text(user_page, operator_reply)
    await scenario.step(
        "Проверьте ответ в чате покупателя",
        user_page,
        screenshot_name="customer-sees-operator-reply",
        label_en="Verify the reply in the customer chat",
        details=(
            "**Демонстрация результата.** Вернитесь к чату покупателя с агентом: "
            "там уже виден ваш ответ оператора. Покупатель получает сообщение сразу, "
            "не дожидаясь закрытия задачи.\n\n"
            "**Итог.** Теперь вы умеете работать с HITL-задачей во встроенном чате: "
            "читать полную историю, отвечать тем же композером, что в Flows, и "
            "видеть результат у покупателя в реальном времени."
        ),
        details_en=(
            "**Result demonstration.** Return to the customer agent chat: your operator "
            "reply is already visible. The customer receives the message immediately, "
            "without waiting for the task to close.\n\n"
            "**Summary.** You can now use the embedded chat on an HITL task: read full "
            "history, reply with the same composer as in Flows, and see the result in "
            "the customer chat in real time."
        ),
    )


@pytest.mark.scenario(
    service="worktracker",
    tag="operators",
    timeout_seconds=60,
    doc_slug="hitl-single-reply-complete",
    title="Один ответ оператора и завершение HITL",
    description=(
        "**Для чего:** эта инструкция покажет режим одного ответа: оператор пишет "
        "покупателю через «Ответить и завершить», а не через комментарии в активности.\n\n"
        "**Какие проблемы решает:** легко перепутать внутренние заметки команды с "
        "ответом покупателю — тогда сообщение не появится в чате агента.\n\n"
        "**Результат:** после «Ответить и завершить» покупатель видит ответ в своём "
        "чате, задача закрывается."
    ),
    title_en="Single operator reply and HITL complete",
    description_en=(
        "**What for:** this guide shows single-reply mode: the operator answers the "
        "customer via Reply and complete, not via Activity comments.\n\n"
        "**Problems it solves:** internal team notes are easy to confuse with a "
        "customer reply — then the message never appears in the agent chat.\n\n"
        "**Result:** after Reply and complete the customer sees the answer in their "
        "chat and the task closes."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_worktracker_hitl_single_reply_complete(
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
) -> None:
    _ = auth_token_system, hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    operator_reply = f"Марина из поддержки: оформим возврат по фото ({unique_id})"

    user_page = ui_page_system
    await flows_open_chat_page(user_page, flows_ui, EXAMPLE_GRAPH_ID)
    work_item_id = await hitl_trigger_deterministic(user_page, GREEN_GARDEN_HITL_MESSAGE)
    user_composer = user_page.locator("flows-chat-page textarea[data-canon='composer']").first
    await expect(user_composer).to_have_attribute("readonly", "", timeout=20_000)
    await hitl_api_wait_conversation_text(
        flows_ui.origin,
        auth_token_system,
        work_item_id,
        GREEN_GARDEN_HITL_MESSAGE,
    )

    wt_page = await user_page.context.new_page()
    try:
        editor = await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
        await worktracker_hitl_embedded_chat(editor)
        await expect(editor.locator(".wt-hitl-hint").first).to_be_visible(timeout=30_000)
        await scenario.step(
            "Откройте задачу с подсказкой single_reply",
            wt_page,
            screenshot_name="single-reply-hint",
            label_en="Open the task with the single-reply hint",
            details=(
                "В карточке видно блок «Диалог с пользователем» и подсказку: ответ "
                "покупателю — только через «Ответить и завершить». Комментарии в "
                "«Активности» пользователь не видит."
            ),
            details_en=(
                "The card shows Conversation with user and a hint: reply to the "
                "customer only via Reply and complete. Activity comments are not "
                "visible to the user."
            ),
        )

        await worktracker_claim_task(wt_page, editor)
        await worktracker_hitl_single_reply_complete(editor, operator_reply)
        await scenario.step(
            "Ответьте и завершите задачу",
            wt_page,
            screenshot_name="single-reply-completed",
            label_en="Reply and complete the task",
            details=(
                "Введите ответ в поле под диалогом и нажмите «Ответить и завершить». "
                "Задача закрывается, ответ уходит покупателю — не через ленту активности."
            ),
            details_en=(
                "Type the reply under the conversation and click Reply and complete. "
                "The task closes and the answer goes to the customer — not via the "
                "activity thread."
            ),
        )
    finally:
        await wt_page.close()

    await flows_user_chat_wait_text(user_page, operator_reply)
    await scenario.step(
        "Проверьте ответ в чате покупателя",
        user_page,
        screenshot_name="customer-sees-single-reply",
        label_en="Verify the reply in the customer chat",
        details=(
            "**Демонстрация результата.** В чате покупателя виден ответ оператора. "
            "Плашка ожидания снимается после завершения задачи.\n\n"
            "**Итог.** В режиме одного ответа пишите только в «Ответить и завершить»; "
            "«Активность» — для внутренних заметок команды."
        ),
        details_en=(
            "**Result demonstration.** The customer chat shows the operator reply. "
            "The waiting banner clears after the task completes.\n\n"
            "**Summary.** In single-reply mode write only in Reply and complete; "
            "Activity is for internal team notes."
        ),
    )
