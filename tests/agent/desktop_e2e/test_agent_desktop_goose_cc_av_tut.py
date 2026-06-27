"""Desktop E2E: Computer Controller, Auto Visualiser, Tutorial call-level tests."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from tests.agent.desktop_e2e.goosed_helpers import (
    goosed_call_tool,
    goosed_tools_list,
    prepare_goosed_session_with_extensions,
    resolve_tool_name,
    tool_response_contains,
    tool_response_text,
    wait_for_goosed_tools,
)
from tests.agent.desktop_e2e.helpers import connect_desktop_browser, find_main_app_page

_GOOSE_CC_DATA = (
    Path(__file__).resolve().parents[3]
    / "apps/agent/desktop/vendor/goose/crates/goose-mcp/src/computercontroller/tests/data"
)


def _cc_fixture_path(name: str) -> Path:
    source = _GOOSE_CC_DATA / name
    if not source.is_file():
        raise FileNotFoundError(f"computercontroller fixture missing: {source}")
    return source


@pytest.mark.asyncio
async def test_goose_cc_02_web_scrape(
    humanitec_desktop_process_factory,
    frontend_service: None,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    _ = frontend_service
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-cc02"
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
            tools = await goosed_tools_list(page, session_id)
            scrape_tool = resolve_tool_name(tools, "web_scrape")
            result = await goosed_call_tool(
                page,
                session_id,
                scrape_tool,
                {"url": "http://localhost:9004/health", "save_as": "text"},
            )
            assert "Content saved to:" in tool_response_text(result)
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_cc_03_cache_list(
    humanitec_desktop_process_factory,
    frontend_service: None,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    _ = frontend_service
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-cc03"
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
            await wait_for_goosed_tools(page, session_id, name_suffix="cache")
            tools = await goosed_tools_list(page, session_id)
            scrape_tool = resolve_tool_name(tools, "web_scrape")
            cache_tool = resolve_tool_name(tools, "cache")
            await goosed_call_tool(
                page,
                session_id,
                scrape_tool,
                {"url": "http://localhost:9004/health", "save_as": "text"},
            )
            cache_result = await goosed_call_tool(
                page,
                session_id,
                cache_tool,
                {"command": "list"},
            )
            assert "Cached files" in tool_response_text(cache_result)
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_cc_04_pdf_tool(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-cc04"
    pdf_path = workspace / "sample.pdf"
    try:
        desktop.start()
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_cc_fixture_path("test.pdf"), pdf_path)
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
            await wait_for_goosed_tools(page, session_id, name_suffix="pdf_tool")
            tools = await goosed_tools_list(page, session_id)
            pdf_tool = resolve_tool_name(tools, "pdf_tool")
            result = await goosed_call_tool(
                page,
                session_id,
                pdf_tool,
                {"path": str(pdf_path), "operation": "extract_text"},
            )
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_cc_05_docx_tool(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-cc05"
    docx_path = workspace / "sample.docx"
    try:
        desktop.start()
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_cc_fixture_path("sample.docx"), docx_path)
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
            await wait_for_goosed_tools(page, session_id, name_suffix="docx_tool")
            tools = await goosed_tools_list(page, session_id)
            docx_tool = resolve_tool_name(tools, "docx_tool")
            result = await goosed_call_tool(
                page,
                session_id,
                docx_tool,
                {"path": str(docx_path), "operation": "extract_text"},
            )
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_cc_06_xlsx_tool(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-cc06"
    xlsx_path = workspace / "sample.xlsx"
    try:
        desktop.start()
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_cc_fixture_path("FinancialSample.xlsx"), xlsx_path)
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
            await wait_for_goosed_tools(page, session_id, name_suffix="xlsx_tool")
            tools = await goosed_tools_list(page, session_id)
            xlsx_tool = resolve_tool_name(tools, "xlsx_tool")
            result = await goosed_call_tool(
                page,
                session_id,
                xlsx_tool,
                {
                    "path": str(xlsx_path),
                    "operation": "list_worksheets",
                },
            )
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_cc_07_automation_script(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-cc07"
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
            await wait_for_goosed_tools(page, session_id, name_suffix="automation_script")
            tools = await goosed_tools_list(page, session_id)
            script_tool = resolve_tool_name(tools, "automation_script")
            if sys.platform == "darwin":
                script = 'echo "humanitec-automation"'
                language = "shell"
            elif sys.platform == "win32":
                script = 'Write-Output "humanitec-automation"'
                language = "powershell"
            else:
                script = 'echo "humanitec-automation"'
                language = "shell"
            result = await goosed_call_tool(
                page,
                session_id,
                script_tool,
                {"language": language, "script": script, "save_output": False},
            )
            assert tool_response_contains(result, "humanitec-automation")
    finally:
        desktop.stop()


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "darwin", reason="computer_control requires macOS CI")
async def test_goose_cc_08_computer_control(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-cc08"
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
            await wait_for_goosed_tools(page, session_id, name_suffix="computer_control")
            tools = await goosed_tools_list(page, session_id)
            control_tool = resolve_tool_name(tools, "computer_control")
            result = await goosed_call_tool(
                page,
                session_id,
                control_tool,
                {"command": "clipboard --action get", "capture_screenshot": False},
            )
            assert len(tool_response_text(result)) >= 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_av_02_render_sankey(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-av02"
    payload = {
        "data": {
            "nodes": [
                {"name": "Source A", "category": "source"},
                {"name": "Target B", "category": "target"},
            ],
            "links": [{"source": "Source A", "target": "Target B", "value": 100}],
        }
    }
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
            tools = await goosed_tools_list(page, session_id)
            sankey_tool = resolve_tool_name(tools, "render_sankey")
            result = await goosed_call_tool(page, session_id, sankey_tool, payload)
            assert "sankey" in tool_response_text(result).lower()
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_av_03_render_radar(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-av03"
    payload = {
        "data": {
            "labels": ["A", "B", "C"],
            "datasets": [{"label": "Series", "data": [1, 2, 3]}],
        }
    }
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
            tools = await goosed_tools_list(page, session_id)
            radar_tool = resolve_tool_name(tools, "render_radar")
            result = await goosed_call_tool(page, session_id, radar_tool, payload)
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_av_04_render_donut(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-av04"
    payload = {"data": {"labels": ["A", "B"], "values": [60, 40]}}
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
            tools = await goosed_tools_list(page, session_id)
            donut_tool = resolve_tool_name(tools, "render_donut")
            result = await goosed_call_tool(page, session_id, donut_tool, payload)
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_av_05_render_treemap(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-av05"
    payload = {
        "data": {
            "name": "root",
            "children": [{"name": "leaf", "value": 10}],
        }
    }
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
            tools = await goosed_tools_list(page, session_id)
            treemap_tool = resolve_tool_name(tools, "render_treemap")
            result = await goosed_call_tool(page, session_id, treemap_tool, payload)
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_av_06_render_chord(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-av06"
    payload = {
        "data": {
            "matrix": [[0, 1], [1, 0]],
            "labels": ["A", "B"],
        }
    }
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
            tools = await goosed_tools_list(page, session_id)
            chord_tool = resolve_tool_name(tools, "render_chord")
            result = await goosed_call_tool(page, session_id, chord_tool, payload)
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_av_07_render_map(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-av07"
    payload = {
        "data": {
            "points": [{"lat": 55.75, "lon": 37.62, "label": "Moscow", "value": 1}],
        }
    }
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
            tools = await goosed_tools_list(page, session_id)
            map_tool = resolve_tool_name(tools, "render_map")
            result = await goosed_call_tool(page, session_id, map_tool, payload)
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_av_08_render_mermaid(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-av08"
    payload = {"data": {"diagram": "graph TD; A-->B;"}}
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
            tools = await goosed_tools_list(page, session_id)
            mermaid_tool = resolve_tool_name(tools, "render_mermaid")
            result = await goosed_call_tool(page, session_id, mermaid_tool, payload)
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_av_09_show_chart(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-av09"
    payload = {
        "data": {
            "type": "bar",
            "labels": ["A", "B"],
            "datasets": [{"label": "Values", "data": [1, 2]}],
        }
    }
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
            tools = await goosed_tools_list(page, session_id)
            chart_tool = resolve_tool_name(tools, "show_chart")
            result = await goosed_call_tool(page, session_id, chart_tool, payload)
            assert len(tool_response_text(result)) > 0
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_tut_02_load_build_mcp_extension(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-tut02"
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
            tools = await goosed_tools_list(page, session_id)
            tutorial_tool = resolve_tool_name(tools, "load_tutorial")
            result = await goosed_call_tool(
                page,
                session_id,
                tutorial_tool,
                {"name": "build-mcp-extension"},
            )
            text = tool_response_text(result)
            assert "MCP" in text or "tutorial" in text.lower()
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_goose_tut_03_load_first_game(
    humanitec_desktop_process_factory,

    agent_frontend_http_client,
    auth_token: str,
) -> None:
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / "goose-workspace-tut03"
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
            tools = await goosed_tools_list(page, session_id)
            tutorial_tool = resolve_tool_name(tools, "load_tutorial")
            result = await goosed_call_tool(
                page,
                session_id,
                tutorial_tool,
                {"name": "first-game"},
            )
            text = tool_response_text(result)
            assert "game" in text.lower() or "tutorial" in text.lower()
    finally:
        desktop.stop()
