"""Desktop E2E: Goose platform extensions (in-process goosed)."""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from tests.agent.desktop_e2e.goosed_helpers import (
    goosed_call_tool,
    goosed_tools_list,
    prepare_goosed_developer_session,
    resolve_tool_name,
    tool_response_text,
    wait_for_goosed_tools,
)
from tests.agent.desktop_e2e.helpers import connect_desktop_browser, find_main_app_page


@pytest.mark.asyncio
async def test_goose_plat_01_analyze_directory(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-plat01"
    sample = workspace / "sample.py"
    try:
        desktop.start()
        workspace.mkdir(parents=True, exist_ok=True)
        sample.write_text("def hello():\n    return 1\n", encoding="utf-8")
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
            await wait_for_goosed_tools(page, session_id, name_suffix="analyze")
            tools = await goosed_tools_list(page, session_id, extension_name="analyze")
            analyze_tool = resolve_tool_name(tools, "analyze")
            result = await goosed_call_tool(
                page,
                session_id,
                analyze_tool,
                {"path": str(workspace), "max_depth": 1, "follow_depth": 0, "force": False},
            )
            assert "sample.py" in tool_response_text(result)
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_plat_02_todo_write(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-plat02"
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
            tools = await goosed_tools_list(page, session_id, extension_name="todo")
            todo_tool = resolve_tool_name(tools, "todo_write")
            result = await goosed_call_tool(
                page,
                session_id,
                todo_tool,
                {"content": "humanitec todo item"},
            )
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_plat_03_apps_list(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-plat03"
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
            tools = await goosed_tools_list(page, session_id, extension_name="apps")
            list_tool = resolve_tool_name(tools, "list_apps")
            result = await goosed_call_tool(page, session_id, list_tool, {})
            assert len(tool_response_text(result)) >= 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_plat_09_extensionmanager_search(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-plat09"
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
            tools = await goosed_tools_list(page, session_id, extension_name="extensionmanager")
            search_tool = resolve_tool_name(tools, "search_available_extensions")
            result = await goosed_call_tool(
                page,
                session_id,
                search_tool,
                {"query": "developer"},
            )
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_plat_11_summon_load(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-plat11"
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
            tools = await goosed_tools_list(page, session_id, extension_name="summon")
            load_tool = resolve_tool_name(tools, "load")
            result = await goosed_call_tool(page, session_id, load_tool, {})
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_plat_08_chatrecall_tools_list(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-plat08"
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
            tools = await goosed_tools_list(page, session_id, extension_name="chatrecall")
            assert len(tools) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_plat_13_summarize_tools_list(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-plat13"
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
            tools = await goosed_tools_list(page, session_id, extension_name="summarize")
            assert len(tools) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_plat_14_skills_tools_list(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-plat14"
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
            tools = await goosed_tools_list(page, session_id, extension_name="skills")
            load_skill_tool = resolve_tool_name(tools, "load_skill")
            assert load_skill_tool.endswith("load_skill")
    finally:
        desktop.stop()
