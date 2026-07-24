"""Playwright E2E: управление пространствами в консоли frontend."""

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
    tag="namespaces",
    doc_slug="console-namespaces",
    title="Как посмотреть и создать пространство компании",
    description=(
        "**Для чего:** эта инструкция поможет администратору открыть список "
        "пространств компании в консоли и создать новое рабочее пространство.\n\n"
        "**Какие проблемы решает:** вы узнаете, где в консоли лежат пространства "
        "сотрудников и отделов, как отфильтровать личные каталоги и как добавить "
        "лёгкое пространство без CRM-шаблона.\n\n"
        "**Результат:** новое пространство видно в списке с именем, которое вы задали."
    ),
    title_en="How to view and create a company namespace",
    description_en=(
        "**Purpose:** helps an admin open the company namespaces list in the console "
        "and create a lightweight workspace.\n\n"
        "**Problems it solves:** you learn where employee and department spaces live, "
        "how to filter personal catalogs, and how to add a workspace without a CRM template.\n\n"
        "**Result:** the new workspace appears in the list under the name you chose."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_console_namespaces_list_filter_and_create(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    workspace_name = f"uiws_{unique_id}"

    await frontend_ui.open(ui_page_system)
    await frontend_ui.expect_shell(ui_page_system)
    await ui_page_system.goto(
        f"{frontend_ui.origin}/namespaces",
        wait_until="domcontentloaded",
    )
    page_root = ui_page_system.locator("frontend-namespaces-page")
    await expect(page_root).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте страницу пространств",
        ui_page_system,
        screenshot_name="namespaces-page-opened",
        details=(
            "В консоли платформы откройте раздел Namespaces (Пространства) в боковом меню "
            "или перейдите по адресу /namespaces. Это нужно, чтобы увидеть реестр "
            "рабочих и личных пространств компании. На экране появится заголовок страницы "
            "и список карточек."
        ),
        label_en="Open the namespaces page",
        details_en=(
            "In the platform console, open Namespaces in the sidebar or go to /namespaces. "
            "This shows the company registry of work and personal spaces. You should see "
            "the page title and a list of cards."
        ),
    )

    personal_filter = page_root.locator(".filter-tag").filter(
        has_text=re.compile(r"Personal|Личные|personal", re.I)
    )
    await personal_filter.click()
    await expect(personal_filter).to_have_attribute("aria-pressed", "true", timeout=15_000)
    await scenario.step(
        "Отфильтруйте личные пространства",
        ui_page_system,
        screenshot_name="namespaces-filter-personal",
        details=(
            "Нажмите фильтр Personal (Личные). Так вы оставите в списке только "
            "именные каталоги сотрудников. Кнопка фильтра подсветится как активная."
        ),
        label_en="Filter personal namespaces",
        details_en=(
            "Click the Personal filter. The list keeps only employee personal catalogs. "
            "The filter button appears pressed."
        ),
    )

    all_filter = page_root.locator(".filter-tag").filter(
        has_text=re.compile(r"^All$|^Все$|all", re.I)
    ).first
    await all_filter.click()
    await expect(all_filter).to_have_attribute("aria-pressed", "true", timeout=15_000)
    await scenario.step(
        "Вернитесь к полному списку",
        ui_page_system,
        screenshot_name="namespaces-filter-all",
        details=(
            "Нажмите фильтр All (Все), чтобы снова увидеть и рабочие пространства компании, "
            "и личные каталоги. Это нужно перед созданием нового workspace — иначе карточка "
            "нового пространства не появится в текущем отфильтрованном списке."
        ),
        label_en="Return to the full list",
        details_en=(
            "Click the All filter to show company workspaces and personal catalogs again. "
            "Do this before creating a new workspace — otherwise the new card may stay "
            "hidden behind the personal-only filter."
        ),
    )

    create_btn = page_root.locator("page-header button, button.btn-primary").filter(
        has_text=re.compile(r"Create workspace|Создать", re.I)
    ).first
    await create_btn.click()
    create_form = page_root.locator("form.create-panel")
    await expect(create_form).to_be_visible(timeout=15_000)
    await scenario.step(
        "Откройте форму создания пространства",
        ui_page_system,
        screenshot_name="namespaces-create-form",
        details=(
            "Нажмите кнопку Create workspace (Создать пространство). Появится форма "
            "с полями имени и описания — без выбора CRM-шаблона."
        ),
        label_en="Open the create workspace form",
        details_en=(
            "Click Create workspace. A form opens with name and description fields — "
            "without choosing a CRM template."
        ),
    )

    name_input = create_form.locator("input.field-pill-input").first
    await expect(name_input).to_be_visible(timeout=15_000)
    await name_input.fill(workspace_name)
    desc_input = create_form.locator("textarea.field-pill-textarea, textarea").first
    await expect(desc_input).to_be_visible(timeout=15_000)
    await desc_input.fill(f"UI workspace {unique_id}")

    await create_form.locator('button[type="submit"]').click()
    await expect(page_root.locator(".card-title, .card").filter(has_text=workspace_name)).to_be_visible(
        timeout=30_000
    )
    crm_link = page_root.locator("a.crm-link").first
    await expect(crm_link).to_be_visible(timeout=15_000)
    await scenario.step(
        "Проверьте созданное пространство в списке",
        ui_page_system,
        screenshot_name="namespace-created-in-list",
        details=(
            "**Демонстрация результата.** В списке появилась карточка с именем "
            f"{workspace_name}. Рядом видна ссылка на настройки CRM — значит пространство "
            "зарегистрировано как рабочее пространство компании.\n\n"
            "**Итог.** Теперь вы умеете открыть реестр пространств, отфильтровать "
            "личные каталоги и создать лёгкое workspace без CRM-шаблона."
        ),
        label_en="Confirm the new workspace in the list",
        details_en=(
            "**Result demonstration.** The list shows a card named "
            f"{workspace_name}. A CRM settings link next to it means the space is "
            "registered as a company workspace.\n\n"
            "**Summary.** You can open the namespaces registry, filter personal "
            "catalogs, and create a lightweight workspace without a CRM template."
        ),
    )
