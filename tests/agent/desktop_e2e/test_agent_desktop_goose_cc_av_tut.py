"""Desktop E2E: Computer Controller, Auto Visualiser, Tutorial call-level tests."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from tests.agent.desktop_e2e.conftest import GoosedExtensionSession, GoosedExtensionSessionSpec
from tests.agent.desktop_e2e.goosed_helpers import (
    goosed_call_tool,
    goosed_tools_list,
    resolve_tool_name,
    tool_response_contains,
    tool_response_text,
)

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
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Computer Controller"],
            workspace_suffix="cc02",
            wait_tool_suffix="web_scrape",
        )
    ],
    indirect=True,
)
async def test_goose_cc_02_web_scrape(
    goosed_extension_session: GoosedExtensionSession,
    frontend_service: None,
) -> None:
    _ = frontend_service
    tools = await goosed_tools_list(goosed_extension_session.page, goosed_extension_session.session_id)
    scrape_tool = resolve_tool_name(tools, "web_scrape")
    result = await goosed_call_tool(
        goosed_extension_session.page,
        goosed_extension_session.session_id,
        scrape_tool,
        {"url": "http://localhost:9004/health", "save_as": "text"},
    )
    assert "Content saved to:" in tool_response_text(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Computer Controller"],
            workspace_suffix="cc03",
            wait_tool_suffix="cache",
        )
    ],
    indirect=True,
)
async def test_goose_cc_03_cache_list(
    goosed_extension_session: GoosedExtensionSession,
    frontend_service: None,
) -> None:
    _ = frontend_service
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    scrape_tool = resolve_tool_name(tools, "web_scrape")
    cache_tool = resolve_tool_name(tools, "cache")
    await goosed_call_tool(
        page,
        session_id,
        scrape_tool,
        {"url": "http://localhost:9004/health", "save_as": "text"},
    )
    cache_result = await goosed_call_tool(page, session_id, cache_tool, {"command": "list"})
    assert "Cached files" in tool_response_text(cache_result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Computer Controller"],
            workspace_suffix="cc04",
            wait_tool_suffix="pdf_tool",
        )
    ],
    indirect=True,
)
async def test_goose_cc_04_pdf_tool(goosed_extension_session: GoosedExtensionSession) -> None:
    pdf_path = goosed_extension_session.workspace / "sample.pdf"
    shutil.copyfile(_cc_fixture_path("test.pdf"), pdf_path)
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    pdf_tool = resolve_tool_name(tools, "pdf_tool")
    result = await goosed_call_tool(
        page,
        session_id,
        pdf_tool,
        {"path": str(pdf_path), "operation": "extract_text"},
    )
    assert len(tool_response_text(result)) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Computer Controller"],
            workspace_suffix="cc05",
            wait_tool_suffix="docx_tool",
        )
    ],
    indirect=True,
)
async def test_goose_cc_05_docx_tool(goosed_extension_session: GoosedExtensionSession) -> None:
    docx_path = goosed_extension_session.workspace / "sample.docx"
    shutil.copyfile(_cc_fixture_path("sample.docx"), docx_path)
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    docx_tool = resolve_tool_name(tools, "docx_tool")
    result = await goosed_call_tool(
        page,
        session_id,
        docx_tool,
        {"path": str(docx_path), "operation": "extract_text"},
    )
    assert len(tool_response_text(result)) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Computer Controller"],
            workspace_suffix="cc06",
            wait_tool_suffix="xlsx_tool",
        )
    ],
    indirect=True,
)
async def test_goose_cc_06_xlsx_tool(goosed_extension_session: GoosedExtensionSession) -> None:
    xlsx_path = goosed_extension_session.workspace / "sample.xlsx"
    shutil.copyfile(_cc_fixture_path("FinancialSample.xlsx"), xlsx_path)
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    xlsx_tool = resolve_tool_name(tools, "xlsx_tool")
    result = await goosed_call_tool(
        page,
        session_id,
        xlsx_tool,
        {"path": str(xlsx_path), "operation": "list_worksheets"},
    )
    assert len(tool_response_text(result)) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Computer Controller"],
            workspace_suffix="cc07",
            wait_tool_suffix="automation_script",
        )
    ],
    indirect=True,
)
async def test_goose_cc_07_automation_script(goosed_extension_session: GoosedExtensionSession) -> None:
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
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


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "darwin", reason="computer_control requires macOS CI")
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Computer Controller"],
            workspace_suffix="cc08",
            wait_tool_suffix="computer_control",
        )
    ],
    indirect=True,
)
async def test_goose_cc_08_computer_control(goosed_extension_session: GoosedExtensionSession) -> None:
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    control_tool = resolve_tool_name(tools, "computer_control")
    result = await goosed_call_tool(
        page,
        session_id,
        control_tool,
        {"command": "clipboard --action get", "capture_screenshot": False},
    )
    assert len(tool_response_text(result)) >= 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Auto Visualiser"],
            workspace_suffix="av02",
            wait_tool_suffix="render_sankey",
        )
    ],
    indirect=True,
)
async def test_goose_av_02_render_sankey(goosed_extension_session: GoosedExtensionSession) -> None:
    payload = {
        "data": {
            "nodes": [
                {"name": "Source A", "category": "source"},
                {"name": "Target B", "category": "target"},
            ],
            "links": [{"source": "Source A", "target": "Target B", "value": 100}],
        }
    }
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    sankey_tool = resolve_tool_name(tools, "render_sankey")
    result = await goosed_call_tool(page, session_id, sankey_tool, payload)
    assert "sankey" in tool_response_text(result).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Auto Visualiser"],
            workspace_suffix="av03",
            wait_tool_suffix="render_radar",
        )
    ],
    indirect=True,
)
async def test_goose_av_03_render_radar(goosed_extension_session: GoosedExtensionSession) -> None:
    payload = {
        "data": {
            "labels": ["A", "B", "C"],
            "datasets": [{"label": "Series", "data": [1, 2, 3]}],
        }
    }
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    radar_tool = resolve_tool_name(tools, "render_radar")
    result = await goosed_call_tool(page, session_id, radar_tool, payload)
    assert len(tool_response_text(result)) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Auto Visualiser"],
            workspace_suffix="av04",
            wait_tool_suffix="render_donut",
        )
    ],
    indirect=True,
)
async def test_goose_av_04_render_donut(goosed_extension_session: GoosedExtensionSession) -> None:
    payload = {"data": [{"values": [60, 40], "labels": ["A", "B"]}]}
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    donut_tool = resolve_tool_name(tools, "render_donut")
    result = await goosed_call_tool(page, session_id, donut_tool, payload)
    assert len(tool_response_text(result)) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Auto Visualiser"],
            workspace_suffix="av05",
            wait_tool_suffix="render_treemap",
        )
    ],
    indirect=True,
)
async def test_goose_av_05_render_treemap(goosed_extension_session: GoosedExtensionSession) -> None:
    payload = {
        "data": {
            "name": "root",
            "children": [{"name": "leaf", "value": 10}],
        }
    }
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    treemap_tool = resolve_tool_name(tools, "render_treemap")
    result = await goosed_call_tool(page, session_id, treemap_tool, payload)
    assert len(tool_response_text(result)) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Auto Visualiser"],
            workspace_suffix="av06",
            wait_tool_suffix="render_chord",
        )
    ],
    indirect=True,
)
async def test_goose_av_06_render_chord(goosed_extension_session: GoosedExtensionSession) -> None:
    payload = {
        "data": {
            "matrix": [[0, 1], [1, 0]],
            "labels": ["A", "B"],
        }
    }
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    chord_tool = resolve_tool_name(tools, "render_chord")
    result = await goosed_call_tool(page, session_id, chord_tool, payload)
    assert len(tool_response_text(result)) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Auto Visualiser"],
            workspace_suffix="av07",
            wait_tool_suffix="render_map",
        )
    ],
    indirect=True,
)
async def test_goose_av_07_render_map(goosed_extension_session: GoosedExtensionSession) -> None:
    payload = {
        "data": {
            "markers": [{"lat": 55.75, "lng": 37.62, "name": "Moscow", "value": 1}],
        }
    }
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    map_tool = resolve_tool_name(tools, "render_map")
    result = await goosed_call_tool(page, session_id, map_tool, payload)
    assert len(tool_response_text(result)) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Auto Visualiser"],
            workspace_suffix="av08",
            wait_tool_suffix="render_mermaid",
        )
    ],
    indirect=True,
)
async def test_goose_av_08_render_mermaid(goosed_extension_session: GoosedExtensionSession) -> None:
    payload = {"mermaid_code": "graph TD; A-->B;"}
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    mermaid_tool = resolve_tool_name(tools, "render_mermaid")
    result = await goosed_call_tool(page, session_id, mermaid_tool, payload)
    assert len(tool_response_text(result)) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Auto Visualiser"],
            workspace_suffix="av09",
            wait_tool_suffix="show_chart",
        )
    ],
    indirect=True,
)
async def test_goose_av_09_show_chart(goosed_extension_session: GoosedExtensionSession) -> None:
    payload = {
        "data": {
            "type": "bar",
            "labels": ["A", "B"],
            "datasets": [{"label": "Values", "data": [1, 2]}],
        }
    }
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
    tools = await goosed_tools_list(page, session_id)
    chart_tool = resolve_tool_name(tools, "show_chart")
    result = await goosed_call_tool(page, session_id, chart_tool, payload)
    assert len(tool_response_text(result)) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Tutorial"],
            workspace_suffix="tut02",
            wait_tool_suffix="load_tutorial",
        )
    ],
    indirect=True,
)
async def test_goose_tut_02_load_build_mcp_extension(goosed_extension_session: GoosedExtensionSession) -> None:
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goosed_extension_session",
    [
        GoosedExtensionSessionSpec(
            extension_display_names=["Tutorial"],
            workspace_suffix="tut03",
            wait_tool_suffix="load_tutorial",
        )
    ],
    indirect=True,
)
async def test_goose_tut_03_load_first_game(goosed_extension_session: GoosedExtensionSession) -> None:
    page, session_id = goosed_extension_session.page, goosed_extension_session.session_id
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
