"""Desktop E2E: goosed /config/extensions API."""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from tests.agent.desktop_e2e.goosed_helpers import (
    disable_extension_in_settings,
    goosed_get_config_extensions,
    goosed_resume_session,
    goosed_start_session,
    goosed_tools_list,
    prepare_goosed_developer_session,
    wait_for_goosed_tools,
)
from tests.agent.desktop_e2e.helpers import (
    connect_desktop_browser,
    ensure_humanitec_paired_and_llm_ready,
    find_main_app_page,
)


@pytest.mark.asyncio
async def test_goose_cfg_01_config_extensions_platform_mcp_first(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            await ensure_humanitec_paired_and_llm_ready(
                desktop,
                page,
                agent_frontend_http_client,
                auth_token,
            )
            extensions = await goosed_get_config_extensions(page)
            names: list[str] = []
            for entry in extensions:
                config = entry.get("config")
                if isinstance(config, dict):
                    name = config.get("name")
                    if isinstance(name, str):
                        names.append(name)
            if not names:
                display_name = extensions[0].get("display_name") if extensions else None
                if isinstance(display_name, str):
                    names.append(display_name)
            assert len(names) > 0
            assert names[0] == "platform_mcp" or "platform_mcp" in names[0]
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_cfg_02_disable_developer_reflected_in_tools(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-cfg02"
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            session_id = await prepare_goosed_developer_session(
                page,
                workspace,
                desktop=desktop,
                agent_frontend_http_client=agent_frontend_http_client,
                auth_token=auth_token,
            )
            await wait_for_goosed_tools(page, session_id, name_suffix="tree")
            await disable_extension_in_settings(page, "Developer")
            session_id_after = await goosed_start_session(page, workspace)
            await goosed_resume_session(page, session_id_after)
            tools_after = await goosed_tools_list(page, session_id_after)
            tool_names = {
                tool.get("name")
                for tool in tools_after
                if isinstance(tool.get("name"), str)
            }
            assert not any(name.endswith("tree") for name in tool_names)
    finally:
        desktop.stop()
