"""Дымовые E2E: shell каждого Lit-SPA при поднятых session-сервисах."""

from __future__ import annotations

import pytest
from playwright.async_api import Page

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    title="Flows: оболочка example_react",
    description="Проверка отображения flows-app на демо-маршруте после авторизации.",
)
@pytest.mark.scenario_tag("flows")
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_flows_shell_loads(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await flows_ui.open(ui_page_system)
    await scenario.step("SPA Flows открыт", ui_page_system)
    await flows_ui.expect_shell(ui_page_system)
    await scenario.step("Оболочка flows-app видна", ui_page_system)


@pytest.mark.scenario(
    title="RAG: оболочка сервиса",
    description="Доступ к RAG UI на system.localhost после входа и маппинга субдомена.",
)
@pytest.mark.scenario_tag("rag")
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_rag_shell_loads(
    scenario: ScenarioRecorder,
    rag_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await rag_ui.open(ui_page_system)
    await scenario.step("SPA RAG открыт", ui_page_system)
    await rag_ui.expect_shell(ui_page_system)
    await scenario.step("Оболочка rag-app видна", ui_page_system)


@pytest.mark.scenario(
    title="CRM: оболочка записной книжки",
    description="Доступ к CRM UI на system.localhost после входа.",
)
@pytest.mark.scenario_tag("crm")
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_crm_shell_loads(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await crm_ui.open(ui_page_system)
    await scenario.step("SPA CRM открыт", ui_page_system)
    await crm_ui.expect_shell(ui_page_system)
    await scenario.step("Оболочка crm-app видна", ui_page_system)


@pytest.mark.scenario(
    title="Frontend: корневая оболочка платформы",
    description="Главная оболочка Humanitec на порту frontend-сервиса.",
)
@pytest.mark.scenario_tag("frontend")
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_frontend_shell_loads(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await frontend_ui.open(ui_page_system)
    await scenario.step("Корневой SPA открыт", ui_page_system)
    await frontend_ui.expect_shell(ui_page_system)
    await scenario.step("Оболочка frontend-app видна", ui_page_system)
