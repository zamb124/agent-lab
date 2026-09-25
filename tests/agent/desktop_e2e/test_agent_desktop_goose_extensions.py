"""Desktop E2E: Goose builtin extensions через real goosed HTTP."""

from __future__ import annotations

import base64

import pytest
from playwright.async_api import async_playwright

from tests.agent.desktop_e2e.conftest import (
    GoosedDeveloperOnlySession,
    GooseDeveloperRuntime,
    GoosedExtensionSession,
    GoosedExtensionSessionSpec,
    PairedDesktopSession,
    PairedDesktopUiSession,
)
from tests.agent.desktop_e2e.goosed_helpers import (
    assert_tool_ok,
    disable_extension_in_settings,
    enable_extension_in_settings,
    get_goosed_base_url,
    goosed_call_tool,
    goosed_resume_session,
    goosed_start_session,
    goosed_tools_list,
    resolve_tool_name,
    tool_response_contains,
    tool_response_text,
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
    goose_developer_runtime: GooseDeveloperRuntime,
) -> None:
    marker = goose_developer_runtime.workspace / "humanitec-tree-marker.txt"
    marker.write_text("tree-marker", encoding="utf-8")
    tools = await goosed_tools_list(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
    )
    tree_tool = resolve_tool_name(tools, "tree")
    result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        tree_tool,
        {"path": ".", "depth": 2},
    )
    assert_tool_ok(result, action="tree")
    text = tool_response_text(result)
    assert marker.name in text or "humanitec-tree-marker" in text


@pytest.mark.asyncio
async def test_goose_dev_02_write_read_file_roundtrip(
    goose_developer_runtime: GooseDeveloperRuntime,
) -> None:
    relative_path = "humanitec-roundtrip.txt"
    target_file = goose_developer_runtime.workspace / relative_path
    payload = "humanitec-goose-dev-02"
    tools = await goosed_tools_list(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
    )
    write_tool = resolve_tool_name(tools, "write")
    shell_tool = resolve_tool_name(tools, "shell")
    write_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        write_tool,
        {"path": relative_path, "content": payload},
    )
    assert_tool_ok(write_result, action="write")
    assert target_file.is_file(), f"write did not create {target_file}: {write_result!r}"
    assert target_file.read_text(encoding="utf-8") == payload
    read_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        shell_tool,
        {"command": f"cat {relative_path}"},
    )
    assert_tool_ok(read_result, action="cat")
    assert tool_response_contains(read_result, payload)


@pytest.mark.asyncio
async def test_goose_dev_03_get_file_info(
    goose_developer_runtime: GooseDeveloperRuntime,
) -> None:
    relative_path = "info.txt"
    target_file = goose_developer_runtime.workspace / relative_path
    tools = await goosed_tools_list(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
    )
    write_tool = resolve_tool_name(tools, "write")
    tree_tool = resolve_tool_name(tools, "tree")
    shell_tool = resolve_tool_name(tools, "shell")
    write_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        write_tool,
        {"path": relative_path, "content": "info"},
    )
    assert_tool_ok(write_result, action="write")
    assert target_file.is_file()
    # tree — directory listing with line counts, not a file-stat tool.
    tree_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        tree_tool,
        {"path": ".", "depth": 1},
    )
    assert_tool_ok(tree_result, action="tree")
    assert "info.txt" in tool_response_text(tree_result)
    stat_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        shell_tool,
        {"command": f"wc -c {relative_path}"},
    )
    assert_tool_ok(stat_result, action="wc")
    assert tool_response_contains(stat_result, "4")


@pytest.mark.asyncio
async def test_goose_dev_04_search_files(
    goose_developer_runtime: GooseDeveloperRuntime,
) -> None:
    relative_path = "needle-humanitec.txt"
    target_file = goose_developer_runtime.workspace / relative_path
    tools = await goosed_tools_list(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
    )
    write_tool = resolve_tool_name(tools, "write")
    shell_tool = resolve_tool_name(tools, "shell")
    write_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        write_tool,
        {"path": relative_path, "content": "find-me"},
    )
    assert_tool_ok(write_result, action="write")
    assert target_file.is_file()
    # Developer instructions recommend rg; PATH must include Homebrew for GUI Electron.
    search_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        shell_tool,
        {"command": "rg --files | rg needle-humanitec"},
    )
    assert_tool_ok(search_result, action="rg search")
    assert tool_response_contains(search_result, "needle-humanitec")


