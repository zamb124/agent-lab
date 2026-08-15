"""Playwright E2E: Access Explorer в консоли frontend."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzRelation
from tests.ui.e2e_worker import ui_e2e_company_id
from tests.ui.harness import AppUI
from tests.ui.personas import UiTestUser

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_console_access_admin_sees_human_grant_and_why(
    frontend_ui: AppUI,
    ui_page_system: Page,
    ui_user_system: UiTestUser,
    frontend_container,
    unique_id: str,
) -> None:
    user_id = ui_user_system.user_id
    if user_id is None or user_id == "":
        raise AssertionError("ui_user_system.user_id required")
    company_id = ui_e2e_company_id()
    namespace = f"accessws_{unique_id}"
    obj = AuthzObject.platform_namespace(company_id, namespace)
    await frontend_container.authz_service.write(
        [
            AuthzTuple(
                subject=AuthzSubject.user(user_id),
                relation=AuthzRelation.VIEWER,
                obj=obj,
            )
        ]
    )

    await frontend_ui.open(ui_page_system)
    await frontend_ui.expect_shell(ui_page_system)
    await ui_page_system.goto(
        f"{frontend_ui.origin}/access",
        wait_until="domcontentloaded",
    )
    page_root = ui_page_system.locator("frontend-access-page")
    await expect(page_root).to_be_visible(timeout=30_000)
    member_row = page_root.locator(".picker-item").filter(
        has=ui_page_system.locator(f"platform-user-chip[user-id='{user_id}']")
    )
    await expect(member_row).to_be_visible(timeout=20_000)
    await member_row.click()
    grant_title = page_root.locator(".grant-title").filter(has_text=namespace)
    await expect(grant_title).to_be_visible(timeout=20_000)
    grant_text = await grant_title.inner_text()
    if user_id in grant_text:
        raise AssertionError(f"grant title must not be raw user_id: {grant_text}")
    if obj.object_key in grant_text:
        raise AssertionError(f"grant title must not be raw object key: {grant_text}")
    await page_root.locator(".grant-row").filter(has_text=namespace).click()
    why = page_root.locator(".why-drawer")
    await expect(why).to_be_visible(timeout=15_000)
    why_text = await why.inner_text()
    if "#" in why_text:
        raise AssertionError(f"why text must not contain FGA #: {why_text}")
    if "union" in why_text.lower():
        raise AssertionError(f"why text must not contain union: {why_text}")
    await expect(why).to_contain_text(
        re.compile(r"Выдан напрямую|Granted directly")
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_console_access_member_sees_forbidden(
    frontend_ui: AppUI,
    ui_page_system_member: Page,
) -> None:
    await frontend_ui.open(ui_page_system_member)
    await frontend_ui.expect_shell(ui_page_system_member)
    await ui_page_system_member.goto(
        f"{frontend_ui.origin}/access",
        wait_until="domcontentloaded",
    )
    page_root = ui_page_system_member.locator("frontend-access-page")
    await expect(page_root).to_be_visible(timeout=30_000)
    await expect(page_root.locator(".forbidden .empty-title")).to_contain_text(
        re.compile(r"Недостаточно прав|Not enough permissions")
    )
    await expect(page_root.locator(".picker-item")).to_have_count(0)
