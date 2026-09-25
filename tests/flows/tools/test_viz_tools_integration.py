"""Integration: viz tools persist .viz to real S3 via FileWriter (flows lifespan)."""

from __future__ import annotations

import json

import pytest

from apps.flows.tools.viz.viz import create_viz, export_viz, update_viz, viz_open_file
from core.clients.files_client import FilesClient
from core.state import ExecutionState
from core.types import require_json_object
from core.viz.models import VIZ_CONTENT_TYPE, VizDocument, parse_viz_document_bytes
from tests.fixtures.s3 import require_s3_configured

pytestmark = [pytest.mark.asyncio]


def _execution_state(unique_id: str) -> ExecutionState:
    return ExecutionState.create(
        task_id=f"viz-task-{unique_id}",
        context_id=f"viz-ctx-{unique_id}",
        user_id="test_user",
        session_id=f"viz-flow:{unique_id}",
        files=[],
    )


def _file_ids(state: ExecutionState) -> list[str]:
    return [item.file_id for item in state.files if item.file_id]


async def _assert_viz_on_s3(di, file_id: str) -> VizDocument:
    record = await di.files_service.get(file_id)
    assert record.content_type == VIZ_CONTENT_TYPE
    assert record.original_name.endswith(".viz")
    raw = await FilesClient().get_bytes(file_id)
    document = parse_viz_document_bytes(raw)
    assert document.schema_version == 1
    return document


async def test_create_viz_mermaid_persists(app, di, unique_id: str) -> None:
    _ = app
    require_s3_configured()
    state = _execution_state(unique_id)
    title = f"Funnel {unique_id}"
    source = "flowchart TD\n  A[Start]-->B[End]"
    out = require_json_object(
        await create_viz.run(
            {"kind": "flowchart", "title": title, "source": source},
            state,
        ),
        "create_viz.result",
    )
    assert out["success"] is True
    assert out["content_type"] == VIZ_CONTENT_TYPE
    blocks_raw = out["blocks"]
    assert isinstance(blocks_raw, list) and len(blocks_raw) == 1
    block = require_json_object(blocks_raw[0], "create_viz.blocks[0]")
    assert block["type"] == "viz"
    assert block["kind"] == "flowchart"
    assert block["engine"] == "mermaid"
    assert block["title"] == title
    file_payload = require_json_object(out["file"], "create_viz.file")
    file_id = file_payload["file_id"]
    assert isinstance(file_id, str) and file_id
    assert file_id in _file_ids(state)
    document = await _assert_viz_on_s3(di, file_id)
    assert document.kind.value == "flowchart"
    assert document.engine.value == "mermaid"
    assert document.title == title
    assert document.spec.get("source") == source


async def test_create_viz_echarts_persists(app, di, unique_id: str) -> None:
    _ = app
    require_s3_configured()
    state = _execution_state(unique_id)
    title = f"Bars {unique_id}"
    option = {
        "xAxis": {"type": "category", "data": ["A", "B"]},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": [1, 2]}],
    }
    out = require_json_object(
        await create_viz.run(
            {"kind": "chart", "title": title, "option": option},
            state,
        ),
        "create_viz.result",
    )
    assert out["success"] is True
    blocks_raw = out["blocks"]
    assert isinstance(blocks_raw, list) and len(blocks_raw) == 1
    block = require_json_object(blocks_raw[0], "create_viz.blocks[0]")
    assert block["type"] == "viz"
    assert block["engine"] == "echarts"
    file_id = require_json_object(out["file"], "create_viz.file")["file_id"]
    assert isinstance(file_id, str)
    document = await _assert_viz_on_s3(di, file_id)
    assert document.engine.value == "echarts"
    assert document.spec.get("option") == option


async def test_create_viz_rejects_invalid(app, unique_id: str) -> None:
    _ = app
    state = _execution_state(unique_id)
    with pytest.raises(ValueError, match="source|mermaid"):
        _ = await create_viz.run(
            {"kind": "flowchart", "title": f"Bad {unique_id}", "source": ""},
            state,
        )
    assert state.files == []


