"""Generated documentation scenarios for basic platform onboarding."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import flows_company_origin
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


async def _close_modal(page: Page, selector: str) -> None:
    host = page.locator(selector).first
    if await host.count() == 0:
        return
    await host.evaluate(
        """
        (el) => {
            if (typeof el.close === 'function') el.close();
            else el.removeAttribute('open');
        }
        """
    )
    await expect(host).not_to_be_visible(timeout=10_000)


async def _open_user_menu(page: Page):
    button = page.locator("platform-user button.user-button").first
    await expect(button).to_be_visible(timeout=30_000)
    await button.click()
    menu = page.locator("platform-user .user-menu").first
    await expect(menu).to_be_visible(timeout=30_000)
    return menu


@pytest.mark.scenario(
    service="platform",
    tag="onboarding",
    doc_slug="main-dashboard-user-menu",
    title="Основные инструкции: вход, Dashboard и меню пользователя",
    description=(
        "Базовый маршрут для нового пользователя: открыть сайт, перейти в Dashboard, "
        "понять список сервисов и разобраться с пунктами меню пользователя."
    ),
    title_en="Platform basics: entry, Dashboard, and user menu",
    description_en=(
        "A basic path for a new user: open the website, go to Dashboard, "
        "understand the service list, and inspect the user menu."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_platform_main_dashboard_user_menu_scenario(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_company2: Page,
    _ui_subdomain_mappings,
) -> None:
    page = ui_page_company2
    company_origin = flows_company_origin(frontend_ui.origin)

    await page.goto(f"{company_origin}/", wait_until="domcontentloaded")
    await expect(page.locator("frontend-app")).to_be_visible(timeout=30_000)
    dashboard_link = page.locator("landing-header a.dashboard-btn").first
    await expect(dashboard_link).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открываем главный сайт. Если пользователь уже вошел, в шапке есть кнопка Dashboard.",
        page,
        label_en="Open the main website. If the user is signed in, the header has a Dashboard button.",
    )

    await dashboard_link.click()
    await expect(page).to_have_url(re.compile(r"/dashboard(?:$|[?#])"), timeout=30_000)
    await expect(page.locator("dashboard-page")).to_be_visible(timeout=30_000)
    await expect(page.locator("dashboard-service-card[svc-id='flows']")).to_be_visible(timeout=30_000)
    await expect(page.locator("dashboard-service-card[svc-id='crm']")).to_be_visible(timeout=30_000)
    await expect(page.locator("dashboard-service-card[svc-id='rag']")).to_be_visible(timeout=30_000)
    await expect(page.locator("dashboard-service-card[svc-id='sync']")).to_be_visible(timeout=30_000)
    await expect(page.locator("dashboard-service-card[svc-id='litserve']")).to_have_count(0)
    await expect(page.locator("dashboard-service-card[svc-id='grafana']")).to_have_count(0)
    await scenario.step(
        "Dashboard показывает основные сервисы компании. Системные сервисы здесь не показываются обычной компании.",
        page,
        label_en="Dashboard shows the company's main services. System-only services are hidden from a regular company.",
    )

    menu = await _open_user_menu(page)
    await expect(menu.locator("[data-menu-action='apps']")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='profile']")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='company-selector']")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='calendar']")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='documentation']")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='language']")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='theme']")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='logout']")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открываем меню пользователя. Здесь находятся сервисы, профиль, компания, календарь, документация, язык, тема и выход.",
        page,
        label_en="Open the user menu. It contains apps, profile, company, calendar, documentation, language, theme, and sign out.",
    )

    await menu.locator("[data-menu-action='company-selector']").click()
    await expect(menu.locator(".company-list")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='create-company']")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Пункт с названием компании раскрывает список компаний. Галочка показывает текущую компанию, а Create company создает новую компанию.",
        page,
        label_en="The company row opens the company list. The checkmark shows the active company, and Create company starts a new company.",
    )

    await menu.locator("[data-menu-action='apps']").click()
    services_modal = page.locator("platform-services-modal").first
    await expect(services_modal).to_be_visible(timeout=30_000)
    await expect(services_modal.locator("[data-service-id='flows']")).to_be_visible(timeout=30_000)
    await expect(services_modal.locator("[data-service-id='litserve']")).to_have_count(0)
    await scenario.step(
        "Пункт Apps открывает витрину сервисов. Это быстрый способ перейти в Flows, NetWorkle, RAG, Sync или Documents.",
        page,
        label_en="Apps opens the service launcher. It is a quick way to go to Flows, NetWorkle, RAG, Sync, or Documents.",
    )
    await _close_modal(page, "platform-services-modal")

    menu = await _open_user_menu(page)
    await menu.locator("[data-menu-action='profile']").click()
    profile_modal = page.locator("platform-user-info-modal").first
    await expect(profile_modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Пункт Profile открывает карточку пользователя: имя, email, роли и действия с аккаунтом.",
        page,
        label_en="Profile opens the user card with name, email, roles, and account actions.",
    )
    await _close_modal(page, "platform-user-info-modal")

    menu = await _open_user_menu(page)
    await expect(menu.locator("[data-menu-action='documentation']")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='language'] [data-locale='ru']")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='theme']")).to_be_visible(timeout=30_000)
    await expect(menu.locator("[data-menu-action='logout']")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Нижние пункты меню: Documentation открывает справку, Language меняет язык, Theme переключает тему, Logout выходит из аккаунта.",
        page,
        label_en="The lower menu items: Documentation opens help, Language changes the locale, Theme switches appearance, and Logout signs out.",
    )

    await menu.locator("[data-menu-action='calendar']").click()
    calendar_modal = page.locator("platform-calendar-modal").first
    await expect(calendar_modal).to_be_visible(timeout=30_000)
    await expect(calendar_modal.locator(".calendar-shell")).to_be_visible(timeout=30_000)
    await page.wait_for_timeout(400)
    await expect(
        page.locator("glass-toast").filter(has_text=re.compile(r"Could not load events|Не удалось загрузить события|HTTP 500"))
    ).to_have_count(0)
    bounds = await calendar_modal.locator(".modal").evaluate(
        """
        (el) => {
            const r = el.getBoundingClientRect();
            return {
                left: r.left,
                top: r.top,
                right: r.right,
                bottom: r.bottom,
                width: r.width,
                height: r.height,
                vw: window.innerWidth,
                vh: window.innerHeight,
            };
        }
        """
    )
    assert bounds["left"] >= -1
    assert bounds["top"] >= -1
    assert bounds["right"] <= bounds["vw"] + 1
    assert bounds["bottom"] <= bounds["vh"] + 1
    await scenario.step(
        "Пункт Calendar открывает календарь на весь экран. Модалка не уезжает за край окна и готова к работе.",
        page,
        label_en="Calendar opens the fullscreen calendar. The modal stays inside the viewport and is ready to use.",
    )
