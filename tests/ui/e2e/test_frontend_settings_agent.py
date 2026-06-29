"""Playwright E2E: вкладка HumanitecAgent в настройках frontend."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


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
    origin: str,
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
        has_text=re.compile(r"HumanitecAgent")
    )
    await expect(agent_tab).to_be_visible(timeout=30_000)
    await agent_tab.click()


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-tab",
    title="Frontend: вкладка HumanitecAgent в настройках",
    title_en="Frontend: HumanitecAgent tab in settings",
    description="Страница настроек открывается, вкладка HumanitecAgent доступна.",
    description_en="Settings page opens and the HumanitecAgent tab is available.",
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
            has_text=re.compile(r"HumanitecAgent")
        )
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Вкладка HumanitecAgent видна на странице настроек",
        ui_page_system,
        label_en="HumanitecAgent tab is visible in settings",
    )


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-connect-section",
    title="Frontend: секция подключения HumanitecAgent",
    title_en="Frontend: HumanitecAgent connect section",
    description="На вкладке HumanitecAgent отображаются заголовок и кнопка подключения.",
    description_en="The HumanitecAgent tab shows the connect section title and button.",
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
        origin=frontend_ui.origin,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка HumanitecAgent",
        ui_page_system,
        label_en="HumanitecAgent settings tab opened",
    )
    await expect(
        ui_page_system.get_by_text(re.compile(r"Подключение компьютера|Connect your computer"))
    ).to_be_visible(timeout=30_000)
    await expect(
        ui_page_system.get_by_role("button", name=re.compile(r"Подключить компьютер|Connect computer"))
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Секция подключения HumanitecAgent отображается",
        ui_page_system,
        label_en="HumanitecAgent connect section is visible",
    )


@pytest.mark.scenario(
    service="frontend",
    tag="settings-agent",
    doc_slug="settings-agent-devices-empty",
    title="Frontend: пустой список устройств HumanitecAgent",
    title_en="Frontend: empty HumanitecAgent devices list",
    description="На вкладке HumanitecAgent показывается пустое состояние списка устройств.",
    description_en="The HumanitecAgent tab shows the empty devices list state.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f3_settings_agent_devices_empty(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await _open_settings_agent_tab(
        scenario,
        ui_page_system,
        origin=frontend_ui.origin,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка HumanitecAgent",
        ui_page_system,
        label_en="HumanitecAgent settings tab opened",
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
    title="Frontend: пустой audit HumanitecAgent",
    title_en="Frontend: empty HumanitecAgent audit log",
    description="На вкладке HumanitecAgent показывается пустой audit log.",
    description_en="The HumanitecAgent tab shows an empty audit log.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f4_settings_agent_audit_empty(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    await _open_settings_agent_tab(
        scenario,
        ui_page_system,
        origin=frontend_ui.origin,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка HumanitecAgent",
        ui_page_system,
        label_en="HumanitecAgent settings tab opened",
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
    title="Frontend: создание pairing code HumanitecAgent",
    title_en="Frontend: create HumanitecAgent pairing code",
    description="Кнопка подключения создаёт pairing code на вкладке HumanitecAgent.",
    description_en="The connect button creates a pairing code on the HumanitecAgent tab.",
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
        origin=frontend_ui.origin,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка HumanitecAgent",
        ui_page_system,
        label_en="HumanitecAgent tab opened",
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
    title="Frontend: ссылка на скачивание HumanitecAgent",
    title_en="Frontend: HumanitecAgent download link",
    description="На вкладке HumanitecAgent есть ссылка на страницу загрузки desktop-клиента.",
    description_en="The HumanitecAgent tab includes a link to the desktop client download page.",
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
        origin=frontend_ui.origin,
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
    title="Frontend: статус релиза HumanitecAgent",
    title_en="Frontend: HumanitecAgent release status",
    description="На вкладке HumanitecAgent отображается блок статуса desktop-релиза.",
    description_en="The HumanitecAgent tab shows the desktop release status block.",
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
        origin=frontend_ui.origin,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка HumanitecAgent",
        ui_page_system,
        label_en="HumanitecAgent settings tab opened",
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
    title="Frontend: подсказка pairing HumanitecAgent",
    title_en="Frontend: HumanitecAgent pairing help text",
    description="На вкладке HumanitecAgent отображается help-текст про pairing code.",
    description_en="The HumanitecAgent tab shows help text about the pairing code.",
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
        origin=frontend_ui.origin,
        frontend_ui=frontend_ui,
    )
    await scenario.step(
        "Открыта вкладка HumanitecAgent",
        ui_page_system,
        label_en="HumanitecAgent settings tab opened",
    )
    await expect(
        ui_page_system.get_by_text(
            re.compile(
                r"Сгенерируйте код и введите его в HumanitecAgent|"
                r"Generate a pairing code and enter it in HumanitecAgent"
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
    agent_frontend_http_client,
    auth_token: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import pair_and_register_device

    device_name = f"Device {unique_id}"
    await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    await ui_page_system.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    await expect(ui_page_system.get_by_text(device_name)).to_be_visible(timeout=30_000)


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
    agent_frontend_http_client,
    auth_token: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import pair_and_register_device

    await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    await ui_page_system.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    ui_page_system.once("dialog", lambda dialog: dialog.accept())
    revoke_button = ui_page_system.locator("frontend-settings-page glass-button").filter(
        has_text=re.compile(r"Отозвать|Revoke")
    ).first
    await expect(revoke_button).to_be_visible(timeout=30_000)
    await revoke_button.click()
    await expect(
        ui_page_system.get_by_text(re.compile(r"Отключено|Revoked|Offline"))
    ).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f11_settings_agent_policy_shell_toggle(
    frontend_ui: AppUI,
    ui_page_system: Page,
    agent_frontend_http_client,
    auth_token: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import pair_and_register_device

    await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    await ui_page_system.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    toggle_shell = ui_page_system.locator("frontend-settings-page glass-button").filter(
        has_text=re.compile(r"Shell|shell")
    ).first
    await expect(toggle_shell).to_be_visible(timeout=30_000)
    shell_line_before = ui_page_system.locator("frontend-settings-page .caps-line").filter(
        has_text=re.compile(r"Shell MCP")
    ).first
    before_text = await shell_line_before.inner_text()
    await toggle_shell.click()
    await expect(
        ui_page_system.get_by_text(re.compile(r"Device policy updated|Политика устройства обновлена"))
    ).to_be_visible(timeout=30_000)
    after_text = await shell_line_before.inner_text()
    assert before_text != after_text


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f12_settings_agent_audit_after_register(
    frontend_ui: AppUI,
    ui_page_system: Page,
    agent_frontend_http_client,
    auth_token: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import pair_and_register_device

    await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    await ui_page_system.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
    await expect(
        ui_page_system.get_by_text(re.compile(r"Device registered|Устройство зарегистрировано"))
    ).to_be_visible(timeout=30_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_f14_settings_agent_release_banner_lvh_origin(
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    assert "system.lvh.me" in frontend_ui.origin
    await _open_settings_agent_tab_raw(ui_page_system, origin=frontend_ui.origin)
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