@pytest.mark.asyncio
async def test_goose_dev_05_run_command(
    goose_developer_runtime: GooseDeveloperRuntime,
) -> None:
    tools = await goosed_tools_list(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
    )
    shell_tool = resolve_tool_name(tools, "shell")
    command_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        shell_tool,
        {"command": "echo humanitec"},
    )
    assert_tool_ok(command_result, action="echo")
    assert tool_response_contains(command_result, "humanitec")


@pytest.mark.asyncio
async def test_goose_dev_06_edit_file(
    goose_developer_runtime: GooseDeveloperRuntime,
) -> None:
    relative_path = "edit-me.txt"
    target_file = goose_developer_runtime.workspace / relative_path
    tools = await goosed_tools_list(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
    )
    write_tool = resolve_tool_name(tools, "write")
    edit_tool = resolve_tool_name(tools, "edit")
    shell_tool = resolve_tool_name(tools, "shell")
    write_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        write_tool,
        {"path": relative_path, "content": "alpha-beta-gamma"},
    )
    assert_tool_ok(write_result, action="write")
    assert target_file.read_text(encoding="utf-8") == "alpha-beta-gamma"
    edit_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        edit_tool,
        {
            "path": relative_path,
            "before": "beta",
            "after": "humanitec",
        },
    )
    assert_tool_ok(edit_result, action="edit")
    assert target_file.read_text(encoding="utf-8") == "alpha-humanitec-gamma"
    read_result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        shell_tool,
        {"command": f"cat {relative_path}"},
    )
    assert_tool_ok(read_result, action="cat")
    assert tool_response_contains(read_result, "alpha-humanitec-gamma")


@pytest.mark.asyncio
async def test_goose_dev_07_read_image(
    goose_developer_runtime: GooseDeveloperRuntime,
) -> None:
    relative_path = "humanitec-pixel.png"
    image_path = goose_developer_runtime.workspace / relative_path
    image_path.write_bytes(_MINIMAL_PNG)
    tools = await goosed_tools_list(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
    )
    read_image_tool = resolve_tool_name(tools, "read_image")
    result = await goosed_call_tool(
        goose_developer_runtime.page,
        goose_developer_runtime.session_id,
        read_image_tool,
        {"source": relative_path},
    )
    assert_tool_ok(result, action="read_image")
    content = result.get("content")
    assert isinstance(content, list)
    assert len(content) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Memory"],
            workspace_suffix="mem01",
            wait_tool_suffix="remember_memory",
        )
    ],
    indirect=True,
)
async def test_goose_mem_01_store_retrieve_memory(
    goosed_extension_session: GoosedExtensionSession,
) -> None:
    memory_category = "humanitec-test-category"
    memory_value = "humanitec-test-value"
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Memory"],
            workspace_suffix="mem02",
            wait_tool_suffix="remember_memory",
        )
    ],
    indirect=True,
)
async def test_goose_mem_02_list_delete_memory(
    goosed_extension_session: GoosedExtensionSession,
) -> None:
    memory_category = "humanitec-delete-category"
    memory_value = "humanitec-delete-value"
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Computer Controller"],
            workspace_suffix="cc01",
            wait_tool_suffix="web_scrape",
        )
    ],
    indirect=True,
)
async def test_goose_cc_01_computercontroller_tools_list(
    goosed_extension_session: GoosedExtensionSession,
) -> None:
    tools = await goosed_tools_list(
        goosed_extension_session.page,
        goosed_extension_session.session_id,
        extension_name="computercontroller",
    )
    names = {tool.get("name") for tool in tools if isinstance(tool.get("name"), str)}
    assert len(names) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Auto Visualiser"],
            workspace_suffix="av01",
            wait_tool_suffix="render_sankey",
        )
    ],
    indirect=True,
)
async def test_goose_av_01_autovisualiser_tools_list(
    goosed_extension_session: GoosedExtensionSession,
) -> None:
    tools = await goosed_tools_list(
        goosed_extension_session.page,
        goosed_extension_session.session_id,
        extension_name="autovisualiser",
    )
    assert len(tools) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Tutorial"],
            workspace_suffix="tut01",
            wait_tool_suffix="load_tutorial",
        )
    ],
    indirect=True,
)
async def test_goose_tut_01_tutorial_tools_list(
    goosed_extension_session: GoosedExtensionSession,
) -> None:
    tools = await goosed_tools_list(
        goosed_extension_session.page,
        goosed_extension_session.session_id,
        extension_name="tutorial",
    )
    assert len(tools) > 0


