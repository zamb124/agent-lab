"""Playwright E2E: бейдж flow-сотрудника на странице команды."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from core.identity.flow_employee import flow_employee_user_id
from tests.ui.e2e.flows_e2e_helpers import flows_api_create_flow, flows_api_delete_flow
from tests.ui.harness import AppUI

_NODES = {"main": {"type": "llm_node", "prompt": "hi"}}


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_team_page_shows_flow_employee_badge(
    flows_service,
    frontend_service,
    frontend_ui: AppUI,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    system_user_id: str,
    unique_id: str,
) -> None:
    _ = flows_service, frontend_service
    flow_id = f"ui_emp_{unique_id}"
    emp_id = flow_employee_user_id(flow_id)

    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        {
            "flow_id": flow_id,
            "name": "UI Employee",
            "entry": "main",
            "nodes": _NODES,
            "edges": [],
            "employee": {
                "enabled": True,
                "roles": ["member"],
                "curator_user_ids": [system_user_id],
            },
        },
    )
    try:
        await frontend_ui.open(ui_page_system)
        await frontend_ui.expect_shell(ui_page_system)
        await ui_page_system.goto(f"{frontend_ui.origin}/team", wait_until="domcontentloaded")
        await expect(ui_page_system.locator("frontend-team-page")).to_be_visible(timeout=30_000)

        employee_row = ui_page_system.locator("frontend-team-page").locator(
            "platform-user-chip"
        ).filter(has=ui_page_system.locator(f'[user-id="{emp_id}"]'))
        await expect(employee_row.first).to_be_visible(timeout=30_000)

        badge = ui_page_system.locator("frontend-team-page .role-tag").filter(
            has_text=re.compile(r"AI employee|AI-сотрудник")
        )
        await expect(badge.first).to_be_visible(timeout=15_000)
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)