async def test_update_viz_creates_new_version(app, di, unique_id: str) -> None:
    _ = app
    require_s3_configured()
    state = _execution_state(unique_id)
    created = require_json_object(
        await create_viz.run(
            {
                "kind": "flowchart",
                "title": f"V1 {unique_id}",
                "source": "flowchart TD\n  A-->B",
            },
            state,
        ),
        "create_viz.result",
    )
    assert created["success"] is True
    previous_file_id = require_json_object(created["file"], "create_viz.file")["file_id"]
    assert isinstance(previous_file_id, str)
    new_source = "flowchart TD\n  A-->B-->C"
    updated = require_json_object(
        await update_viz.run(
            {"file_id": previous_file_id, "source": new_source, "title": f"V2 {unique_id}"},
            state,
        ),
        "update_viz.result",
    )
    assert updated["success"] is True
    assert updated["previous_file_id"] == previous_file_id
    new_file_id = require_json_object(updated["file"], "update_viz.file")["file_id"]
    assert isinstance(new_file_id, str)
    assert new_file_id != previous_file_id
    assert new_file_id in _file_ids(state)
    document = await _assert_viz_on_s3(di, new_file_id)
    assert document.title == f"V2 {unique_id}"
    assert document.spec.get("source") == new_source
    old_body = await FilesClient().get_bytes(previous_file_id)
    new_body = await FilesClient().get_bytes(new_file_id)
    assert old_body != new_body


async def test_export_viz_svg_and_json(app, di, unique_id: str) -> None:
    _ = app
    require_s3_configured()
    state = _execution_state(unique_id)
    title = f"ExportMe {unique_id}"
    created = require_json_object(
        await create_viz.run(
            {
                "kind": "flowchart",
                "title": title,
                "source": "flowchart TD\n  X-->Y",
            },
            state,
        ),
        "create_viz.result",
    )
    file_id = require_json_object(created["file"], "create_viz.file")["file_id"]
    assert isinstance(file_id, str)

    svg_out = require_json_object(
        await export_viz.run({"file_id": file_id, "format": "svg"}, state),
        "export_viz.svg",
    )
    assert svg_out["success"] is True
    assert svg_out["format"] == "svg"
    svg_file_id = require_json_object(svg_out["file"], "export_viz.svg.file")["file_id"]
    assert isinstance(svg_file_id, str)
    assert svg_file_id in _file_ids(state)
    svg_bytes = await FilesClient().get_bytes(svg_file_id)
    svg_text = svg_bytes.decode("utf-8")
    assert title in svg_text
    assert "<svg" in svg_text

    json_out = require_json_object(
        await export_viz.run({"file_id": file_id, "format": "json"}, state),
        "export_viz.json",
    )
    assert json_out["success"] is True
    assert json_out["format"] == "json"
    json_file_id = require_json_object(json_out["file"], "export_viz.json.file")["file_id"]
    assert isinstance(json_file_id, str)
    json_bytes = await FilesClient().get_bytes(json_file_id)
    document = VizDocument.model_validate(json.loads(json_bytes.decode("utf-8")))
    assert document.title == title
    _ = await di.files_service.get(json_file_id)


async def test_viz_open_file_returns_blocks(app, di, unique_id: str) -> None:
    _ = app
    require_s3_configured()
    state = _execution_state(unique_id)
    created = require_json_object(
        await create_viz.run(
            {
                "kind": "sequence",
                "title": f"Open {unique_id}",
                "source": "sequenceDiagram\n  Alice->>Bob: Hi",
            },
            state,
        ),
        "create_viz.result",
    )
    file_id = require_json_object(created["file"], "create_viz.file")["file_id"]
    assert isinstance(file_id, str)
    files_before = list(_file_ids(state))
    opened = require_json_object(
        await viz_open_file.run({"file_id": file_id}, state),
        "viz_open_file.result",
    )
    assert opened["success"] is True
    assert opened["content_type"] == VIZ_CONTENT_TYPE
    blocks_raw = opened["blocks"]
    assert isinstance(blocks_raw, list) and len(blocks_raw) == 1
    block = require_json_object(blocks_raw[0], "viz_open_file.blocks[0]")
    assert block["type"] == "viz"
    assert block["file_id"] == file_id
    assert _file_ids(state) == files_before
    _ = await _assert_viz_on_s3(di, file_id)
