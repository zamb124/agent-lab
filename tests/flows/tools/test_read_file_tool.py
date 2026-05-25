"""Тесты встроенного tool read_file."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.flows.tools.files import read_file
from core.files.file_ref import FileRef
from core.state import ExecutionState
from core.types import require_json_array, require_json_object


def test_read_file_tool_metadata() -> None:
    assert read_file.name == "read_file"
    assert "read_file" in read_file.description or "Читает" in read_file.description
    params = read_file.parameters
    props = require_json_object(params.get("properties", {}), "read_file.parameters.properties")
    assert "file_name" in props


@pytest.mark.asyncio
async def test_read_file_integration_txt(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    _ = f.write_text("hello", encoding="utf-8")
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
        files=[
            FileRef(
                original_name="a.txt",
                url=str(f),
                content_type="text/plain",
                file_size=5,
            )
        ],
    )
    result = require_json_object(
        await read_file.run(
            {"file_name": "a.txt", "include_asset_bytes": False},
            state,
        ),
        "read_file.result",
    )
    assert result["success"] is True
    pages = require_json_array(result["pages"], "read_file.result.pages")
    page = require_json_object(pages[0], "read_file.result.pages[0]")
    assert page["text"] == "hello"


@pytest.mark.asyncio
async def test_read_file_matches_unicode_combining_marks(tmp_path: Path) -> None:
    actual_name = "Договор наи\u0306ма жилого помещения.txt"
    requested_name = "Договор наи\u030bма жилого помещения.txt"
    f = tmp_path / "contract.txt"
    _ = f.write_text("contract", encoding="utf-8")
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
        files=[
            FileRef(
                original_name=actual_name,
                url=str(f),
                content_type="text/plain",
                file_size=8,
            )
        ],
    )
    result = require_json_object(
        await read_file.run(
            {"file_name": requested_name, "include_asset_bytes": False},
            state,
        ),
        "read_file.result",
    )
    assert result["success"] is True
    assert result["file_name"] == actual_name
    pages = require_json_array(result["pages"], "read_file.result.pages")
    page = require_json_object(pages[0], "read_file.result.pages[0]")
    assert page["text"] == "contract"
