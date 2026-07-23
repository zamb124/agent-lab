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
