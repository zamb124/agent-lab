"""Документационный сценарий frontend: обзорный тур по консоли компании.

Первый экран, который видит сотрудник после входа: дашборд с карточками
приложений, страница команды и быстрые действия. Маршрут — чистая навигация
по живому UI без подготовки данных.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="frontend",
    tag="getting-started",
    doc_slug="dashboard-tour",
    title="Первый взгляд на консоль: дашборд, команда, приложения",
    title_en="First look at the console: dashboard, team, apps",
    description=(
        "**Для чего:** первый вход в рабочее место компании — за пять минут "
        "понять, где что находится и с чего начать работу.\n\n"
        "**Какие проблемы решает:** вы узнаете, что показывает дашборд, где "
        "список коллег и где каталог приложений компании — магазин, склад, "
        "чаты, документы и другие.\n\n"
        "**Результат:** вы ориентируетесь в консоли и знаете, как открыть "
        "нужное приложение."
    ),
    description_en=(
        "**Purpose:** your first sign-in to the company workspace — learn "
        "in five minutes where things are and where to start.\n\n"
        "**Problems solved:** you will know what the dashboard shows, where "
        "the colleagues list lives, and where the company app catalog is — "
        "shop, warehouse, chats, documents and more.\n\n"
        "**Result:** you can navigate the console and open the app you need."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_frontend_dashboard_tour(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    await frontend_ui.expect_shell(page)

    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("dashboard-page")).to_be_visible(timeout=30_000)
    await expect(page.locator("dashboard-services-grid")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте консоль — вы на дашборде",
        page,
        screenshot_name="dashboard-home",
        label_en="Open the console — the dashboard",
        details=(
            "После входа вы попадаете на дашборд — главный экран компании. "
            "Сверху приветствие и сводка, ниже — карточки всех приложений, "
            "к которым у компании есть доступ, и панель быстрых действий."
        ),
        details_en=(
            "After sign-in you land on the dashboard — the company's main "
            "screen. On top are a greeting and a summary, below are cards "
            "of all apps available to the company and a quick-actions bar."
        ),
    )

    await page.goto(f"{frontend_ui.origin}/team", wait_until="domcontentloaded")
    await expect(page.locator("frontend-team-page")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Посмотрите страницу «Команда»",
        page,
        screenshot_name="team-page",
        label_en="See the Team page",
        details=(
            "В разделе «Команда» собраны все сотрудники компании: кто "
            "работает, какие у них роли и права. Отсюда же приглашают "
            "новых коллег по ссылке."
        ),
        details_en=(
            "The «Team» section lists all company members: who works here, "
            "their roles and permissions. New colleagues are also invited "
            "from here via a link."
        ),
    )

    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("dashboard-services-grid")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Найдите нужное приложение в каталоге",
        page,
        screenshot_name="services-grid",
        label_en="Find the app you need in the catalog",
        details=(
            "Вернитесь на дашборд: плитки — это приложения компании. Чат, "
            "документы, база знаний, магазин, склад — каждая плитка ведёт в "
            "свой раздел. Кликните по нужной, чтобы начать работу."
        ),
        details_en=(
            "Back on the dashboard: the tiles are the company's apps. Chat, "
            "documents, knowledge base, shop, warehouse — each tile opens "
            "its own section. Click the one you need to start working."
        ),
    )

    await scenario.step(
        "Запомните панель быстрых действий",
        page,
        screenshot_name="quick-actions",
        label_en="Remember the quick-actions bar",
        details=(
            "**Демонстрация результата.** Внизу дашборда — быстрые "
            "действия: то, что делают чаще всего, доступно в один клик без "
            "поиска по меню.\n\n"
            "**Итог.** Вы знаете карту консоли: дашборд — старт и каталог "
            "приложений, «Команда» — коллеги и приглашения, быстрые "
            "действия — частые задачи."
        ),
        details_en=(
            "**Result demonstration.** At the bottom of the dashboard are "
            "quick actions: the most common tasks are one click away, no "
            "menu digging needed.\n\n"
            "**Summary.** You know the console map: dashboard — start and "
            "app catalog, «Team» — colleagues and invites, quick actions — "
            "frequent tasks."
        ),
    )
