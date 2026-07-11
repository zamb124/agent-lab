"""UI E2E сценарии Worktracker: операторский цикл HITL.

Сквозной пример «Зелёный сад» — см. docs/scenarios/flows/CATALOG.md (блок 4a, B1–B5).
"""

from __future__ import annotations

import os

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_OPERATOR,
    GREEN_GARDEN_RETURNS_QUEUE,
    GREEN_GARDEN_SUPPORT_QUEUE,
    flows_doc_flow_id,
    flows_open_chat_page,
)
from tests.ui.e2e.hitl_e2e_bridge import (
    EXAMPLE_GRAPH_ID,
    EXAMPLE_REACT_ID,
    GREEN_GARDEN_HITL_MESSAGE,
    GREEN_GARDEN_OPERATOR_REPLY,
    GREEN_GARDEN_TAKEOVER_MESSAGE,
    HITL_BRANCH_NODE,
    hitl_open_react_branch_chat,
    hitl_trigger_deterministic,
    hitl_wait_chat_resume,
)
from tests.ui.e2e.worktracker_e2e_helpers import (
    worktracker_add_comment,
    worktracker_api_complete_work_item,
    worktracker_api_create_board,
    worktracker_api_create_queue,
    worktracker_api_create_work_item,
    worktracker_api_reassign_work_item,
    worktracker_claim_task,
    worktracker_create_queue_ui,
    worktracker_open_inbox,
    worktracker_open_queues,
    worktracker_open_task_page,
)
from tests.ui.harness import AppUI
from tests.ui.personas import UiTestUser
from tests.ui.scenario_doc import ScenarioRecorder

_ = os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

OPERATOR_FOLLOWUP = "Уточните, пожалуйста, номер заказа для возврата."


