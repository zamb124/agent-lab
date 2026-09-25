"""Playwright E2E: вкладка LinnexAgent в настройках frontend."""

from __future__ import annotations

import os
import re

import pytest
import pytest_asyncio
from playwright.async_api import Page, expect

from tests.agent._helpers import reset_company_agent_ui_state
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest_asyncio.fixture
async def system_agent_settings_empty(frontend_di) -> None:
    from tests.ui.e2e_worker import ui_e2e_company_id

    await reset_company_agent_ui_state(frontend_di, company_id=ui_e2e_company_id())


async def _open_settings_page(scenario: ScenarioRecorder, frontend_ui: AppUI, page: Page) -> None:
    await frontend_ui.open(page)
    await frontend_ui.expect_shell(page)
    await page.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await expect(page.locator("frontend-settings-page")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открыта страница настроек платформы",
        page,
        label_en="Platform settings page opened",
    )


async def _open_settings_agent_tab(
    scenario: ScenarioRecorder,
    page: Page,
    *,
    frontend_ui: AppUI,
) -> None:
    await _open_settings_page(scenario, frontend_ui, page)
    await _click_settings_agent_tab(page)


async def _open_settings_agent_tab_raw(page: Page, *, origin: str) -> None:
    await page.goto(f"{origin}/settings", wait_until="domcontentloaded")
    await expect(page.locator("frontend-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("frontend-settings-page")).to_be_visible(timeout=30_000)
    await _click_settings_agent_tab(page)


async def _click_settings_agent_tab(page: Page) -> None:
    agent_tab = page.locator("frontend-settings-page .tab").filter(
        has_text=re.compile(r"LinnexAgent")
    )
    await expect(agent_tab).to_be_visible(timeout=30_000)
    await agent_tab.click()


async def _wait_agent_releases_status(page: Page) -> None:
    await page.wait_for_function(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const slice = bus.getState().frontendAgentReleasesStatus;
            if (!slice || slice.busy) return false;
            return slice.lastResult != null;
        }""",
        timeout=60_000,
    )


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-tab",
    title="Frontend: вкладка LinnexAgent в настройках",
    title_en="Frontend: LinnexAgent tab in settings",
    description="Страница настроек открывается, вкладка LinnexAgent доступна.",
    description_en="Settings page opens and the LinnexAgent tab is available.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f1_settings_agent_tab_visible(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await frontend_ui.open(ui_page_system)
    await frontend_ui.expect_shell(ui_page_system)
    await ui_page_system.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await expect(ui_page_system.locator("frontend-settings-page")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открыта страница настроек платформы",
        ui_page_system,
        label_en="Platform settings page opened",
    )
    await expect(
        ui_page_system.locator("frontend-settings-page .tab").filter(
            has_text=re.compile(r"LinnexAgent")
        )
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Вкладка LinnexAgent видна на странице настроек",
        ui_page_system,
        label_en="LinnexAgent tab is visible in settings",
    )


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-connect-section",
    title="Frontend: секция подключения LinnexAgent",
    title_en="Frontend: LinnexAgent connect section",
    description="На вкладке LinnexAgent отображаются заголовок и кнопка подключения.",
    description_en="The LinnexAgent tab shows the connect section title and button.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f2_settings_agent_connect_section(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await _open_settings_agent_tab(
        scenario,
        ui_page_system,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка LinnexAgent",
        ui_page_system,
        label_en="LinnexAgent settings tab opened",
    )
    await expect(
        ui_page_system.get_by_text(re.compile(r"Подключение компьютера|Connect your computer"))
    ).to_be_visible(timeout=30_000)
    await expect(
        ui_page_system.get_by_role("button", name=re.compile(r"Подключить компьютер|Connect computer"))
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Секция подключения LinnexAgent отображается",
        ui_page_system,
        label_en="LinnexAgent connect section is visible",
    )


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-devices-empty",
    title="Frontend: пустой список устройств LinnexAgent",
    title_en="Frontend: empty LinnexAgent devices list",
    description="На вкладке LinnexAgent показывается пустое состояние списка устройств.",
    description_en="The LinnexAgent tab shows the empty devices list state.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f3_settings_agent_devices_empty(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
    system_agent_settings_empty: None,
) -> None:
    await _open_settings_agent_tab(
        scenario,
        ui_page_system,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка LinnexAgent",
        ui_page_system,
        label_en="LinnexAgent settings tab opened",
    )
    await expect(
        ui_page_system.get_by_text(re.compile(r"Подключённые устройства|Connected devices"))
    ).to_be_visible(timeout=30_000)
    await expect(
        ui_page_system.get_by_text(re.compile(r"Устройства ещё не подключены|No devices connected yet"))
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Пустой список устройств отображается",
        ui_page_system,
        label_en="Empty devices list is visible",
    )


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-audit-empty",
    title="Frontend: пустой audit LinnexAgent",
    title_en="Frontend: empty LinnexAgent audit log",
    description="На вкладке LinnexAgent показывается пустой audit log.",
    description_en="The LinnexAgent tab shows an empty audit log.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f4_settings_agent_audit_empty(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
    system_agent_settings_empty: None,
) -> None:
    await _open_settings_agent_tab(
        scenario,
        ui_page_system,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка LinnexAgent",
        ui_page_system,
        label_en="LinnexAgent settings tab opened",
    )
    await expect(
        ui_page_system.get_by_text(re.compile(r"Журнал аудита|Audit log"))
    ).to_be_visible(timeout=30_000)
    await expect(
        ui_page_system.get_by_text(re.compile(r"Событий аудита пока нет|No audit events yet"))
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Пустой audit log отображается",
        ui_page_system,
        label_en="Empty audit log is visible",
    )


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-pairing-code",
    title="Frontend: создание pairing code LinnexAgent",
    title_en="Frontend: create LinnexAgent pairing code",
    description="Кнопка подключения создаёт pairing code на вкладке LinnexAgent.",
    description_en="The connect button creates a pairing code on the LinnexAgent tab.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f5_settings_agent_pairing_code(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await _open_settings_agent_tab(
        scenario,
        ui_page_system,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка LinnexAgent",
        ui_page_system,
        label_en="LinnexAgent tab opened",
    )
    connect_button = ui_page_system.get_by_role(
        "button",
        name=re.compile(r"Подключить компьютер|Connect computer"),
    )
    await connect_button.click()
    pairing_code_cell = ui_page_system.locator("frontend-settings-page .info-grid dd").first
    await expect(pairing_code_cell).to_be_visible(timeout=30_000)
    pairing_text = await pairing_code_cell.inner_text()
    assert len(re.sub(r"\D", "", pairing_text)) >= 6
    await scenario.step(
        "Pairing code создан и отображается",
        ui_page_system,
        label_en="Pairing code is created and visible",
    )


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-download-link",
    title="Frontend: ссылка на скачивание LinnexAgent",
    title_en="Frontend: LinnexAgent download link",
    description="На вкладке LinnexAgent есть ссылка на страницу загрузки desktop-клиента.",
    description_en="The LinnexAgent tab includes a link to the desktop client download page.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f6_settings_agent_download_link(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await _open_settings_agent_tab(
        scenario,
        ui_page_system,
        frontend_ui=frontend_ui,
    )
    download_link = ui_page_system.locator('frontend-settings-page a[href="/agent"]')
    await expect(download_link).to_be_visible(timeout=30_000)
    await expect(
        download_link.filter(has_text=re.compile(r"страницу загрузки|download page"))
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Ссылка на download page видна",
        ui_page_system,
        label_en="Download page link is visible",
    )


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-release-banner",
    title="Frontend: статус релиза LinnexAgent",
    title_en="Frontend: LinnexAgent release status",
    description="На вкладке LinnexAgent отображается блок статуса desktop-релиза.",
    description_en="The LinnexAgent tab shows the desktop release status block.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f7_settings_agent_release_banner(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await _open_settings_agent_tab(
        scenario,
        ui_page_system,
        frontend_ui=frontend_ui,
    )
    await _wait_agent_releases_status(ui_page_system)
    await scenario.step(
        "Открыта вкладка LinnexAgent",
        ui_page_system,
        label_en="LinnexAgent settings tab opened",
    )
    await expect(
        ui_page_system.locator("frontend-settings-page .section-help").filter(
            has_text=re.compile(
                r"Desktop release is available|Desktop release is not published|"
                r"Desktop release доступен|Desktop release ещё не опубликован"
            )
        )
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Блок статуса релиза отображается",
        ui_page_system,
        label_en="Release status block is visible",
    )


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-help-text",
    title="Frontend: подсказка pairing LinnexAgent",
    title_en="Frontend: LinnexAgent pairing help text",
    description="На вкладке LinnexAgent отображается help-текст про pairing code.",
    description_en="The LinnexAgent tab shows help text about the pairing code.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f8_settings_agent_help_text(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await _open_settings_agent_tab(
        scenario,
        ui_page_system,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка LinnexAgent",
        ui_page_system,
        label_en="LinnexAgent settings tab opened",
    )
    await expect(
        ui_page_system.get_by_text(
            re.compile(
                r"Сгенерируйте код и введите его в LinnexAgent|"
                r"Generate a pairing code and enter it in LinnexAgent"
            )
        )
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Help-текст про pairing отображается",
        ui_page_system,
        label_en="Pairing help text is visible",
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f9_settings_agent_devices_after_pair(
    frontend_ui: AppUI,
    ui_page_system: Page,
    agent_frontend_http_client_system,
    auth_token_system: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import pair_and_register_device

    device_name = f"Device {unique_id}"
    await pair_and_register_device(
        agent_frontend_http_client_system,
        auth_cookie=auth_token_system,
        unique_id=unique_id,
    )
    await ui_page_system.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    # title-line + ref-line оба содержат device_name — берём видимый title.
    await expect(
        ui_page_system.locator(".title-line").filter(has_text=device_name).first
    ).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f13_settings_agent_download_href(
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    _ = frontend_ui
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    download_link = ui_page_system.locator("frontend-settings-page a[href='/agent']")
    await expect(download_link).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f10_settings_agent_revoke_device(
    frontend_ui: AppUI,
    ui_page_system: Page,
    agent_frontend_http_client_system,
    auth_token_system: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import pair_and_register_device

    await pair_and_register_device(
        agent_frontend_http_client_system,
        auth_cookie=auth_token_system,
        unique_id=unique_id,
    )
    await ui_page_system.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    device_card = ui_page_system.locator("frontend-settings-page .custom-provider-card").filter(
        has_text=f"Device {unique_id}"
    )
    ui_page_system.once("dialog", lambda dialog: dialog.accept())
    revoke_button = device_card.locator("glass-button").filter(
        has_text=re.compile(r"Отозвать|Revoke")
    )
    await expect(revoke_button).to_be_visible(timeout=30_000)
    await revoke_button.click()
    await expect(
        device_card.locator(".caps-line").filter(
            has_text=re.compile(r"Revoked|Отключено")
        )
    ).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f11_settings_agent_policy_shell_toggle(
    frontend_ui: AppUI,
    ui_page_system: Page,
    agent_frontend_http_client_system,
    auth_token_system: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import pair_and_register_device

    await pair_and_register_device(
        agent_frontend_http_client_system,
        auth_cookie=auth_token_system,
        unique_id=unique_id,
    )
    await ui_page_system.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    device_card = ui_page_system.locator("frontend-settings-page .custom-provider-card").filter(
        has_text=f"Device {unique_id}"
    )
    toggle_shell = device_card.locator("glass-button").filter(
        has_text=re.compile(r"Shell|shell")
    )
    await expect(toggle_shell).to_be_visible(timeout=30_000)
    shell_line_before = device_card.locator(".caps-line").filter(
        has_text=re.compile(r"Shell MCP")
    )
    before_text = await shell_line_before.inner_text()
    await toggle_shell.click()
    await expect(shell_line_before).not_to_have_text(before_text, timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f12_settings_agent_audit_after_register(
    frontend_ui: AppUI,
    ui_page_system: Page,
    agent_frontend_http_client_system,
    auth_token_system: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import pair_and_register_device

    await pair_and_register_device(
        agent_frontend_http_client_system,
        auth_cookie=auth_token_system,
        unique_id=unique_id,
    )
    await ui_page_system.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    await expect(
        ui_page_system.locator("frontend-settings-page .custom-provider-card").filter(
            has_text=re.compile(r"Device registered|Устройство зарегистрировано")
        ).filter(
            has_text=f"Device {unique_id}"
        )
    ).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f14_settings_agent_release_banner_lvh_origin(
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    from tests.ui.e2e_worker import ui_e2e_subdomain

    assert f"{ui_e2e_subdomain()}.lvh.me" in frontend_ui.origin
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    await _wait_agent_releases_status(ui_page_system)
    await expect(
        ui_page_system.locator("frontend-settings-page .section-help").filter(
            has_text=re.compile(
                r"Desktop release is available|Desktop release is not published|"
                r"Desktop release доступен|Desktop release ещё не опубликован"
            )
        )
    ).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f15_settings_agent_pairing_code_ttl(
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    connect_button = ui_page_system.locator("frontend-settings-page button.btn").filter(
        has_text=re.compile(r"Подключить|Connect")
    )
    await connect_button.click()
    pairing_code = ui_page_system.locator("frontend-settings-page .info-grid dd").first
    await expect(pairing_code).to_be_visible(timeout=30_000)
    ttl_line = ui_page_system.locator("frontend-settings-page .info-grid dd").nth(1)
    await expect(ttl_line).to_be_visible(timeout=30_000)
    ttl_text = await ttl_line.inner_text()
    assert ttl_text.endswith("s")
    assert int(ttl_text.replace("s", "").strip()) > 0


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-toolkits",
    title="Frontend: группы инструментов LinnexAgent",
    title_en="Frontend: LinnexAgent toolkits section",
    description="Вкладка LinnexAgent показывает список групп инструментов платформы.",
    description_en="LinnexAgent tab shows platform toolkit groups list.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f16_settings_agent_toolkits_section(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await _open_settings_agent_tab(
        scenario,
        ui_page_system,
        frontend_ui=frontend_ui,
    )
    toolkits_heading = ui_page_system.locator("frontend-settings-page h3").filter(
        has_text=re.compile(r"Группы инструментов|Agent tool groups")
    )
    await expect(toolkits_heading).to_be_visible(timeout=30_000)
    await scenario.step(
        "Секция групп инструментов агента видна",
        ui_page_system,
        label_en="Agent toolkits section is visible",
    )
    await expect(
        ui_page_system.locator("frontend-settings-page .custom-provider-card").first
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Список групп инструментов отображается",
        ui_page_system,
        label_en="Toolkit groups list is rendered",
    )
