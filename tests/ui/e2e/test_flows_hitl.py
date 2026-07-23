"""UI E2E сценарии Flows: операторы и HITL (сторона агента и покупателя).

Сквозной пример «Зелёный сад» — см. docs/scenarios/flows/CATALOG.md (блок 4a, A1–A5).
"""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    GREEN_GARDEN_SUPPORT_QUEUE,
    flows_api_create_flow,
    flows_background_task_payload,
    flows_chat_send_message,
    flows_doc_flow_id,
    flows_e2e_ensure_canvas_layout,
    flows_open_chat_page,
    flows_open_durable_history_modal,
    flows_open_editor,
    flows_open_node_editor,
    flows_seed_mock_llm,
)
from tests.ui.e2e.hitl_e2e_bridge import (
    EXAMPLE_REACT_ID,
    GREEN_GARDEN_HITL_MESSAGE,
    GREEN_GARDEN_OPERATOR_REPLY,
    HITL_BRANCH_NODE,
    HITL_BRANCH_REACT,
    HITL_NODE_PAUSE,
    HITL_REACT_NODE,
    hitl_open_react_branch_chat,
    hitl_operator_claim_and_complete,
    hitl_return_to_chat_session,
    hitl_trigger_deterministic,
)
from tests.ui.e2e.worktracker_e2e_helpers import (
    worktracker_api_list_work_items,
    worktracker_open_inbox,
    worktracker_open_task_page,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_ = os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    timeout_seconds=60,
    doc_slug="escalate-to-operator",
    title="Передаём сложный случай оператору",
    description=(
        "**Для чего:** эта инструкция поможет настроить передачу сложного обращения "
        "покупателя живому оператору через очередь «Поддержка клиентов».\n\n"
        "**Какие проблемы решает:** агент не всегда может решить спорный вопрос сам — "
        "нужно понять, где в графе включить паузу и ожидание ответа человека.\n\n"
        "**Результат:** диалог уходит в очередь поддержки, и покупатель видит понятное "
        "сообщение об ожидании оператора."
    ),
    title_en="Escalate a hard case to an operator",
    description_en=(
        "**What for:** this guide helps you route a complex customer request to a live "
        "operator through the Customer Support queue.\n\n"
        "**Problems it solves:** the agent cannot always resolve a disputed issue alone; "
        "you need to know where in the graph to pause and wait for a human reply.\n\n"
        "**Result:** the dialog goes to the support queue and the customer sees a clear "
        "message that an operator is on the way."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_escalate_to_operator(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker
    page = ui_page_system
    await flows_open_editor(page, flows_ui, EXAMPLE_REACT_ID, branch_id=HITL_BRANCH_NODE)
    await scenario.step(
        "Откройте ветку с передачей оператору",
        page,
        screenshot_name="hitl-branch-editor",
        label_en="Open the operator handoff branch",
        details=(
            "В редакторе «Помощника Зелёного сада» откройте демо-ветку с нодой передачи "
            "оператору. На канве видно, что перед паузой подготавливается контекст "
            "обращения, а затем диалог останавливается до ответа человека."
        ),
        details_en=(
            "In the Green Garden Assistant editor, open the demo branch with the operator "
            "handoff node. The canvas shows that context is prepared before the pause, and "
            "then the dialog stops until a human replies."
        ),
    )

    hitl_node = page.locator(
        f"flows-flow-canvas g.node[data-node-id='{HITL_NODE_PAUSE}']"
    ).first
    await expect(hitl_node).to_be_visible(timeout=30_000)
    _ = await flows_open_node_editor(page, HITL_NODE_PAUSE)
    queue_field = page.locator("flows-hitl-node-editor platform-field").first
    await expect(queue_field).to_be_visible(timeout=15_000)
    await scenario.step(
        "Проверьте настройки ноды передачи",
        page,
        screenshot_name="hitl-node-settings",
        label_en="Check the handoff node settings",
        details=(
            "Откройте ноду передачи оператору. Укажите очередь «Поддержка клиентов» "
            "(демо-очередь example_hitl), режим «один ответ», заголовок задачи и текст "
            "для покупателя на время ожидания. Так агент объясняет, что запрос передан "
            "живому специалисту."
        ),
        details_en=(
            "Open the operator handoff node. Set the Customer Support queue (demo queue "
            "example_hitl), single-reply mode, task title, and the waiting message for the "
            "customer. This way the agent explains that the request was passed to a live "
            "specialist."
        ),
    )

    _ = await hitl_open_react_branch_chat(page, flows_ui, branch_id=HITL_BRANCH_NODE)
    await hitl_trigger_deterministic(page, "Нужен оператор по доставке в Воронеж")
    banner = page.locator("chat-page .input-required-banner").first
    await expect(banner).to_be_visible(timeout=30_000)
    await scenario.step(
        "Запустите тестовый чат и доведите до передачи",
        page,
        screenshot_name="hitl-chat-waiting",
        label_en="Run test chat until handoff",
        details=(
            "Отправьте в чате сообщение, которое запускает передачу оператору. "
            "Появится плашка ожидания — диалог поставлен на паузу до ответа из очереди "
            "«Поддержка клиентов»."
        ),
        details_en=(
            "Send a chat message that triggers operator handoff. A waiting banner appears — "
            "the dialog is paused until a reply from the Customer Support queue."
        ),
    )

    task_badge = page.locator("chat-page platform-work-item-badge[work-item-id]").first
    await expect(task_badge).to_be_visible(timeout=30_000)
    await scenario.step(
        "Проверьте карточку задачи в чате",
        page,
        screenshot_name="hitl-task-badge-visible",
        label_en="Check the task badge in chat",
        details=(
            "**Демонстрация результата.** Рядом с плашкой ожидания видна карточка задачи — "
            "значит, обращение попало в очередь и ждёт оператора.\n\n"
            "**Итог.** Теперь вы умеете настроить ноду передачи оператору и увидеть, как "
            "покупатель ждёт ответа живого специалиста."
        ),
        details_en=(
            "**Result demonstration.** A task badge appears next to the waiting banner — "
            "the request reached the queue and waits for an operator.\n\n"
            "**Summary.** You can now configure the operator handoff node and see how the "
            "customer waits for a live specialist."
        ),
    )
    _ = GREEN_GARDEN_SUPPORT_QUEUE


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    timeout_seconds=60,
    doc_slug="agent-decides-to-escalate",
    title="Агент сам зовёт оператора",
    description=(
        "**Для чего:** эта инструкция покажет, как дать агенту инструмент «передать "
        "оператору» и позволить ему самому решать, когда нужен человек.\n\n"
        "**Какие проблемы решает:** заранее неизвестно, какой вопрос окажется сложным — "
        "жёсткая развилка на графе срабатывает не всегда к месту.\n\n"
        "**Результат:** при спорном вопросе о возврате агент сам передаёт диалог в очередь "
        "«Поддержка клиентов»."
    ),
    title_en="Let the agent call an operator itself",
    description_en=(
        "**What for:** this guide shows how to give the agent a hand-off-to-operator tool "
        "and let it decide when a human is needed.\n\n"
        "**Problems it solves:** you cannot predict which question will be complex; a fixed "
        "graph branch does not always fit.\n\n"
        "**Result:** on a disputed return question, the agent itself routes the dialog to "
        "the Customer Support queue."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_agent_decides_to_escalate(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker
    await flows_seed_mock_llm(
        [
            {
                "type": "tool_call",
                "tool": "hitl_operator_task",
                "args": {
                    "question": GREEN_GARDEN_HITL_MESSAGE,
                    "task_title": "Возврат без чека — Зелёный сад",
                    "assignee_queue": "example_hitl",
                    "handoff_mode": "single_reply",
                },
            },
        ]
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, EXAMPLE_REACT_ID, branch_id=HITL_BRANCH_REACT)
    await flows_e2e_ensure_canvas_layout(page)
    react_node = page.locator(
        f"flows-flow-canvas g.node[data-node-id='{HITL_REACT_NODE}']"
    ).first
    await expect(react_node).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте ветку агента с инструментами",
        page,
        screenshot_name="hitl-tools-branch-opened",
        label_en="Open the agent branch with tools",
        details=(
            "Откройте ветку, где агент работает в режиме «Инструменты». На канве видна "
            "нода ответа с подключёнными операциями."
        ),
        details_en=(
            "Open the branch where the agent runs in Tools mode. The canvas shows the "
            "answer node with attached operations."
        ),
    )

    _ = await flows_open_node_editor(page, HITL_REACT_NODE)
    await scenario.step(
        "Проверьте инструмент передачи оператору",
        page,
        screenshot_name="hitl-tool-node-opened",
        label_en="Check the handoff-to-operator tool",
        details=(
            "Откройте ноду агента. В списке инструментов есть «передать оператору» — "
            "агент вызывает его сам, когда вопрос слишком сложный. В инструкции опишите, "
            "при каких случаях звать человека (возврат, спор, жалоба)."
        ),
        details_en=(
            "Open the agent node. The tool list includes hand-off to operator; the agent "
            "calls it when the question is too complex. In the instruction, describe when "
            "to call a human (return, dispute, complaint)."
        ),
    )

    _ = await hitl_open_react_branch_chat(page, flows_ui, branch_id=HITL_BRANCH_REACT)
    await scenario.step(
        "Откройте тестовый чат этой ветки",
        page,
        screenshot_name="hitl-branch-chat-opened",
        label_en="Open this branch test chat",
        details=(
            "Откройте чат выбранной ветки. Так вы проверяете поведение именно этой "
            "конфигурации агента, а не другой экспериментальной ветки."
        ),
        details_en=(
            "Open the selected branch chat. This tests this agent configuration, not "
            "another experimental branch."
        ),
    )

    await hitl_trigger_deterministic(page, GREEN_GARDEN_HITL_MESSAGE)
    await scenario.step(
        "Задайте сложный вопрос в чате",
        page,
        screenshot_name="agent-initiated-handoff",
        label_en="Ask a complex question in chat",
        details=(
            "**Демонстрация результата.** Напишите про спорный возврат без чека. Агент "
            "сам вызывает инструмент передачи — в чате появляется ожидание оператора, "
            "хотя на графе нет отдельной жёсткой развилки.\n\n"
            "**Итог.** Теперь вы умеете доверять агенту решение, когда подключать "
            "оператора из очереди «Поддержка клиентов»."
        ),
        details_en=(
            "**Result demonstration.** Ask about a disputed return without a receipt. The "
            "agent calls the handoff tool on its own; the chat shows operator waiting even "
            "without a separate hard branch on the graph.\n\n"
            "**Summary.** You can now let the agent decide when to involve an operator from "
            "the Customer Support queue."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="execution",
    timeout_seconds=60,
    doc_slug="customer-waits-for-operator",
    title="Что видит покупатель, пока ждёт оператора",
    description=(
        "**Для чего:** эта инструкция покажет поведение чата глазами покупателя, когда "
        "агент передал вопрос оператору Марине.\n\n"
        "**Какие проблемы решает:** непонятно, завис ли чат, можно ли писать дальше и как "
        "придёт ответ живого человека.\n\n"
        "**Результат:** покупатель видит ожидание, карточку задачи и получает ответ "
        "оператора прямо в ленте чата."
    ),
    title_en="What the customer sees while waiting for an operator",
    description_en=(
        "**What for:** this guide shows chat behavior from the customer's perspective "
        "when the agent handed the question to operator Marina.\n\n"
        "**Problems it solves:** it is unclear whether the chat froze, whether you can "
        "keep typing, and how a human reply will arrive.\n\n"
        "**Result:** the customer sees waiting state, a task badge, and the operator's "
        "answer in the chat feed."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_flows_customer_waits_for_operator(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    page = ui_page_system
    _ = await hitl_open_react_branch_chat(page, flows_ui, branch_id=HITL_BRANCH_NODE)
    await scenario.step(
        "Откройте чат агента как покупатель",
        page,
        screenshot_name="customer-chat-opened",
        label_en="Open the agent chat as a customer",
        details=(
            "Откройте чат «Помощника Зелёного сада» в демо-ветке с передачей оператору. "
            "Здесь покупатель задаёт вопросы так же, как в реальном магазине."
        ),
        details_en=(
            "Open the Green Garden Assistant chat in the demo branch with operator handoff. "
            "Here the customer asks questions the same way as in a real store."
        ),
    )

    work_item_id = await hitl_trigger_deterministic(
        page, "Хочу вернуть куст без чека — помогите"
    )
    banner = page.locator("chat-page .input-required-banner").first
    await expect(banner).to_be_visible(timeout=30_000)
    await scenario.step(
        "Дождитесь передачи оператору",
        page,
        screenshot_name="waiting-banner-visible",
        label_en="Wait for operator handoff",
        details=(
            "Отправьте сложный вопрос. Появится плашка ожидания и значок задачи — чат "
            "не завис, а ждёт ответа из очереди «Поддержка клиентов»."
        ),
        details_en=(
            "Send a complex question. A waiting banner and task badge appear; the chat did "
            "not freeze but waits for a reply from the Customer Support queue."
        ),
    )

    await expect(page.get_by_text(re.compile(r"оператор|operator|ожидан|waiting", re.I)).first).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Проверьте текст ожидания для покупателя",
        page,
        screenshot_name="waiting-message-visible",
        label_en="Check the waiting message for the customer",
        details=(
            "Убедитесь, что в чате виден понятный текст ожидания — покупатель понимает, "
            "что запрос передан живому специалисту и ответ придёт в эту же ленту."
        ),
        details_en=(
            "Make sure the chat shows a clear waiting message — the customer understands "
            "the request was passed to a live specialist and the reply will appear here."
        ),
    )

    await hitl_operator_claim_and_complete(
        flows_ui.origin,
        auth_token_system,
        work_item_id,
        GREEN_GARDEN_OPERATOR_REPLY,
    )
    await hitl_return_to_chat_session(
        page,
        origin=flows_ui.origin,
        auth_token=auth_token_system,
        work_item_id=work_item_id,
        flows_ui=flows_ui,
        flow_id=EXAMPLE_REACT_ID,
        expect_operator_text=GREEN_GARDEN_OPERATOR_REPLY,
    )
    await scenario.step(
        "Получите ответ оператора в чате",
        page,
        screenshot_name="operator-reply-in-chat",
        label_en="Receive the operator reply in chat",
        details=(
            "**Демонстрация результата.** После ответа оператора Марины плашка ожидания "
            "исчезает, а её текст появляется в ленте чата — покупатель видит ответ живого "
            "человека и может продолжить диалог.\n\n"
            "**Итог.** Теперь вы понимаете, что видит покупатель при передаче оператору и "
            "как ответ человека возвращается в чат агента."
        ),
        details_en=(
            "**Result demonstration.** After operator Marina replies, the waiting banner "
            "disappears and her text appears in the chat feed; the customer sees a human "
            "answer and can continue the dialog.\n\n"
            "**Summary.** You now understand what the customer sees during operator handoff "
            "and how a human reply returns to the agent chat."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    timeout_seconds=60,
    doc_slug="agent-logs-background-task",
    title="Агент ставит фоновую задачу команде",
    description=(
        "**Для чего:** эта инструкция поможет научить агента создавать поручение людям "
        "без остановки диалога с покупателем.\n\n"
        "**Какие проблемы решает:** перезвон или проверка остатка нужны команде, но "
        "покупателя нельзя заставлять ждать на линии.\n\n"
        "**Результат:** агент сразу отвечает покупателю, а фоновая задача появляется в "
        "очереди «Поддержка клиентов»."
    ),
    title_en="Agent files a background task for the team",
    description_en=(
        "**What for:** this guide helps you teach the agent to create a task for people "
        "without stopping the customer dialog.\n\n"
        "**Problems it solves:** a callback or stock check needs the team, but the customer "
        "should not wait on the line.\n\n"
        "**Result:** the agent replies immediately while a background task appears in the "
        "Customer Support queue."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_agent_logs_background_task(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    worktracker_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    flow_id = flows_doc_flow_id("bg_task", unique_id)
    task_title = f"Перезвонить по доставке ({unique_id})"
    _ = await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_background_task_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )
    await flows_seed_mock_llm(
        [
            {
                "type": "tool_call",
                "tool": "work_item_create",
                "args": {
                    "title": task_title,
                    "description": "Покупатель просил перезвон по доставке в Воронеж",
                    "assignee_type": "queue",
                    "assignee_queue_slug": "example_hitl",
                    "blocking": False,
                },
            },
            {
                "type": "text",
                "content": (
                    "Запрос на перезвон передан команде «Зелёного сада». "
                    "Пока могу подсказать по ассортименту и срокам доставки."
                ),
            },
        ]
    )

    page = ui_page_system
    await flows_open_chat_page(page, flows_ui, flow_id)
    await scenario.step(
        "Откройте чат агента с фоновой задачей",
        page,
        screenshot_name="background-task-chat-opened",
        label_en="Open the agent chat with background tasks",
        details=(
            "Откройте чат агента, у которого есть инструмент создания задачи без ожидания. "
            "Так агент может поручить перезвон или проверку остатка команде и сразу "
            "продолжить разговор с покупателем."
        ),
        details_en=(
            "Open the agent chat that has a non-blocking task creation tool. This lets the "
            "agent assign a callback or stock check to the team and keep talking to the "
            "customer right away."
        ),
    )

    await flows_chat_send_message(page, "Перезвоните, пожалуйста, по доставке завтра")
    reply = page.get_by_text(re.compile(r"передан команде", re.IGNORECASE)).first
    await expect(reply).to_be_visible(timeout=120_000)
    await expect(page.locator("chat-page .input-required-banner")).to_be_hidden(timeout=10_000)
    await scenario.step(
        "Попросите перезвон и получите мгновенный ответ",
        page,
        screenshot_name="agent-replied-without-pause",
        label_en="Request a callback and get an instant reply",
        details=(
            "Попросите перезвон. Агент отвечает сразу — без плашки ожидания — и сообщает, "
            "что поручение передано команде. Диалог с покупателем не прерывается."
        ),
        details_en=(
            "Ask for a callback. The agent replies immediately, without a waiting banner, "
            "and says the request was passed to the team. The customer dialog is not "
            "interrupted."
        ),
    )

    items = await worktracker_api_list_work_items(
        worktracker_ui.origin,
        auth_token_system,
        exclude_terminal="true",
    )
    matched = [item for item in items if task_title in str(item.get("title") or "")]
    if not matched:
        raise AssertionError(f"Background task {task_title!r} not found in worktracker")
    background_work_item_id = str(matched[0]["work_item_id"])
    await worktracker_open_inbox(page, worktracker_ui)
    # Фоновая задача — в queue inbox (не «Assigned to you»). Ждём карточку / deep-link.
    title_loc = page.locator("worktracker-inbox-page").get_by_text(task_title, exact=False).first
    try:
        await expect(title_loc).to_be_visible(timeout=20_000)
    except AssertionError:
        await worktracker_open_task_page(page, worktracker_ui, background_work_item_id)
        await expect(page.get_by_text(task_title, exact=False).first).to_be_visible(timeout=15_000)
        await worktracker_open_inbox(page, worktracker_ui)
        await expect(title_loc).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте входящие задач команды",
        page,
        screenshot_name="background-task-in-inbox-list",
        label_en="Open the team task inbox",
        details=(
            "Перейдите во входящие раздела задач. В списке должно появиться новое поручение "
            "«Перезвонить по доставке» — агент создал его, не прерывая чат с покупателем."
        ),
        details_en=(
            "Open inbox in the tasks section. The new callback assignment should appear — "
            "the agent created it without stopping the customer chat."
        ),
    )

    await worktracker_open_task_page(page, worktracker_ui, background_work_item_id)
    await scenario.step(
        "Откройте карточку фоновой задачи",
        page,
        screenshot_name="background-task-in-inbox",
        label_en="Open the background task card",
        details=(
            "**Демонстрация результата.** Карточка задачи открыта — видны заголовок, очередь "
            "«Поддержка клиентов» и описание перезвона, хотя чат агента уже продолжил "
            "отвечать покупателю.\n\n"
            "**Итог.** Теперь вы отличаете фоновую задачу от паузы HITL: покупатель не "
            "ждёт, а команда получает поручение в очередь."
        ),
        details_en=(
            "**Result demonstration.** The task card is open — title, Customer Support queue, "
            "and callback description are visible even though the agent chat already "
            "continued with the customer.\n\n"
            "**Summary.** You can now tell a background task from an HITL pause: the "
            "customer does not wait, and the team gets the assignment in the queue."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="execution",
    timeout_seconds=60,
    doc_slug="trace-operator-handoff",
    title="Смотрим передачу оператору в истории выполнения",
    description=(
        "**Для чего:** эта инструкция поможет разобрать после прогона, где агент "
        "передал диалог оператору и когда диалог возобновился.\n\n"
        "**Какие проблемы решает:** по одному чату не видно, в какой момент и в какую "
        "очередь ушла задача.\n\n"
        "**Результат:** в истории выполнения найдены события передачи и возврата после "
        "ответа оператора."
    ),
    title_en="See the operator handoff in the run history",
    description_en=(
        "**What for:** this guide helps you review after a run where the agent handed the "
        "dialog to an operator and when it resumed.\n\n"
        "**Problems it solves:** a single chat view does not show when and to which queue "
        "the task was sent.\n\n"
        "**Result:** the run history shows handoff and resume events after the operator "
        "replied."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_flows_trace_operator_handoff(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    hitl_demo_ready: str,
    flows_service,
    taskiq_worker,
    worktracker_http_service,
) -> None:
    _ = hitl_demo_ready, flows_service, taskiq_worker, worktracker_http_service
    page = ui_page_system
    _ = await hitl_open_react_branch_chat(page, flows_ui, branch_id=HITL_BRANCH_NODE)
    work_item_id = await hitl_trigger_deterministic(page, GREEN_GARDEN_HITL_MESSAGE)
    await hitl_operator_claim_and_complete(
        flows_ui.origin,
        auth_token_system,
        work_item_id,
        GREEN_GARDEN_OPERATOR_REPLY,
    )
    await hitl_return_to_chat_session(
        page,
        origin=flows_ui.origin,
        auth_token=auth_token_system,
        work_item_id=work_item_id,
        flows_ui=flows_ui,
        flow_id=EXAMPLE_REACT_ID,
        expect_operator_text=GREEN_GARDEN_OPERATOR_REPLY,
    )

    modal = await flows_open_durable_history_modal(page)
    await scenario.step(
        "Откройте историю выполнения диалога",
        page,
        screenshot_name="durable-history-opened",
        label_en="Open the dialog run history",
        details=(
            "В чате откройте историю выполнения — это журнал всех шагов агента: ноды, "
            "инструменты, передачи оператору и возобновления."
        ),
        details_en=(
            "In chat, open run history; it is the log of all agent steps: nodes, tools, "
            "operator handoffs, and resumes."
        ),
    )

    requested = modal.get_by_text("HandoffRequested", exact=True).first
    await expect(requested).to_be_visible(timeout=30_000)
    await scenario.step(
        "Найдите событие передачи оператору",
        page,
        screenshot_name="handoff-requested-event",
        label_en="Find the operator handoff event",
        details=(
            "В списке событий найдите HandoffRequested — это момент, когда агент передал "
            "диалог в очередь «Поддержка клиентов» и создал задачу для оператора."
        ),
        details_en=(
            "In the event list, find HandoffRequested; that is when the agent handed the "
            "dialog to the Customer Support queue and created an operator task."
        ),
    )

    resumed = modal.get_by_text("HandoffResumed", exact=True).first
    await expect(resumed).to_be_visible(timeout=30_000)
    await scenario.step(
        "Найдите событие возврата после ответа",
        page,
        screenshot_name="handoff-resumed-event",
        label_en="Find the resume event after the reply",
        details=(
            "Прокрутите список до HandoffResumed — это момент, когда оператор ответил "
            "и управление вернулось агенту."
        ),
        details_en=(
            "Scroll the list to HandoffResumed — that is when the operator replied "
            "and control returned to the agent."
        ),
    )

    await expect(modal.get_by_text("HandoffRequested", exact=True).first).to_be_visible(
        timeout=15_000
    )
    await expect(modal.get_by_text("HandoffResumed", exact=True).first).to_be_visible(
        timeout=15_000
    )
    await scenario.step(
        "Сверьте цепочку передачи и возврата",
        page,
        screenshot_name="handoff-chain-visible",
        label_en="Review the handoff and resume chain",
        details=(
            "**Демонстрация результата.** В одном списке видны HandoffRequested и "
            "HandoffResumed — полная картина передачи человеку и возобновления диалога.\n\n"
            "**Итог.** Теперь вы умеете читать историю выполнения и находить передачу "
            "оператору и возврат диалога агенту."
        ),
        details_en=(
            "**Result demonstration.** HandoffRequested and HandoffResumed appear in one "
            "list — the full picture of human handoff and dialog resume.\n\n"
            "**Summary.** You can now read run history and find operator handoff and "
            "dialog resume events."
        ),
    )
