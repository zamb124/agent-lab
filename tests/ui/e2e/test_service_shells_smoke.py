"""Дымовые E2E: shell каждого Lit-SPA при поднятых session-сервисах."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="rag",
    doc_slug="rag-shell",
    title="RAG: оболочка сервиса",
    description="Доступ к RAG UI на system.localhost после входа и маппинга субдомена.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
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
    service="crm",
    doc_slug="crm-shell",
    title="NetWorkle: оболочка записной книжки",
    description="Доступ к NetWorkle UI на system.localhost после входа.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_crm_shell_loads(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await crm_ui.open(ui_page_system)
    await scenario.step("SPA NetWorkle открыт", ui_page_system)
    await crm_ui.expect_shell(ui_page_system)
    await scenario.step("Оболочка NetWorkle видна", ui_page_system)


@pytest.mark.scenario(
    service="crm",
    doc_slug="crm-settings-hub",
    title="NetWorkle: хаб настроек",
    description="Переход на /crm/settings и проверка отображения settings-hub-page с карточками.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_crm_settings_hub_loads(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await ui_page_system.goto(f"{crm_ui.origin}/crm/settings", wait_until="domcontentloaded")
    await scenario.step("Открыт раздел настроек NetWorkle", ui_page_system)
    await expect(ui_page_system.locator("crm-app")).to_be_visible(timeout=30_000)
    hub = ui_page_system.locator("crm-settings-hub-page")
    await expect(hub).to_be_visible(timeout=30_000)
    await expect(
        hub.get_by_text(re.compile(r"Настройки NetWorkle|NetWorkle settings"))
    ).to_be_visible(timeout=30_000)
    await expect(
        hub.get_by_text(re.compile(r"Шаблоны пространств|Namespace templates"))
    ).to_be_visible(timeout=30_000)
    await expect(
        hub.get_by_text(re.compile(r"Пространства|Namespaces"))
    ).to_be_visible(timeout=30_000)
    await scenario.step("Хаб настроек NetWorkle отображен с карточками", ui_page_system)


@pytest.mark.scenario(
    service="frontend",
    doc_slug="frontend-shell",
    title="Frontend: корневая оболочка платформы",
    description="Главная оболочка Humanitec на порту frontend-сервиса.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_frontend_shell_loads(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await frontend_ui.open(ui_page_system)
    await scenario.step("Корневой SPA открыт", ui_page_system)
    await frontend_ui.expect_shell(ui_page_system)
    await scenario.step("Оболочка frontend-app видна", ui_page_system)
