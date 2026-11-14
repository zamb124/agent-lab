"""Документационный сценарий RAG: страница «Настройки».

L3-маршрут: секция провайдеров показывает, какой backend хранит
векторы документов и какой из них выбран по умолчанию.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="rag",
    tag="settings",
    doc_slug="rag-settings",
    title="Настройки RAG: провайдеры поиска",
    title_en="RAG settings: search providers",
    description=(
        "**Для чего:** посмотреть, какой движок хранит векторы "
        "документов и используется для умного поиска.\n\n"
        "**Какие проблемы решает:** когда поиск работает не так, "
        "первым делом проверяют активный провайдер — он показан "
        "на странице настроек.\n\n"
        "**Результат:** карточки провайдеров с отметками «активен» "
        "и «по умолчанию»."
    ),
    description_en=(
        "**Purpose:** see which engine stores document vectors and "
        "powers semantic search.\n\n"
        "**Problems solved:** when search behaves unexpectedly, the "
        "active provider is the first thing to check — it is shown "
        "on the settings page.\n\n"
        "**Result:** provider cards with «active» and «default» "
        "badges."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_rag_settings_providers(
    scenario: ScenarioRecorder,
    rag_ui: AppUI,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await rag_ui.open(page)
    await rag_ui.expect_shell(page)

    item = page.locator("rag-sidebar .nav-item").nth(2)
    await expect(item).to_be_visible(timeout=10_000)
    await item.click()
    await expect(page.locator("rag-settings-page")).to_be_visible(timeout=15_000)

    cards = page.locator("rag-settings-page provider-selector .card")
    await expect(cards.first).to_be_visible(timeout=30_000)
    await expect(
        page.locator("rag-settings-page provider-selector .badge.active").first
    ).to_be_visible(timeout=10_000)
    await scenario.step(
        "Откройте «Настройки» и найдите активного провайдера",
        page,
        screenshot_name="settings-providers",
        label_en="Open «Settings» and find the active provider",
        details=(
            "В меню слева выберите «Настройки». В секции «Провайдеры» "
            "карточки показывают движки, которые хранят векторы "
            "документов. Подсвеченная карточка с отметкой «активен» — "
            "тот движок, который сейчас отвечает на поисковые запросы; "
            "отметка «по умолчанию» — провайдер, выбранный "
            "в конфигурации."
        ),
        details_en=(
            "Choose «Settings» in the left menu. The «Providers» "
            "section lists engines that store document vectors. The "
            "highlighted card with an «active» badge is the engine "
            "currently answering search queries; the «default» badge "
            "marks the provider chosen in configuration."
        ),
    )

    info = page.locator("rag-settings-page .info-box")
    await expect(info).to_be_visible(timeout=10_000)
    await scenario.step(
        "Прочитайте, как работает поиск",
        page,
        screenshot_name="settings-about",
        label_en="Read how the search works",
        details=(
            "Ниже — блок «О RAG Service»: он коротко объясняет "
            "устройство умного поиска. Документы разбиваются на "
            "фрагменты, превращаются в векторы и сохраняются — "
            "поэтому поиск находит по смыслу, а не по точным словам.\n\n"
            "**Итог.** На странице настроек видно, какой провайдер "
            "обслуживает поиск, и как устроена индексация документов."
        ),
        details_en=(
            "Below is the «About RAG Service» box: it briefly explains "
            "how semantic search works. Documents are split into "
            "chunks, turned into vectors and stored — that is why "
            "search works by meaning, not exact words.\n\n"
            "**Summary.** The settings page shows which provider "
            "serves search and how document indexing works."
        ),
    )
