"""UI E2E сценарии Flows: подключения компании (MCP и интеграции)."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from apps.flows.src.services.mcp_catalog_ids import server_id_from_catalog_id
from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_sync_mcp_server,
    flows_click_platform_button,
    flows_open_integrations_modal_from_home,
    flows_open_mcp_servers_modal,
    flows_seed_mcp_store_catalog_entry,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="setup",
    doc_slug="manage-mcp-servers",
    title="Управляем MCP-серверами компании",
    description=(
        "**Для чего:** эта инструкция поможет добавить MCP-сервер в компанию и проверить "
        "его инструменты.\n\n"
        "**Какие проблемы решает:** непонятно, где хранятся общие MCP-серверы и как "
        "установить сервер из каталога.\n\n"
        "**Результат:** MCP-сервер установлен, синхронизирован и готов к использованию агентами."
    ),
    title_en="Manage company MCP servers",
    description_en=(
        "**What for:** this guide helps you add an MCP server to the company and verify "
        "its tools.\n\n"
        "**Problems it solves:** it is unclear where shared MCP servers live and how to "
        "install one from the catalog.\n\n"
        "**Result:** the MCP server is installed, synced, and ready for agents."
    ),
    timeout_seconds=120,
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_flows_manage_mcp_servers(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    local_mcp_http_url: str,
) -> None:
    catalog_id = await flows_seed_mcp_store_catalog_entry(
        unique_id,
        upstream_url=local_mcp_http_url,
    )
    server_id = server_id_from_catalog_id(catalog_id)

    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-home-page")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте главную Flows",
        page,
        screenshot_name="flows-home-mcp-entry",
        label_en="Open the Flows home page",
        details=(
            "На главной Flows есть блок подключений компании. Кнопка MCP открывает "
            "управление серверами и каталогом инструментов."
        ),
        details_en=(
            "On the Flows home page, the company connections block includes MCP to manage "
            "servers and the tools catalog."
        ),
    )

    modal = await flows_open_mcp_servers_modal(page)
    await scenario.step(
        "Откройте управление MCP-серверами",
        page,
        screenshot_name="mcp-servers-modal-opened",
        label_en="Open MCP server management",
        details=(
            "В модалке видны подключённые серверы компании и вкладка каталога. Здесь "
            "добавляют HTTP/SSE серверы и устанавливают готовые записи."
        ),
        details_en=(
            "The modal shows connected company servers and a catalog tab. Here you add "
            "HTTP/SSE servers and install ready-made entries."
        ),
    )

    await flows_click_platform_button(modal, "Catalog", "Каталог")
    search = modal.locator("platform-modal-search-field").first
    await expect(search).to_be_visible(timeout=30_000)
    await search.evaluate(
        """
        (el, value) => {
            el.value = value;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        unique_id,
    )
    catalog_card = modal.locator(".mcp-card").filter(has_text=server_id).first
    await expect(catalog_card).to_be_visible(timeout=30_000)
    await flows_click_platform_button(catalog_card, "Install", "Установить")
    await expect(
        catalog_card.locator(".mcp-chip").filter(
            has_text=re.compile(r"Installed|Установлен")
        ).first
    ).to_be_visible(timeout=30_000)
    # Общий search filter модалки иначе оставляет Installed-вкладку пустой.
    await search.evaluate(
        """
        (el) => {
            el.value = '';
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: '' },
                bubbles: true,
                composed: true,
            }));
        }
        """
    )
    await flows_click_platform_button(modal, "Installed", "Подключённые")
    # Поиск по server_id: empty_init_pending скрывает карточки без platform defaults.
    await search.evaluate(
        """
        (el, value) => {
            el.value = value;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        server_id,
    )
    await expect(modal.get_by_text(server_id, exact=True)).to_be_visible(timeout=30_000)
    await flows_api_sync_mcp_server(flows_ui.origin, auth_token_system, server_id)
    await scenario.step(
        "Установите сервер из каталога",
        page,
        screenshot_name="mcp-server-installed",
        label_en="Install a server from the catalog",
        details=(
            "Найдите сервер в каталоге и нажмите «Установить». После синхронизации "
            "инструменты появятся в списке подключённых серверов."
        ),
        details_en=(
            "Find the server in the catalog and click Install. After sync, tools appear "
            "in the connected servers list."
        ),
    )

    await expect(modal.get_by_text(server_id, exact=True)).to_be_visible(timeout=30_000)
    await scenario.step(
        "Проверьте подключённый сервер",
        page,
        screenshot_name="mcp-server-ready",
        label_en="Verify the connected server",
        details=(
            "**Демонстрация результата.** Сервер виден среди подключённых — значит, "
            "инструменты MCP доступны агентам компании.\n\n"
            "**Итог.** Теперь вы умеете открыть управление MCP, установить сервер из "
            "каталога и подготовить его к работе."
        ),
        details_en=(
            "**Result demonstration.** The server appears among connected entries — MCP "
            "tools are available to company agents.\n\n"
            "**Summary.** You can now open MCP management, install a server from the "
            "catalog, and prepare it for use."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="setup",
    doc_slug="connect-oauth-integrations",
    title="Подключаем внешние аккаунты",
    description=(
        "**Для чего:** эта инструкция покажет, где смотреть OAuth-интеграции компании.\n\n"
        "**Какие проблемы решает:** непонятно, подключён ли внешний сервис и где управлять "
        "списком учётных данных.\n\n"
        "**Результат:** открыт список интеграций с поиском и таблицей подключений."
    ),
    title_en="Connect external accounts",
    description_en=(
        "**What for:** this guide shows where to review company OAuth integrations.\n\n"
        "**Problems it solves:** it is unclear whether an external service is connected "
        "and where to manage credentials.\n\n"
        "**Result:** the integrations list with search and connection table is open."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_connect_oauth_integrations(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-home-page")).to_be_visible(timeout=30_000)
    connect_card = page.locator(".connect-card").filter(
        has_text=re.compile(r"Integrations|Интеграции")
    ).first
    await expect(connect_card).to_be_visible(timeout=30_000)
    await scenario.step(
        "Найдите блок интеграций на главной",
        page,
        screenshot_name="integrations-entry-on-home",
        label_en="Find the integrations block on home",
        details=(
            "На главной Flows в разделе подключений есть карточка «Интеграции». "
            "Она ведёт к OAuth-учётным данным компании."
        ),
        details_en=(
            "On the Flows home page, the connections section has an Integrations card. "
            "It leads to company OAuth credentials."
        ),
    )

    modal = await flows_open_integrations_modal_from_home(page, flows_ui)
    await expect(modal.locator("platform-modal-search-field")).to_be_visible(timeout=30_000)
    await expect(modal.locator("table.int-table th").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте список интеграций",
        page,
        screenshot_name="integrations-modal-opened",
        label_en="Open the integrations list",
        details=(
            "Откроется модальное окно со строкой поиска и таблицей: провайдер, сервис, "
            "статус и действия. Здесь видно, какие аккаунты уже подключены."
        ),
        details_en=(
            "A modal opens with search and a table: provider, service, status, and actions. "
            "You can see which accounts are already connected."
        ),
    )

    empty_or_rows = modal.locator("table.int-table tbody tr").first
    await expect(empty_or_rows).to_be_visible(timeout=30_000)
    headers = modal.locator("table.int-table th")
    await expect(headers.filter(has_text=re.compile(r"Provider|Провайдер"))).to_be_visible(
        timeout=15_000
    )
    await expect(headers.filter(has_text=re.compile(r"Service|Сервис"))).to_be_visible(timeout=15_000)
    await scenario.step(
        "Проверьте колонки таблицы подключений",
        page,
        screenshot_name="integrations-table-columns",
        label_en="Review the connections table columns",
        details=(
            "Убедитесь, что в таблице есть колонки провайдера, сервиса и статуса. "
            "По ним видно, какой внешний аккаунт подключён и в каком он состоянии."
        ),
        details_en=(
            "Confirm the table has provider, service, and status columns. "
            "They show which external account is connected and its state."
        ),
    )

    search_field = modal.locator("platform-modal-search-field").first
    await expect(search_field).to_be_visible(timeout=15_000)
    await scenario.step(
        "Проверьте список подключённых аккаунтов",
        page,
        screenshot_name="integrations-list-ui",
        label_en="Review the connected accounts list",
        details=(
            "**Демонстрация результата.** Видны поиск, колонки таблицы и список записей "
            "или понятное пустое состояние — интерфейс готов для подключения внешних "
            "аккаунтов.\n\n"
            "**Итог.** Теперь вы знаете, где открыть интеграции компании и как проверить "
            "статус подключённых сервисов."
        ),
        details_en=(
            "**Result demonstration.** Search, table columns, and rows or a clear empty "
            "state are visible — the UI is ready for connecting external accounts.\n\n"
            "**Summary.** You now know where to open company integrations and how to check "
            "connected service status."
        ),
    )
