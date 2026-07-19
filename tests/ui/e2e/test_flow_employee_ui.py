"""UI E2E: бейдж flow-сотрудника на странице команды (scenario)."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from core.identity.flow_employee import flow_employee_user_id
from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    flows_api_create_flow,
    flows_api_delete_flow,
    flows_doc_flow_id,
    flows_open_editor,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="operations",
    doc_slug="enable-flow-employee",
    title="Включаем агента как AI-сотрудника",
    description=(
        "**Для чего:** эта инструкция покажет, как агент появляется в команде компании "
        "как AI-сотрудник.\n\n"
        "**Какие проблемы решает:** непонятно, где увидеть, что flow работает как "
        "участник команды, а не только как чат-бот.\n\n"
        "**Результат:** на странице команды виден бейдж AI-сотрудника у помощника "
        "«Зелёного сада»."
    ),
    title_en="Enable the agent as an AI employee",
    description_en=(
        "**What for:** this guide shows how an agent appears on the company team as an "
        "AI employee.\n\n"
        "**Problems it solves:** it is unclear where to see that a flow is a team member, "
        "not only a chat bot.\n\n"
        "**Result:** the team page shows an AI employee badge for the Green Garden "
        "assistant."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_enable_flow_employee(
    scenario: ScenarioRecorder,
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
    flow_id = flows_doc_flow_id("flow_emp", unique_id)
    emp_id = flow_employee_user_id(flow_id)

    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        {
            "flow_id": flow_id,
            "name": GREEN_GARDEN_AGENT_NAME,
            "entry": "main",
            "nodes": {"main": {"type": "llm_node", "prompt": "Помогай команде магазина."}},
            "edges": [],
            "employee": {
                "enabled": True,
                "roles": ["member"],
                "curator_user_ids": [system_user_id],
            },
        },
    )
    page = ui_page_system
    try:
        await flows_open_editor(page, flows_ui, flow_id, layout="agent")
        await scenario.step(
            "Откройте опубликованного агента-сотрудника",
            page,
            screenshot_name="employee-agent-in-editor",
            label_en="Open the employee agent in the editor",
            details=(
                "Откройте «Помощника Зелёного сада» в редакторе. Когда агент включён как "
                "сотрудник компании, он получает учётную запись в команде."
            ),
            details_en=(
                "Open the Green Garden Assistant in the editor. When the agent is enabled "
                "as a company employee, it gets a team account."
            ),
        )

        await frontend_ui.open(page)
        await frontend_ui.expect_shell(page)
        await scenario.step(
            "Перейдите в раздел команды",
            page,
            screenshot_name="team-page-opened",
            label_en="Go to the team section",
            details=(
                "Откройте страницу команды компании. Здесь перечислены люди и "
                "AI-сотрудники."
            ),
            details_en=(
                "Open the company team page. People and AI employees are listed here."
            ),
        )

        await page.goto(f"{frontend_ui.origin}/team", wait_until="domcontentloaded")
        await expect(page.locator("frontend-team-page")).to_be_visible(timeout=30_000)
        employee_chip = page.locator(
            f'frontend-team-page platform-user-chip[user-id="{emp_id}"]'
        ).first
        await expect(employee_chip).to_be_visible(timeout=30_000)
        await scenario.step(
            "Найдите AI-сотрудника в списке",
            page,
            screenshot_name="employee-row-visible",
            label_en="Find the AI employee in the list",
            details=(
                "В списке команды найдите запись помощника. У AI-сотрудника отдельная "
                "карточка участника."
            ),
            details_en=(
                "In the team list find the assistant entry. An AI employee has its own "
                "member card."
            ),
        )

        badge = page.locator("frontend-team-page .role-tag").filter(
            has_text=re.compile(r"AI employee|AI-сотрудник")
        )
        await expect(badge.first).to_be_visible(timeout=15_000)
        await scenario.step(
            "Убедитесь в бейдже AI-сотрудника",
            page,
            screenshot_name="ai-employee-badge",
            label_en="Confirm the AI employee badge",
            details=(
                "**Демонстрация результата.** Рядом с участником виден бейдж "
                "«AI-сотрудник» — агент состоит в команде.\n\n"
                "**Итог.** Вы понимаете, как агент-сотрудник отображается на странице "
                "команды."
            ),
            details_en=(
                "**Result demonstration.** Next to the member you see the AI employee "
                "badge — the agent is on the team.\n\n"
                "**Summary.** You understand how an employee agent appears on the team "
                "page."
            ),
        )
    finally:
        await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)
