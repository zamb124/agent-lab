"""UI E2E сценарии Flows: тестирование и отладка (чат, breakpoints, observability).

Сквозной пример «Зелёный сад» — см. docs/scenarios/flows/CATALOG.md.
"""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    GREEN_GARDEN_STORE,
    GREEN_GARDEN_STORE_EN,
    flows_api_create_flow,
    flows_chat_click_clear,
    flows_chat_echo_payload,
    flows_chat_send_message,
    flows_continue_breakpoint,
    flows_doc_flow_id,
    flows_execution_send_message,
    flows_open_chat_page,
    flows_open_durable_history_modal,
    flows_open_editor,
    flows_open_logs_from_chat,
    flows_open_sessions_modal,
    flows_open_tracing_from_chat,
    flows_switch_editor_mode,
    flows_toggle_breakpoint,
    flows_wait_breakpoint_hit,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="execution",
    doc_slug="test-agent-in-chat",
    title="Тестируем агента в чате",
    description=(
        "**Для чего:** эта инструкция поможет проверить «Помощника Зелёного сада» "
        "так же, как это делает покупатель в диалоге.\n\n"
        "**Какие проблемы решает:** непонятно, где открыть чат агента и как убедиться, "
        "что он отвечает на реальный вопрос.\n\n"
        "**Результат:** агент ответил на вопрос о доставке в ленте чата."
    ),
    title_en="Test the agent in chat",
    description_en=(
        "**What for:** this guide helps you test the Green Garden Assistant the same "
        "way a customer would in a dialog.\n\n"
        "**Problems it solves:** it is unclear where to open the agent chat and how to "
        "confirm it answers a real question.\n\n"
        "**Result:** the agent replied to a delivery question in the chat feed."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_test_agent_in_chat(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    flows_service,
    taskiq_worker,
) -> None:
    _ = flows_service, taskiq_worker
    flow_id = flows_doc_flow_id("chat_test", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_chat_echo_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )

    page = ui_page_system
    await flows_open_chat_page(page, flows_ui, flow_id)
    await scenario.step(
        "Откройте чат агента",
        page,
        screenshot_name="chat-opened",
        label_en="Open the agent chat",
        details=(
            "Перейдите в чат «Помощника Зелёного сада». В центре — лента сообщений, "
            "внизу поле ввода. Это тот же интерфейс, который видит покупатель."
        ),
        details_en=(
            "Open the Green Garden Assistant chat. The message feed is in the center "
            "and the input field is at the bottom. This is the same interface a "
            "customer sees."
        ),
    )

    question = "Здравствуйте! Подскажите про доставку по Воронежу."
    await flows_chat_send_message(page, question)
    await scenario.step(
        "Задайте вопрос о доставке",
        page,
        screenshot_name="question-sent",
        label_en="Ask about delivery",
        details=(
            "Напишите вопрос покупателя — например, про доставку в ваш город — и "
            "отправьте сообщение. Так вы проверяете агента на типичном обращении "
            f"в магазин «{GREEN_GARDEN_STORE}»."
        ),
        details_en=(
            "Type a customer question — for example about delivery to your city — "
            "and send it. This tests the agent on a typical "
            f"{GREEN_GARDEN_STORE_EN} store request."
        ),
    )

    reply = page.get_by_text(re.compile(r"chat-ok:"), exact=False).first
    await expect(reply).to_be_visible(timeout=120_000)
    await scenario.step(
        "Дождитесь ответа в ленте",
        page,
        screenshot_name="reply-streaming-done",
        label_en="Wait for the reply in the feed",
        details=(
            "Подождите, пока ответ появится в ленте чата. Потоковый ответ показывает, "
            "что агент обрабатывает сообщение в реальном времени."
        ),
        details_en=(
            "Wait until the reply appears in the chat feed. A streaming reply shows "
            "the agent is processing the message in real time."
        ),
    )

    await flows_chat_click_clear(page)
    await expect(page.get_by_text(re.compile(r"chat-ok:"), exact=False)).to_have_count(
        0, timeout=30_000
    )
    await scenario.step(
        "Начните новый диалог",
        page,
        screenshot_name="new-chat-cleared",
        label_en="Start a new conversation",
        details=(
            "Очистите ленту или начните новый чат — так проверяют сценарий «с чистого "
            "листа», как покупатель после прошлого обращения. Чипы загрузки Skills в "
            "диалоге описаны в отдельной инструкции."
        ),
        details_en=(
            "Clear the feed or start a new chat — this checks a fresh-start scenario, "
            "like a customer after a previous request. Skill load chips in the dialog "
            "are covered in a separate guide."
        ),
    )

    await flows_chat_send_message(page, "Ещё раз: когда доставка в Воронеж?")
    second = page.get_by_text(re.compile(r"chat-ok:"), exact=False).first
    await expect(second).to_be_visible(timeout=120_000)
    await scenario.step(
        "Проверьте содержательный ответ",
        page,
        screenshot_name="agent-replied",
        label_en="Verify the meaningful reply",
        details=(
            "**Демонстрация результата.** После нового сообщения в ленте снова появился "
            "ответ агента — диалог работает для «Помощника Зелёного сада».\n\n"
            f"**Итог.** Теперь вы умеете открыть чат агента «{GREEN_GARDEN_STORE}», "
            "отправить вопрос и начать новый диалог."
        ),
        details_en=(
            "**Result demonstration.** After the new message an agent reply appears "
            "again — the Green Garden Assistant dialog works.\n\n"
            f"**Summary.** You can open the {GREEN_GARDEN_STORE_EN} agent chat, send a "
            "question, and start a new conversation."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="execution",
    doc_slug="debug-with-breakpoints",
    title="Отлаживаем агента по шагам",
    description=(
        "**Для чего:** эта инструкция поможет остановить выполнение агента на нужном "
        "шаге и посмотреть, что происходит внутри.\n\n"
        "**Какие проблемы решает:** при ошибке в ответе непонятно, на каком шаге "
        "граф пошёл не так.\n\n"
        "**Результат:** выполнение остановилось на точке останова, после продолжения "
        "агент завершил диалог."
    ),
    title_en="Debug the agent step by step",
    description_en=(
        "**What for:** this guide helps you pause the agent at a specific step and "
        "see what happens inside.\n\n"
        "**Problems it solves:** when a reply is wrong, it is unclear which graph step "
        "went off track.\n\n"
        "**Result:** execution paused at a breakpoint and the agent finished the "
        "dialog after you continued."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_debug_with_breakpoints(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    flows_service,
    taskiq_worker,
) -> None:
    _ = flows_service, taskiq_worker
    flow_id = flows_doc_flow_id("breakpoint", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_chat_echo_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_toggle_breakpoint(page, "main")
    await scenario.step(
        "Поставьте точку останова на блоке",
        page,
        screenshot_name="breakpoint-set",
        label_en="Set a breakpoint on the block",
        details=(
            "В редакторе «Помощника Зелёного сада» включите точку останова на блоке "
            "ответа. При следующем запуске выполнение остановится здесь, и вы сможете "
            "осмотреть состояние."
        ),
        details_en=(
            "In the Green Garden Assistant editor, enable a breakpoint on the answer "
            "block. On the next run, execution stops here so you can inspect the state."
        ),
    )

    await flows_switch_editor_mode(page, "run")
    await scenario.step(
        "Переключитесь в режим запуска",
        page,
        screenshot_name="run-mode-for-debug",
        label_en="Switch to run mode",
        details=(
            "Выберите режим «Запуск» в шапке редактора. Справа откроется панель чата "
            "для тестового диалога с точками останова."
        ),
        details_en=(
            "Choose Run mode in the editor header. A chat panel opens on the right "
            "for a test dialog with breakpoints."
        ),
    )

    await flows_execution_send_message(page, "Проверка точки останова")
    await flows_wait_breakpoint_hit(page, "main")
    await scenario.step(
        "Дождитесь остановки на точке останова",
        page,
        screenshot_name="breakpoint-hit",
        label_en="Wait for the breakpoint to hit",
        details=(
            "Отправьте тестовое сообщение. Выполнение остановится на блоке с точкой "
            "останова — на канве блок подсветится, а в чате появится кнопка "
            "«Продолжить»."
        ),
        details_en=(
            "Send a test message. Execution stops at the breakpoint block — the block "
            "is highlighted on the canvas and a Continue button appears in the chat."
        ),
    )

    await flows_continue_breakpoint(page)
    reply = page.locator("flows-execution-panel").get_by_text("chat-ok:", exact=False).first
    await expect(reply).to_be_visible(timeout=120_000)
    await scenario.step(
        "Продолжите выполнение и проверьте ответ",
        page,
        screenshot_name="breakpoint-continued",
        label_en="Continue execution and verify the reply",
        details=(
            "**Демонстрация результата.** Нажмите «Продолжить» — агент завершит шаг "
            "и вернёт ответ в чате запуска. Значит вы контролируете выполнение "
            "пошагово.\n\n"
            f"**Итог.** Теперь вы умеете ставить точки останова и отлаживать агента "
            f"«{GREEN_GARDEN_STORE}» прямо в редакторе."
        ),
        details_en=(
            "**Result demonstration.** Click Continue — the agent finishes the step "
            "and returns a reply in the run chat. You are controlling execution step "
            "by step.\n\n"
            f"**Summary.** You can now set breakpoints and debug the "
            f"{GREEN_GARDEN_STORE_EN} agent directly in the editor."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="execution",
    doc_slug="inspect-traces-logs",
    title="Разбираем, что произошло: трейсы и логи",
    description=(
        "**Для чего:** эта инструкция поможет найти причину неверного ответа после "
        "прогона агента.\n\n"
        "**Какие проблемы решает:** после диалога непонятно, на каком шаге ответ "
        "пошёл не так и что писала система в логах.\n\n"
        "**Результат:** открыты трейс и логи последнего ответа «Помощника Зелёного сада»."
    ),
    title_en="Inspect traces and logs",
    description_en=(
        "**What for:** this guide helps you find why an agent reply was wrong after "
        "a run.\n\n"
        "**Problems it solves:** after a dialog it is unclear which step went wrong "
        "and what the system logged.\n\n"
        "**Result:** the trace and logs for the last Green Garden Assistant reply are "
        "open."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_inspect_traces_logs(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    flows_service,
    taskiq_worker,
) -> None:
    _ = flows_service, taskiq_worker
    flow_id = flows_doc_flow_id("traces_logs", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_chat_echo_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )

    page = ui_page_system
    await flows_open_chat_page(page, flows_ui, flow_id)
    await scenario.step(
        "Откройте чат агента",
        page,
        screenshot_name="observability-chat-opened",
        label_en="Open the agent chat",
        details=(
            "Перейдите в чат «Помощника Зелёного сада». После каждого ответа под "
            "сообщением доступны кнопки трейса и логов."
        ),
        details_en=(
            "Open the Green Garden Assistant chat. After each reply, trace and log "
            "buttons are available under the message."
        ),
    )

    user_line = "Нужна помощь с заказом садовых товаров"
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(f"chat-ok:{user_line}", exact=False).first).to_be_visible(
        timeout=120_000
    )
    await scenario.step(
        "Запустите диалог и дождитесь ответа",
        page,
        screenshot_name="chat-run-complete",
        label_en="Run the dialog and wait for the reply",
        details=(
            "Отправьте вопрос покупателя и дождитесь ответа. К каждому ответу можно "
            "открыть трейс и логи для разбора."
        ),
        details_en=(
            "Send a customer question and wait for the reply. Each answer can be "
            "inspected with traces and logs."
        ),
    )

    tracing_modal = await flows_open_tracing_from_chat(page)
    await expect(tracing_modal).to_be_visible(timeout=30_000)
    await page.keyboard.press("Escape")
    await expect(page.locator("flows-tracing-modal")).to_be_hidden(timeout=15_000)
    await scenario.step(
        "Откройте трейс последнего ответа",
        page,
        screenshot_name="tracing-modal-open",
        label_en="Open the last reply trace",
        details=(
            "Под ответом агента нажмите значок трейса. Откроется дерево шагов "
            "выполнения — по нему видно, какие блоки отработали и сколько времени "
            "занял каждый шаг."
        ),
        details_en=(
            "Under the agent reply, click the trace icon. A step tree opens showing "
            "which blocks ran and how long each step took."
        ),
    )

    logs_modal = await flows_open_logs_from_chat(page)
    await expect(logs_modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте логи этого же ответа",
        page,
        screenshot_name="logs-modal-open",
        label_en="Open logs for the same reply",
        details=(
            "**Демонстрация результата.** Нажмите значок логов рядом с тем же "
            "ответом — откроется журнал системных записей для этого прогона. Трейс "
            "и логи вместе помогают понять, что произошло внутри агента.\n\n"
            f"**Итог.** Теперь вы умеете разбирать ответы «{GREEN_GARDEN_STORE}» "
            "через трейсы и логи после каждого диалога."
        ),
        details_en=(
            "**Result demonstration.** Click the logs icon next to the same reply — "
            "the system log for that run opens. Traces and logs together show what "
            "happened inside the agent.\n\n"
            f"**Summary.** You can now analyze {GREEN_GARDEN_STORE_EN} replies using "
            "traces and logs after each dialog."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="execution",
    doc_slug="time-travel-history",
    title="Возвращаемся к прошлому состоянию",
    description=(
        "**Для чего:** эта инструкция поможет посмотреть историю выполнения диалога "
        "и найти момент, с которого стоит переиграть сценарий.\n\n"
        "**Какие проблемы решает:** после ошибки непонятно, на каком шаге всё "
        "пошло не так, и приходится начинать диалог заново.\n\n"
        "**Результат:** открыта история выполнения с перечнем событий последнего прогона."
    ),
    title_en="Time-travel the run history",
    description_en=(
        "**What for:** this guide helps you review dialog execution history and find "
        "the moment to replay from.\n\n"
        "**Problems it solves:** after a failure it is unclear which step failed and "
        "you have to restart the whole dialog.\n\n"
        "**Result:** execution history is open with a list of events from the last run."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_time_travel_history(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    flows_service,
    taskiq_worker,
) -> None:
    _ = flows_service, taskiq_worker
    flow_id = flows_doc_flow_id("time_travel", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_chat_echo_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )

    page = ui_page_system
    await flows_open_chat_page(page, flows_ui, flow_id)
    await scenario.step(
        "Откройте чат агента",
        page,
        screenshot_name="history-chat-opened",
        label_en="Open the agent chat",
        details=(
            "Перейдите в чат «Помощника Зелёного сада». История выполнения доступна "
            "для диалогов, которые уже запускались хотя бы один раз."
        ),
        details_en=(
            "Open the Green Garden Assistant chat. Execution history is available "
            "for dialogs that have run at least once."
        ),
    )

    user_line = "Проверка истории выполнения"
    await flows_chat_send_message(page, user_line)
    await expect(page.get_by_text(f"chat-ok:{user_line}", exact=False).first).to_be_visible(
        timeout=120_000
    )
    await scenario.step(
        "Запустите диалог",
        page,
        screenshot_name="history-run-done",
        label_en="Run the dialog",
        details=(
            "Отправьте сообщение и дождитесь ответа. После завершения прогона "
            "система сохраняет цепочку событий, по которой можно вернуться назад."
        ),
        details_en=(
            "Send a message and wait for the reply. After the run completes, the "
            "system stores the event chain you can navigate."
        ),
    )

    history_modal = await flows_open_durable_history_modal(page)
    events = history_modal.locator(".event-row")
    await expect(events.first).to_be_visible(timeout=30_000)
    await expect(events).not_to_have_count(0, timeout=30_000)
    await scenario.step(
        "Откройте историю выполнения",
        page,
        screenshot_name="durable-history-opened",
        label_en="Open execution history",
        details=(
            "Нажмите кнопку истории выполнения в чате или выберите пункт в меню. "
            "Откроется модальное окно с цепочкой событий последнего прогона."
        ),
        details_en=(
            "Click the execution history button in the chat or choose the menu item. "
            "A modal opens with the event chain from the last run."
        ),
    )

    await scenario.step(
        "Просмотрите список событий",
        page,
        screenshot_name="durable-history-events",
        label_en="Review the event list",
        details=(
            "**Демонстрация результата.** В списке видны события последнего прогона — "
            "по ним можно выбрать момент для переигрывания или ответвления.\n\n"
            f"**Итог.** Теперь вы умеете просматривать историю выполнения агента "
            f"«{GREEN_GARDEN_STORE}» и находить нужный шаг."
        ),
        details_en=(
            "**Result demonstration.** The list shows events from the last run — you "
            "can pick a moment to replay or branch from.\n\n"
            f"**Summary.** You can now review {GREEN_GARDEN_STORE_EN} agent execution "
            "history and find the step you need."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="execution",
    doc_slug="find-past-sessions",
    title="Находим и продолжаем прошлые диалоги",
    description=(
        "**Для чего:** эта инструкция поможет найти прошлый диалог покупателя "
        "и вернуться к нему из редактора.\n\n"
        "**Какие проблемы решает:** после нескольких тестовых запусков теряется "
        "нужная переписка, и непонятно, где её искать.\n\n"
        "**Результат:** список сессий открыт из редактора, виден недавний диалог."
    ),
    title_en="Find and resume past sessions",
    description_en=(
        "**What for:** this guide helps you find a past customer dialog and return "
        "to it from the editor.\n\n"
        "**Problems it solves:** after several test runs the needed conversation is "
        "lost and it is unclear where to look.\n\n"
        "**Result:** the sessions list is open from the editor and shows a recent dialog."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_find_past_sessions(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    flows_service,
    taskiq_worker,
) -> None:
    _ = flows_service, taskiq_worker
    flow_id = flows_doc_flow_id("sessions", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_chat_echo_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )

    page = ui_page_system
    await flows_open_chat_page(page, flows_ui, flow_id)
    marker = f"session-marker-{unique_id}"
    await flows_chat_send_message(page, marker)
    await expect(page.get_by_text(f"chat-ok:{marker}", exact=False).first).to_be_visible(
        timeout=120_000
    )
    await scenario.step(
        "Создайте тестовый диалог",
        page,
        screenshot_name="session-created",
        label_en="Create a test dialog",
        details=(
            "Откройте чат «Помощника Зелёного сада» и отправьте сообщение. Так "
            "появится сессия, которую потом можно найти в списке прошлых диалогов."
        ),
        details_en=(
            "Open the Green Garden Assistant chat and send a message. This creates "
            "a session you can later find in the past dialogs list."
        ),
    )

    await flows_open_editor(page, flows_ui, flow_id)
    await scenario.step(
        "Откройте агента в редакторе",
        page,
        screenshot_name="editor-for-sessions",
        label_en="Open the agent in the editor",
        details=(
            "Перейдите в редактор того же агента. Список сессий доступен из меню "
            "дополнительных действий в шапке."
        ),
        details_en=(
            "Go to the same agent editor. The sessions list is available from the "
            "overflow menu in the header."
        ),
    )

    sessions_modal = await flows_open_sessions_modal(page, flows_ui)
    session_rows = sessions_modal.locator(".flows-sessions-table tbody tr")
    await expect(session_rows.first).to_be_visible(timeout=30_000)
    await expect(session_rows).not_to_have_count(0, timeout=30_000)
    await scenario.step(
        "Откройте список сессий",
        page,
        screenshot_name="sessions-modal-open",
        label_en="Open the sessions list",
        details=(
            "В меню «⋯» выберите «Сессии». Откроется таблица прошлых диалогов "
            "с датой последней активности."
        ),
        details_en=(
            "In the ⋯ menu choose Sessions. A table of past dialogs opens with "
            "last activity dates."
        ),
    )

    await expect(session_rows.first).to_be_visible(timeout=30_000)
    row_count = await session_rows.count()
    assert row_count >= 1, "sessions table must list at least one dialog"
    await scenario.step(
        "Найдите недавний диалог в таблице",
        page,
        screenshot_name="session-row-visible",
        label_en="Find the recent dialog in the table",
        details=(
            "**Демонстрация результата.** В таблице есть хотя бы одна строка с недавней "
            "активностью — значит, тестовая сессия сохранилась и её можно открыть снова.\n\n"
            f"**Итог.** Теперь вы умеете находить прошлые диалоги «{GREEN_GARDEN_STORE}» "
            "и возвращаться к ним из редактора."
        ),
        details_en=(
            "**Result demonstration.** The table has at least one row with recent activity — "
            "your test session was saved and you can reopen it.\n\n"
            f"**Summary.** You can now find past {GREEN_GARDEN_STORE_EN} dialogs and "
            "return to them from the editor."
        ),
    )