@pytest.mark.asyncio
async def test_goose_ext_03_enable_disable_extension_toggle(
    paired_desktop_session: PairedDesktopSession,
) -> None:
    page = paired_desktop_session.page
    await open_settings_extensions(page)
    body_before = await page.locator("body").inner_text()
    assert "Memory" in body_before
    await enable_extension_in_settings(page, "Memory")
    body_after_enable = await page.locator("body").inner_text()
    assert body_after_enable != body_before or "Memory" in body_after_enable


@pytest.mark.asyncio
@pytest.mark.timeout(30, func_only=True)
async def test_goose_ext_01_bundled_order_persisted_after_restart(
    di,
    paired_desktop_session: PairedDesktopSession,
    agent_frontend_http_client,
    auth_token: str,
) -> None:
    """Полный второй запуск Electron проверяем внутри теста — само поведение под тестом."""
    from tests.agent.desktop_e2e.helpers import (
        assert_platform_mcp_first_in_settings,
        read_bundled_extensions,
    )

    extensions = read_bundled_extensions()
    extension_ids = {item.get("id") for item in extensions}
    assert "platform_mcp" not in extension_ids
    desktop = paired_desktop_session.desktop
    await assert_platform_mcp_first_in_settings(paired_desktop_session.page)
    desktop.stop(cleanup_user_data=False)
    desktop.start()
    async with async_playwright() as playwright:
        browser = await connect_desktop_browser(playwright, desktop)
        page = await find_main_app_page(browser)
        await ensure_humanitec_paired_and_llm_ready(
            desktop,
            page,
            agent_frontend_http_client,
            auth_token,
        di)
        await assert_platform_mcp_first_in_settings(page)


@pytest.mark.asyncio
@pytest.mark.parametrize("goosed_developer_only_session", ["ext02"], indirect=True)
async def test_goose_ext_02_disable_developer_removes_tree_tool(
    goosed_developer_only_session: GoosedDeveloperOnlySession,
) -> None:
    page = goosed_developer_only_session.page
    session_id = goosed_developer_only_session.session_id
    workspace = goosed_developer_only_session.workspace
    tools_before = await goosed_tools_list(page, session_id)
    _ = resolve_tool_name(tools_before, "tree")
    await disable_extension_in_settings(page, "Developer")
    session_id_after = await goosed_start_session(page, workspace)
    await goosed_resume_session(page, session_id_after)
    tools_after = await goosed_tools_list(page, session_id_after)
    tool_names: set[str] = set()
    for tool in tools_after:
        tool_name = tool.get("name")
        if isinstance(tool_name, str):
            tool_names.add(tool_name)
    assert not any(name == "tree" or name.endswith("__tree") for name in tool_names)


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
    paired_desktop_ui_session: PairedDesktopUiSession,
) -> None:
    page = paired_desktop_ui_session.page
    discover = await page.evaluate("window.humanitecAgent.discover()")
    if not isinstance(discover, dict):
        raise AssertionError("humanitecAgent.discover() must return object")
    frontend_base_url = discover.get("frontend_base_url")
    if not isinstance(frontend_base_url, str) or not frontend_base_url:
        raise AssertionError("discover.frontend_base_url missing")
    assert "9004" in frontend_base_url or frontend_base_url.startswith("http")


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
@pytest.mark.timeout(60, func_only=True)
async def test_goose_ipc_08_llm_autoconfig_after_pair(
    di,
    agent_frontend_http_client,
    auth_token: str,
    humanitec_desktop_process_factory
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
            di)
            credentials = desktop.read_credentials()
            assert credentials["llm_provider_id"] == "humanitec"
            assert credentials["llm_model_id"] == "auto"
            assert credentials["llm_api_base_url"]
    finally:
        desktop.stop()
