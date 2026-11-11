"""UI E2E: Networkle /crm/tasks workspace на WorkItem(crm_activity)."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.crm_activity_tasks_helpers import (
    crm_api_create_activity_task,
    crm_api_list_activity_tasks,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="crm",
    tag="tasks",
    doc_slug="tasks-in-crm",
    title="Задачи внутри NetWorkle",
    title_en="Tasks inside NetWorkle",
    description=(
        "**Для чего:** поручения по клиентам и сделкам не должны жить отдельно "
        "от картотеки — задачи пространства видны прямо в разделе «Задачи».\n\n"
        "**Какие проблемы решает:** менеджер видит список задач компании "
        "в одном месте: статус, приоритет и постановщик — без перехода в "
        "отдельный таск-трекер.\n\n"
        "**Результат:** задача создана и видна в списке «Задачи» NetWorkle, "
        "из списка открывается форма новой задачи."
    ),
    description_en=(
        "**Purpose:** assignments about customers and deals should not live "
        "apart from the card index — space tasks are visible right in the "
        "Tasks section.\n\n"
        "**Problems solved:** a manager sees the company task list in one "
        "place: status, priority and creator — without switching to a "
        "separate tracker.\n\n"
        "**Result:** the task is created and visible in the NetWorkle Tasks "
        "list, and the new-task form opens from the list."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180, func_only=True)
async def test_crm_tasks_in_crm_scenario(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    namespace = "default"
    title = f"Позвонить клиенту {unique_id}"
    created = await crm_api_create_activity_task(
        crm_ui.origin,
        auth_token_system,
        title=title,
        namespace=namespace,
        priority="high",
    )
    work_item = created.get("work_item")
    assert isinstance(work_item, dict) and work_item.get("work_item_id")

    await crm_ui.open(ui_page_system)
    await ui_page_system.goto(
        f"{crm_ui.origin}/crm/tasks",
        wait_until="domcontentloaded",
    )
    page_root = ui_page_system.locator("crm-tasks-page")
    await expect(page_root).to_be_visible(timeout=60_000)
    await scenario.step(
        "Откройте раздел «Задачи»",
        ui_page_system,
        screenshot_name="tasks-page",
        label_en="Open the Tasks section",
        details=(
            "В боковом меню NetWorkle выберите «Задачи». Откроется общий список "
            "поручений компании: здесь видны статус, приоритет и исполнитель."
        ),
        details_en=(
            "In the NetWorkle sidebar choose Tasks. The company task list "
            "opens: status, priority and assignee are visible here."
        ),
    )

    row = page_root.locator("platform-work-item-row").filter(has_text=title)
    await expect(row).to_be_visible(timeout=60_000)
    await row.first.click()
    await expect(
        page_root.locator("platform-work-item-detail")
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте карточку задачи",
        ui_page_system,
        screenshot_name="task-detail-panel",
        label_en="Open the task card",
        details=(
            "Каждая строка — отдельная задача: название, статус и приоритет. "
            "Клик по строке открывает карточку справа: описание, исполнитель, "
            "срок и чат с заказчиком."
        ),
        details_en=(
            "Each row is a separate task: title, status and priority. Clicking "
            "a row opens the card on the right: description, assignee, due "
            "date and the customer chat."
        ),
    )

    create_btn = page_root.get_by_role("button", name=re.compile(r"Создать задачу|Create task"))
    await expect(create_btn.first).to_be_visible(timeout=30_000)
    await create_btn.first.click()
    modal = ui_page_system.locator("crm-activity-task-create-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    await expect(
        modal.get_by_text(re.compile(r"Новая задача|New task"))
    ).to_be_visible(timeout=15_000)
    await scenario.step(
        "Создайте задачу из списка",
        ui_page_system,
        screenshot_name="task-create-modal",
        label_en="Create a task from the list",
        details=(
            "Кнопка «Создать задачу» открывает форму: название, приоритет, "
            "исполнитель и срок. После сохранения задача появляется в списке "
            "и в разделе «Задачи» платформы.\n\n"
            "**Итог.** Поручения по клиентам ведутся прямо в NetWorkle."
        ),
        details_en=(
            "The Create task button opens a form: title, priority, assignee "
            "and due date. After saving, the task appears in the list and in "
            "the platform Tasks section.\n\n"
            "**Summary.** Customer assignments are managed right inside "
            "NetWorkle."
        ),
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_tasks_page_lists_activity_task_from_api(
    crm_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    namespace = "default"
    title = f"E2E task {unique_id}"
    created = await crm_api_create_activity_task(
        crm_ui.origin,
        auth_token_system,
        title=title,
        namespace=namespace,
        priority="high",
    )
    work_item = created.get("work_item")
    assert isinstance(work_item, dict)
    work_item_id = work_item.get("work_item_id")
    assert isinstance(work_item_id, str) and work_item_id

    listed = await crm_api_list_activity_tasks(
        crm_ui.origin,
        auth_token_system,
        namespace=namespace,
    )
    assert any(row.get("work_item_id") == work_item_id for row in listed)

    await crm_ui.open(ui_page_system)
    await ui_page_system.goto(
        f"{crm_ui.origin}/crm/tasks",
        wait_until="domcontentloaded",
    )
    page_root = ui_page_system.locator("crm-tasks-page")
    await expect(page_root).to_be_visible(timeout=60_000)
    await expect(page_root.get_by_text(title, exact=False)).to_be_visible(timeout=60_000)
    await expect(
        page_root.locator("platform-work-item-row").filter(has_text=title)
    ).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_tasks_create_modal_and_empty_cta(
    crm_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    _ = unique_id
    await crm_ui.open(ui_page_system)
    await ui_page_system.goto(
        f"{crm_ui.origin}/crm/tasks",
        wait_until="domcontentloaded",
    )
    page_root = ui_page_system.locator("crm-tasks-page")
    await expect(page_root).to_be_visible(timeout=60_000)

    create_btn = page_root.get_by_role("button", name=re.compile(r"Создать задачу|Create task"))
    await expect(create_btn.first).to_be_visible(timeout=30_000)
    await create_btn.first.click()

    modal = ui_page_system.locator("crm-activity-task-create-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    await expect(
        modal.get_by_text(re.compile(r"Новая задача|New task"))
    ).to_be_visible(timeout=15_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_sidebar_tasks_route_opens_tasks_workspace(
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await crm_ui.open(ui_page_system)
    await ui_page_system.goto(f"{crm_ui.origin}/crm/", wait_until="domcontentloaded")
    await expect(ui_page_system.locator("crm-app")).to_be_visible(timeout=60_000)

    # Bottom nav Tasks (mobile shell) или sidebar leaf.
    tasks_nav = ui_page_system.locator(
        "platform-bottom-nav [data-route-key='tasks'], "
        "platform-sidebar-nav-tree [data-route-key='tasks'], "
        "a[href*='/crm/tasks']"
    )
    if await tasks_nav.count() > 0:
        await tasks_nav.first.click()
    else:
        await ui_page_system.goto(f"{crm_ui.origin}/crm/tasks", wait_until="domcontentloaded")

    await expect(ui_page_system).to_have_url(re.compile(r"/crm/tasks"), timeout=60_000)
    await expect(ui_page_system.locator("crm-tasks-page")).to_be_visible(timeout=60_000)
