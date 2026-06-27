"""Playwright E2E: CTA «Скачать HumanitecAgent» на лендинге и в Flows home."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="frontend",
    tag="agent-download",
    doc_slug="landing-hero-download-link",
    title="Frontend: ссылка на скачивание HumanitecAgent в hero лендинга",
    description="На главной странице есть floating-карточка со ссылкой на /agent.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_landing_hero_agent_download_link(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_anonymous: Page,
) -> None:
    page = ui_page_anonymous
    await page.goto(f"{frontend_ui.origin}/", wait_until="domcontentloaded")
    await expect(page.locator("frontend-app")).to_be_visible(timeout=30_000)
    download_link = page.locator('landing-agent-download-card a[href="/agent"]')
    await expect(download_link).to_be_visible(timeout=30_000)
    await expect(
        download_link.filter(
            has_text=re.compile(r"Скачать HumanitecAgent|Download HumanitecAgent")
        )
    ).to_be_visible(timeout=30_000)
    await scenario.step("Floating-карточка download page видна на лендинге", page)


@pytest.mark.scenario(
    service="flows",
    tag="agent-download",
    doc_slug="flows-home-download-link",
    title="Flows: ссылка на скачивание HumanitecAgent на главной",
    description="На flows home в hero actions есть ссылка с href, содержащим /agent.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_home_agent_download_link(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("flows-home-page")).to_be_visible(timeout=30_000)
    download_link = page.locator('flows-home-page a.text-action[href*="/agent"]')
    await expect(download_link).to_be_visible(timeout=30_000)
    await expect(
        download_link.filter(
            has_text=re.compile(r"Скачать HumanitecAgent|Download HumanitecAgent")
        )
    ).to_be_visible(timeout=30_000)
    href = await download_link.get_attribute("href")
    assert href is not None
    assert "/agent" in href
    await scenario.step("Ссылка на download page видна на flows home", page)