@pytest.mark.scenario(
    service="worktracker",
    tag="operators",
    doc_slug="setup-operator-queue",
    title="Готовим очередь поддержки для агента",
    description=(
        "**Для чего:** эта инструкция поможет собрать очередь, в которую агенты будут "
        "передавать сложные обращения покупателей.\n\n"
        "**Какие проблемы решает:** без очереди и назначенных людей задачи от агента "
        "просто некому разбирать.\n\n"
        "**Результат:** создана очередь «Поддержка клиентов», и в ней появляется раздел "
        "входящих, куда будут попадать задачи от агента."
    ),
    title_en="Set up a support queue for the agent",
    description_en=(
        "**What for:** this guide helps you build a queue where agents route complex "
        "customer requests.\n\n"
        "**Problems it solves:** without a queue and assigned people, there's no one to "
        "handle the agent's tasks.\n\n"
        "**Result:** the Customer Support queue is created and shows an inbox section "
        "where agent tasks will arrive."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_worktracker_setup_operator_queue(
    scenario: ScenarioRecorder,
    worktracker_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await worktracker_open_queues(page, worktracker_ui)
    await scenario.step(
        "Откройте раздел очередей",
        page,
        screenshot_name="queues-page",
        label_en="Open the queues section",
        details=(
            "В сервисе задач откройте раздел очередей. Очередь — это общий ящик задач, из "
            "которого операторы разбирают обращения. Сюда агент будет складывать сложные "
            "случаи."
        ),
        details_en=(
            "In the tasks service, open the queues section. A queue is a shared task "
            "inbox operators pull from. This is where the agent will drop complex cases."
        ),
    )

    slug = flows_doc_flow_id("support", unique_id).replace("_", "-")
    await worktracker_create_queue_ui(page, name=GREEN_GARDEN_SUPPORT_QUEUE, slug=slug)
    queue_row = page.locator("worktracker-queues-page button.queue-row").filter(
        has_text=GREEN_GARDEN_SUPPORT_QUEUE
    ).first
    await expect(queue_row).to_be_visible(timeout=30_000)
    await scenario.step(
        "Создайте очередь поддержки",
        page,
        screenshot_name="queue-created",
        label_en="Create the support queue",
        details=(
            "Нажмите создание очереди, укажите название «Поддержка клиентов» и короткий "
            "идентификатор. После сохранения очередь появляется в списке."
        ),
        details_en=(
            "Click create queue, enter the name Customer Support and a short identifier. "
            "After saving, the queue appears in the list."
        ),
    )

    await queue_row.click()
    detail = page.locator("worktracker-queue-detail-page").first
    await expect(detail).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте очередь и её входящие",
        page,
        screenshot_name="queue-detail",
        label_en="Open the queue and its inbox",
        details=(
            "**Демонстрация результата.** Откройте очередь — внутри есть раздел входящих и "
            "список участников. Сюда попадут задачи от агента, и здесь добавляют "
            "операторов, например Марину.\n\n"
            "**Итог.** Теперь у вас есть очередь поддержки, готовая принимать обращения от "
            "агента."
        ),
        details_en=(
            "**Result demonstration.** Open the queue — inside there is an inbox section "
            "and a members list. Agent tasks land here, and this is where you add "
            "operators such as Marina.\n\n"
            "**Summary.** You now have a support queue ready to receive requests from the "
            "agent."
        ),
    )
    _ = GREEN_GARDEN_OPERATOR
    _ = UiTestUser


@pytest.mark.scenario(
    service="worktracker",
    tag="operators",
    doc_slug="operator-inbox-single-reply",
    title="Оператор берёт задачу и отвечает один раз",
    description=(
        "**Для чего:** эта инструкция покажет базовый цикл: агент передал обращение — "
        "оператор Марина ответила — диалог с покупателем продолжился.\n\n"
        "**Какие проблемы решает:** оператор не понимает, откуда приходят задачи агента "
        "и как вернуть ответ в чат покупателю.\n\n"
        "**Результат:** Марина взяла задачу из очереди «Поддержка клиентов», ответила и "
        "закрыла её — агент продолжил диалог."
    ),
    title_en="Operator claims a task and replies once",
    description_en=(
        "**What for:** this guide shows the basic loop: the agent handed off — operator "
        "Marina replied — the customer dialog continued.\n\n"
        "**Problems it solves:** operators are unsure where agent tasks come from and how "
        "to return an answer to the customer chat.\n\n"
        "**Result:** Marina claimed a task from the Customer Support queue, replied, closed "
        "it, and the agent continued the dialog."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_worktracker_operator_inbox_single_reply(
    scenario: ScenarioRecorder,
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
    page = ui_page_system
    await hitl_open_react_branch_chat(page, flows_ui, branch_id=HITL_BRANCH_NODE)
    work_item_id = await hitl_trigger_deterministic(page, GREEN_GARDEN_HITL_MESSAGE)

    wt_page = await page.context.new_page()
    try:
        await worktracker_open_inbox(wt_page, worktracker_ui)
        await scenario.step(
            "Откройте входящие оператора",
            wt_page,
            screenshot_name="operator-inbox-opened",
            label_en="Open the operator inbox",
            details=(
                "Перейдите в раздел задач и откройте входящие. В блоке очереди появится "
                "задача от «Помощника Зелёного сада» — сюда попадают сложные обращения "
                "покупателей."
            ),
            details_en=(
                "Go to tasks and open inbox. The queue section shows a task from the Green "
                "Garden Assistant; complex customer requests land here."
            ),
        )

        await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
        editor = wt_page.locator(
            f"work-item-detail-editor[work-item-id='{work_item_id}']"
        ).first
        await worktracker_claim_task(wt_page, editor)
        await scenario.step(
            "Возьмите задачу себе",
            wt_page,
            screenshot_name="operator-task-claimed",
            label_en="Claim the task",
            details=(
                "Откройте карточку задачи и нажмите «Взять себе». Так Марина фиксирует, что "
                "именно она отвечает покупателю, и видит контекст обращения из чата агента."
            ),
            details_en=(
                "Open the task card and click claim. Marina marks that she will answer the "
                "customer and sees the request context from the agent chat."
            ),
        )

        await worktracker_api_complete_work_item(
            worktracker_ui.origin,
            auth_token_system,
            work_item_id,
            resolution_text=GREEN_GARDEN_OPERATOR_REPLY,
        )
    finally:
        await wt_page.close()

    await hitl_wait_chat_resume(page, expect_operator_text=GREEN_GARDEN_OPERATOR_REPLY)
    await scenario.step(
        "Завершите задачу с ответом покупателю",
        page,
        screenshot_name="customer-chat-resumed",
        label_en="Complete the task with a customer reply",
        details=(
            "**Демонстрация результата.** Закройте задачу с текстом ответа. В чате "
            "покупателя появляется сообщение Марины из поддержки — агент продолжает "
            "диалог с учётом ответа оператора.\n\n"
            "**Итог.** Теперь вы знаете путь задачи: из чата агента во входящие, взять, "
            "ответить один раз и вернуть результат покупателю."
        ),
        details_en=(
            "**Result demonstration.** Close the task with the reply text. Marina's support "
            "message appears in the customer chat; the agent continues with the operator "
            "answer.\n\n"
            "**Summary.** You now know the task path: from agent chat to inbox, claim, "
            "reply once, and return the result to the customer."
        ),
    )
    _ = GREEN_GARDEN_OPERATOR


@pytest.mark.scenario(
    service="worktracker",
    tag="operators",
    doc_slug="operator-takeover-dialog",
    title="Оператор ведёт живой диалог с покупателем",
    description=(
        "**Для чего:** эта инструкция покажет режим «перехват диалога», когда оператору "
        "Марине нужен не один ответ, а переписка с покупателем.\n\n"
        "**Какие проблемы решает:** по спорному возврату одного сообщения мало — нужно "
        "уточнять детали в живом диалоге.\n\n"
        "**Результат:** Марина ведёт переписку в задаче, завершает её — агент подхватывает "
        "итог и продолжает с покупателем."
    ),
    title_en="Operator takes over the live dialog",
    description_en=(
        "**What for:** this guide shows dialog takeover mode when operator Marina needs "
        "a conversation, not a single reply.\n\n"
        "**Problems it solves:** for a disputed return one message is not enough; details "
        "must be clarified in a live dialog.\n\n"
        "**Result:** Marina chats in the task, completes it, and the agent picks up the "
        "outcome and continues with the customer."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_worktracker_operator_takeover_dialog(
    scenario: ScenarioRecorder,
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
    page = ui_page_system
    await flows_open_chat_page(page, flows_ui, EXAMPLE_GRAPH_ID)
    work_item_id = await hitl_trigger_deterministic(page, GREEN_GARDEN_TAKEOVER_MESSAGE)

    wt_page = await page.context.new_page()
    try:
        await worktracker_open_task_page(wt_page, worktracker_ui, work_item_id)
        editor = wt_page.locator(
            f"work-item-detail-editor[work-item-id='{work_item_id}']"
        ).first
        await scenario.step(
            "Откройте задачу режима перехвата",
            wt_page,
            screenshot_name="takeover-task-opened",
            label_en="Open the takeover-mode task",
            details=(
                "В чате демо-агента напишите «перехват» — создаётся задача с полным перехватом "
                "диалога. Откройте её в разделе задач: Марина видит контекст спорного возврата."
            ),
            details_en=(
                "In the demo agent chat, type takeover trigger text; a full dialog takeover "
                "task is created. Open it in tasks; Marina sees the disputed return context."
            ),
        )

        await worktracker_claim_task(wt_page, editor)
        await worktracker_add_comment(wt_page, editor, OPERATOR_FOLLOWUP)
        await scenario.step(
            "Напишите покупателю уточняющий вопрос",
            wt_page,
            screenshot_name="operator-followup-sent",
            label_en="Send a follow-up question to the customer",
            details=(
                "Возьмите задачу и напишите уточняющий вопрос в ленте задачи. В режиме "
                "перехвата оператор ведёт живой диалог, а не ограничивается одним финальным "
                "ответом."
            ),
            details_en=(
                "Claim the task and write a follow-up in the task thread. In takeover mode the "
                "operator runs a live dialog instead of a single final reply."
            ),
        )

        takeover_resolution = (
            f"{GREEN_GARDEN_OPERATOR}: оформим возврат по фото и номеру заказа. "
            f"{OPERATOR_FOLLOWUP}"
        )
        await worktracker_api_complete_work_item(
            worktracker_ui.origin,
            auth_token_system,
            work_item_id,
            resolution_text=takeover_resolution,
        )
    finally:
        await wt_page.close()

    await hitl_wait_chat_resume(page, expect_operator_text=GREEN_GARDEN_OPERATOR)
    await scenario.step(
        "Завершите перехват с итогом диалога",
        page,
        screenshot_name="takeover-chat-resumed",
        label_en="Complete takeover with dialog outcome",
        details=(
            "**Демонстрация результата.** Закройте задачу с итогом переписки. В чате "
            "покупателя появляется ответ Марины — агент подхватывает весь диалог "
            "оператора и продолжает обслуживание.\n\n"
            "**Итог.** Теперь вы умеете отличать «один ответ» от «перехвата» и вести "
            "многошаговый разговор оператора с покупателем."
        ),
        details_en=(
            "**Result demonstration.** Close the task with the conversation outcome. "
            "Marina's reply appears in the customer chat; the agent picks up the full "
            "operator dialog and continues service.\n\n"
            "**Summary.** You can now tell single-reply from takeover and run a multi-step "
            "operator–customer conversation."
        ),
    )


@pytest.mark.scenario(
    service="worktracker",
    tag="operators",
    doc_slug="route-and-reassign-tasks",
    title="Маршрутизация и переназначение задач",
    description=(
        "**Для чего:** эта инструкция поможет направлять разные обращения в разные очереди "
        "и передавать задачу другому исполнителю.\n\n"
        "**Какие проблемы решает:** возвраты и общие вопросы смешиваются; иногда задачу "
        "нужно отдать коллеге в другую очередь.\n\n"
        "**Результат:** задача из «Поддержка клиентов» переназначена в очередь «Возвраты» "
        "для отдельной обработки."
    ),
    title_en="Route and reassign operator tasks",
    description_en=(
        "**What for:** this guide helps you route different requests to different queues "
        "and pass a task to another assignee.\n\n"
        "**Problems it solves:** returns and general questions get mixed; sometimes a task "
        "must go to a colleague in another queue.\n\n"
        "**Result:** a task from Customer Support is reassigned to the Returns queue for "
        "separate handling."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_worktracker_route_and_reassign_tasks(
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
    support_slug = flows_doc_flow_id("support", unique_id).replace("_", "-")
    returns_slug = flows_doc_flow_id("returns", unique_id).replace("_", "-")
    support_queue = await worktracker_api_create_queue(
        worktracker_ui.origin,
        auth_token_system,
        name=GREEN_GARDEN_SUPPORT_QUEUE,
        slug=support_slug,
    )
    returns_queue = await worktracker_api_create_queue(
        worktracker_ui.origin,
        auth_token_system,
        name=GREEN_GARDEN_RETURNS_QUEUE,
        slug=returns_slug,
    )
    support_queue_id = str(support_queue["work_queue_id"])
    returns_queue_id = str(returns_queue["work_queue_id"])

    page = ui_page_system
    await hitl_open_react_branch_chat(page, flows_ui, branch_id=HITL_BRANCH_NODE)
    work_item_id = await hitl_trigger_deterministic(page, GREEN_GARDEN_HITL_MESSAGE)

    await worktracker_open_queues(page, worktracker_ui)
    support_row = page.locator("worktracker-queues-page button.queue-row").filter(
        has_text=GREEN_GARDEN_SUPPORT_QUEUE
    ).first
    returns_row = page.locator("worktracker-queues-page button.queue-row").filter(
        has_text=GREEN_GARDEN_RETURNS_QUEUE
    ).first
    await expect(support_row).to_be_visible(timeout=30_000)
    await expect(returns_row).to_be_visible(timeout=30_000)
    await scenario.step(
        "Создайте очереди поддержки и возвратов",
        page,
        screenshot_name="two-queues-created",
        label_en="Create support and returns queues",
        details=(
            "В разделе очередей видны «Поддержка клиентов» и «Возвраты». Разные типы "
            "обращений можно направлять в разные ящики, чтобы операторы не смешивали "
            "общие вопросы и спорные возвраты."
        ),
        details_en=(
            "The queues section shows Customer Support and Returns. Different request types "
            "can go to different inboxes so operators do not mix general questions and "
            "disputed returns."
        ),
    )

    await worktracker_api_reassign_work_item(
        worktracker_ui.origin,
        auth_token_system,
        work_item_id,
        {"assignee_kind": "queue", "work_queue_id": returns_queue_id},
    )
    await worktracker_open_task_page(page, worktracker_ui, work_item_id)
    editor = page.locator(f"work-item-detail-editor[work-item-id='{work_item_id}']").first
    await expect(editor).to_be_visible(timeout=30_000)
    await expect(editor).to_contain_text(GREEN_GARDEN_RETURNS_QUEUE, timeout=30_000)
    await scenario.step(
        "Переназначьте задачу в очередь возвратов",
        page,
        screenshot_name="task-reassigned-to-returns",
        label_en="Reassign the task to the returns queue",
        details=(
            "**Демонстрация результата.** Откройте задачу после переназначения — она "
            "теперь в очереди «Возвраты». Марина или коллега из этой очереди увидят её "
            "во входящих и смогут обработать отдельно от общей поддержки.\n\n"
            "**Итог.** Теперь вы умеете маршрутизировать задачи агента между очередями "
            "«Поддержка клиентов» и «Возвраты»."
        ),
        details_en=(
            "**Result demonstration.** Open the task after reassignment; it is now in the "
            "Returns queue. Marina or a colleague in that queue will see it in inbox and "
            "handle it separately from general support.\n\n"
            "**Summary.** You can now route agent tasks between Customer Support and "
            "Returns queues."
        ),
    )
    _ = support_queue_id


@pytest.mark.scenario(
    service="worktracker",
    tag="operators",
    doc_slug="track-work-on-board",
    title="Ведём задачи на доске",
    description=(
        "**Для чего:** эта инструкция поможет держать поток обращений под контролем на "
        "канбан-доске, а не только списком входящих.\n\n"
        "**Какие проблемы решает:** список входящих не показывает общий статус всех задач "
        "от агента и операторов.\n\n"
        "**Результат:** на доске видно задачи в колонках «К выполнению» и «В работе»."
    ),
    title_en="Track operator work on a board",
    description_en=(
        "**What for:** this guide helps you keep the request flow under control on a kanban "
        "board, not only as an inbox list.\n\n"
        "**Problems it solves:** the inbox list does not show the overall status of all "
        "agent and operator tasks.\n\n"
        "**Result:** the board shows tasks in To do and In progress columns."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_worktracker_track_work_on_board(
    scenario: ScenarioRecorder,
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
    board_name = f"Поток поддержки ({unique_id})"
    board = await worktracker_api_create_board(
        worktracker_ui.origin,
        auth_token_system,
        name=board_name,
    )
    board_id = str(board["board_id"])
    task_title = f"Проверить остаток саженцев ({unique_id})"
    await worktracker_api_create_work_item(
        worktracker_ui.origin,
        auth_token_system,
        {
            "title": task_title,
            "description": "Фоновое поручение от агента «Зелёного сада»",
            "kind": "generic",
            "board_id": board_id,
            "board_column_id": "todo",
        },
    )

    page = ui_page_system
    await page.goto(
        f"{worktracker_ui.origin}/worktracker/board?board_id={board_id}",
        wait_until="domcontentloaded",
    )
    await expect(page.locator("worktracker-board-page")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте канбан-доску задач",
        page,
        screenshot_name="board-opened",
        label_en="Open the tasks kanban board",
        details=(
            "В разделе задач откройте доску. Колонки показывают этапы работы: что ждёт "
            "выполнения, что уже в работе у операторов вроде Марины."
        ),
        details_en=(
            "In tasks, open the board. Columns show work stages: what is waiting and what "
            "operators such as Marina are already working on."
        ),
    )

    card = page.locator("worktracker-work-item-card").filter(has_text=task_title).first
    await expect(card).to_be_visible(timeout=60_000)
    await scenario.step(
        "Найдите задачу агента на доске",
        page,
        screenshot_name="task-on-board",
        label_en="Find the agent task on the board",
        details=(
            "**Демонстрация результата.** Карточка поручения от «Помощника Зелёного сада» "
            "лежит в колонке «К выполнению». С доски видно весь поток, а не только "
            "последнее входящее.\n\n"
            "**Итог.** Теперь вы умеете смотреть задачи агента и операторов на канбан-доске "
            "и контролировать статус потока поддержки."
        ),
        details_en=(
            "**Result demonstration.** The Green Garden Assistant task card sits in the To do "
            "column. The board shows the whole flow, not only the latest inbox item.\n\n"
            "**Summary.** You can now view agent and operator tasks on the kanban board and "
            "control support flow status."
        ),
    )
    _ = GREEN_GARDEN_OPERATOR
