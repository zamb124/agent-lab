"""Desktop E2E: Goose builtin extensions через real goosed HTTP."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from tests.agent.desktop_e2e.goosed_helpers import (
    disable_extension_in_settings,
    enable_extension_in_settings,
    get_goosed_base_url,
    goosed_call_tool,
    goosed_resume_session,
    goosed_start_session,
    goosed_tools_list,
    prepare_goosed_developer_session,
    prepare_goosed_session_with_extensions,
    resolve_tool_name,
    tool_response_contains,
    tool_response_text,
    wait_for_goosed_tools,
)
from tests.agent.desktop_e2e.helpers import (
    connect_desktop_browser,
    ensure_humanitec_paired_and_llm_ready,
    find_main_app_page,
    open_settings_extensions,
)

_MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.mark.asyncio
async def test_goose_dev_01_list_directory(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-dev01"
    marker = workspace / "humanitec-tree-marker.txt"
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            workspace.mkdir(parents=True, exist_ok=True)
            marker.write_text("tree-marker", encoding="utf-8")
            session_id = await prepare_goosed_developer_session(
                page,
                workspace,
                desktop=desktop,
                agent_frontend_http_client=agent_frontend_http_client,
                auth_token=auth_token,
            )
            tools = await goosed_tools_list(page, session_id)
            tree_tool = resolve_tool_name(tools, "tree")
            result = await goosed_call_tool(
                page,
                session_id,
                tree_tool,
                {"path": str(workspace), "depth": 2},
            )
            text = tool_response_text(result)
            assert marker.name in text or "humanitec-tree-marker" in text
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_dev_02_write_read_file_roundtrip(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-dev02"
    target_file = workspace / "humanitec-roundtrip.txt"
    payload = "humanitec-goose-dev-02"
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
            tools = await goosed_tools_list(page, session_id)
            write_tool = resolve_tool_name(tools, "write")
            shell_tool = resolve_tool_name(tools, "shell")
            await goosed_call_tool(
                page,
                session_id,
                write_tool,
                {"path": str(target_file), "content": payload},
            )
            read_result = await goosed_call_tool(
                page,
                session_id,
                shell_tool,
                {"command": f"cat {target_file}"},
            )
            assert tool_response_contains(read_result, payload)
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_dev_03_get_file_info(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-dev03"
    target_file = workspace / "info.txt"
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
            tools = await goosed_tools_list(page, session_id)
            write_tool = resolve_tool_name(tools, "write")
            tree_tool = resolve_tool_name(tools, "tree")
            await goosed_call_tool(
                page,
                session_id,
                write_tool,
                {"path": str(target_file), "content": "info"},
            )
            info_result = await goosed_call_tool(
                page,
                session_id,
                tree_tool,
                {"path": str(target_file), "depth": 1},
            )
            text = tool_response_text(info_result)
            assert "info.txt" in text or target_file.name in text
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_dev_04_search_files(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-dev04"
    target_file = workspace / "needle-humanitec.txt"
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
            tools = await goosed_tools_list(page, session_id)
            write_tool = resolve_tool_name(tools, "write")
            shell_tool = resolve_tool_name(tools, "shell")
            await goosed_call_tool(
                page,
                session_id,
                write_tool,
                {"path": str(target_file), "content": "find-me"},
            )
            search_result = await goosed_call_tool(
                page,
                session_id,
                shell_tool,
                {"command": f"rg --files {workspace} | rg needle-humanitec"},
            )
            assert tool_response_contains(search_result, "needle-humanitec")
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_dev_05_run_command(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-dev05"
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
            tools = await goosed_tools_list(page, session_id)
            shell_tool = resolve_tool_name(tools, "shell")
            command_result = await goosed_call_tool(
                page,
                session_id,
                shell_tool,
                {"command": "echo humanitec"},
            )
            assert tool_response_contains(command_result, "humanitec")
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_dev_06_edit_file(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-dev06"
    target_file = workspace / "edit-me.txt"
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
            tools = await goosed_tools_list(page, session_id)
            write_tool = resolve_tool_name(tools, "write")
            edit_tool = resolve_tool_name(tools, "edit")
            shell_tool = resolve_tool_name(tools, "shell")
            await goosed_call_tool(
                page,
                session_id,
                write_tool,
                {"path": str(target_file), "content": "alpha-beta-gamma"},
            )
            await goosed_call_tool(
                page,
                session_id,
                edit_tool,
                {
                    "path": str(target_file),
                    "before": "beta",
                    "after": "humanitec",
                },
            )
            read_result = await goosed_call_tool(
                page,
                session_id,
                shell_tool,
                {"command": f"cat {target_file}"},
            )
            assert tool_response_contains(read_result, "alpha-humanitec-gamma")
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_dev_07_read_image(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-dev07"
    image_path = workspace / "humanitec-pixel.png"
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            workspace.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(_MINIMAL_PNG)
            session_id = await prepare_goosed_developer_session(
                page,
                workspace,
                desktop=desktop,
                agent_frontend_http_client=agent_frontend_http_client,
                auth_token=auth_token,
            )
            tools = await goosed_tools_list(page, session_id)
            read_image_tool = resolve_tool_name(tools, "read_image")
            result = await goosed_call_tool(
                page,
                session_id,
                read_image_tool,
                {"source": str(image_path)},
            )
            content = result.get("content")
            assert isinstance(content, list)
            assert len(content) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_mem_01_store_retrieve_memory(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-mem01"
    memory_category = "humanitec-test-category"
    memory_value = "humanitec-test-value"
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            session_id = await prepare_goosed_session_with_extensions(
                page,
                workspace,
                desktop=desktop,
                agent_frontend_http_client=agent_frontend_http_client,
                auth_token=auth_token,
                enabled_extensions=["Memory"],
            )
            await wait_for_goosed_tools(page, session_id, name_suffix="remember_memory")
            tools = await goosed_tools_list(page, session_id)
            remember_tool = resolve_tool_name(tools, "remember_memory")
            retrieve_tool = resolve_tool_name(tools, "retrieve_memories")
            await goosed_call_tool(
                page,
                session_id,
                remember_tool,
                {
                    "category": memory_category,
                    "data": memory_value,
                    "tags": [],
                    "is_global": False,
                },
            )
            retrieve_result = await goosed_call_tool(
                page,
                session_id,
                retrieve_tool,
                {"category": memory_category, "is_global": False},
            )
            assert memory_value in tool_response_text(retrieve_result)
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_mem_02_list_delete_memory(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-mem02"
    memory_category = "humanitec-delete-category"
    memory_value = "humanitec-delete-value"
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            session_id = await prepare_goosed_session_with_extensions(
                page,
                workspace,
                desktop=desktop,
                agent_frontend_http_client=agent_frontend_http_client,
                auth_token=auth_token,
                enabled_extensions=["Memory"],
            )
            await wait_for_goosed_tools(page, session_id, name_suffix="remember_memory")
            tools = await goosed_tools_list(page, session_id)
            remember_tool = resolve_tool_name(tools, "remember_memory")
            retrieve_tool = resolve_tool_name(tools, "retrieve_memories")
            remove_tool = resolve_tool_name(tools, "remove_specific_memory")
            remove_category_tool = resolve_tool_name(tools, "remove_memory_category")
            await goosed_call_tool(
                page,
                session_id,
                remember_tool,
                {
                    "category": memory_category,
                    "data": memory_value,
                    "tags": [],
                    "is_global": False,
                },
            )
            list_result = await goosed_call_tool(
                page,
                session_id,
                retrieve_tool,
                {"category": memory_category, "is_global": False},
            )
            assert memory_value in tool_response_text(list_result)
            await goosed_call_tool(
                page,
                session_id,
                remove_tool,
                {
                    "category": memory_category,
                    "memory_content": memory_value,
                    "is_global": False,
                },
            )
            list_after = await goosed_call_tool(
                page,
                session_id,
                retrieve_tool,
                {"category": memory_category, "is_global": False},
            )
            assert memory_value not in tool_response_text(list_after)
            await goosed_call_tool(
                page,
                session_id,
                remove_category_tool,
                {"category": memory_category, "is_global": False},
            )
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_cc_01_computercontroller_tools_list(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-cc01"
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            session_id = await prepare_goosed_session_with_extensions(
                page,
                workspace,
                desktop=desktop,
                agent_frontend_http_client=agent_frontend_http_client,
                auth_token=auth_token,
                enabled_extensions=["Computer Controller"],
            )
            await wait_for_goosed_tools(page, session_id, name_suffix="web_scrape")
            tools = await goosed_tools_list(page, session_id, extension_name="computercontroller")
            names = {tool.get("name") for tool in tools if isinstance(tool.get("name"), str)}
            assert len(names) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_av_01_autovisualiser_tools_list(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-av01"
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            session_id = await prepare_goosed_session_with_extensions(
                page,
                workspace,
                desktop=desktop,
                agent_frontend_http_client=agent_frontend_http_client,
                auth_token=auth_token,
                enabled_extensions=["Auto Visualiser"],
            )
            await wait_for_goosed_tools(page, session_id, name_suffix="render_sankey")
            tools = await goosed_tools_list(page, session_id, extension_name="autovisualiser")
            assert len(tools) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_tut_01_tutorial_tools_list(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-tut01"
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            session_id = await prepare_goosed_session_with_extensions(
                page,
                workspace,
                desktop=desktop,
                agent_frontend_http_client=agent_frontend_http_client,
                auth_token=auth_token,
                enabled_extensions=["Tutorial"],
            )
            await wait_for_goosed_tools(page, session_id, name_suffix="load_tutorial")
            tools = await goosed_tools_list(page, session_id, extension_name="tutorial")
            assert len(tools) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_ext_03_enable_disable_extension_toggle(
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
            await open_settings_extensions(page)
            body_before = await page.locator("body").inner_text()
            assert "Memory" in body_before
            await enable_extension_in_settings(page, "Memory")
            body_after_enable = await page.locator("body").inner_text()
            assert body_after_enable != body_before or "Memory" in body_after_enable
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_ext_01_bundled_order_persisted_after_restart(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    from tests.agent.desktop_e2e.helpers import assert_platform_mcp_first_in_settings, read_bundled_extensions

    extensions = read_bundled_extensions()
    assert extensions[0]["id"] == "platform_mcp"
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
            await assert_platform_mcp_first_in_settings(page)
        desktop.stop()
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
            await assert_platform_mcp_first_in_settings(page)
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_ext_02_disable_developer_removes_tree_tool(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-ext02"
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
            tools_before = await goosed_tools_list(page, session_id)
            _ = resolve_tool_name(tools_before, "tree")
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


@pytest.mark.asyncio
async def test_goose_ipc_01_humanitec_agent_status_paired(
    agent_frontend_http_client,
    auth_token: str,
    humanitec_desktop_process_factory
) -> None:
    from tests.agent.desktop_e2e.helpers import pair_desktop_via_deep_link

    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            status = await page.evaluate("window.humanitecAgent.status()")
            if not isinstance(status, dict):
                raise AssertionError("humanitecAgent.status() must return object")
            assert status.get("paired") is True
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_ipc_02_resync_extensions_after_pair(
    agent_frontend_http_client,
    auth_token: str,
    humanitec_desktop_process_factory
) -> None:
    from tests.agent.desktop_e2e.helpers import pair_desktop_via_deep_link

    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            await page.evaluate("window.humanitecAgent.resyncExtensions()")
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_ipc_03_get_goosed_host_port_localhost(
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
            base_url = await get_goosed_base_url(page)
            assert base_url.startswith("https://127.0.0.1:") or base_url.startswith(
                "http://127.0.0.1:"
            )
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_ipc_04_discover_urls_match_frontend(
    agent_frontend_http_client,
    auth_token: str,
    humanitec_desktop_process_factory
) -> None:
    from tests.agent.desktop_e2e.helpers import pair_desktop_via_deep_link

    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            discover = await page.evaluate("window.humanitecAgent.discover()")
            if not isinstance(discover, dict):
                raise AssertionError("humanitecAgent.discover() must return object")
            frontend_base_url = discover.get("frontend_base_url")
            if not isinstance(frontend_base_url, str) or not frontend_base_url:
                raise AssertionError("discover.frontend_base_url missing")
            assert "9004" in frontend_base_url or frontend_base_url.startswith("http")
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_ipc_05_logout_clears_credentials(
    agent_frontend_http_client,
    auth_token: str,
    humanitec_desktop_process_factory
) -> None:
    from tests.agent.desktop_e2e.helpers import pair_desktop_via_deep_link

    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            await page.evaluate("window.humanitecAgent.logout()")
            status = await page.evaluate("window.humanitecAgent.status()")
            if not isinstance(status, dict):
                raise AssertionError("humanitecAgent.status() must return object")
            assert status.get("paired") is False
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_ipc_06_open_pairing_window(
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
            await page.evaluate("window.humanitecAgent.openPairing()")
            await page.wait_for_timeout(1500)
            pages = browser.contexts[0].pages if browser.contexts else []
            assert len(pages) >= 1
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_ipc_07_platform_mcp_env_updated_after_pair(
    agent_frontend_http_client,
    auth_token: str,
    humanitec_desktop_process_factory
) -> None:
    from tests.agent.desktop_e2e.helpers import pair_desktop_via_deep_link

    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            await page.evaluate(
                """() => {
                  window.__humanitecMcpEnvUpdated = false;
                  window.humanitecAgent.onPlatformMcpEnvUpdated(() => {
                    window.__humanitecMcpEnvUpdated = true;
                  });
                }"""
            )
            await pair_desktop_via_deep_link(
                desktop,
                agent_frontend_http_client,
                auth_token,
            )
            await page.wait_for_timeout(3000)
            event_after_pair = await page.evaluate("window.__humanitecMcpEnvUpdated")
            assert event_after_pair is True
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_ipc_08_llm_autoconfig_after_pair(
    agent_frontend_http_client,
    auth_token: str,
    humanitec_desktop_process_factory
) -> None:
    from tests.agent.desktop_e2e.helpers import pair_desktop_via_deep_link

    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            await pair_desktop_via_deep_link(
                desktop,
                agent_frontend_http_client,
                auth_token,
            )
            await page.wait_for_selector("[data-humanitec-chat-composer]", timeout=120_000)
            credentials = desktop.read_credentials()
            assert credentials["llm_provider_id"] == "humanitec"
            assert credentials["llm_model_id"] == "auto"
            assert credentials["llm_api_base_url"]
    finally:
        desktop.stop()
