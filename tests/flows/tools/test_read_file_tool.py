"""Тесты встроенного tool read_file."""

from __future__ import annotations

import pytest

from apps.flows.tools.files import _read_file_mock, read_file
from core.state import ExecutionState


def test_read_file_tool_metadata() -> None:
    assert read_file.name == "read_file"
    assert "read_file" in read_file.description or "Читает" in read_file.description
    params = read_file.parameters
    assert "file_name" in params.get("properties", {})


@pytest.mark.asyncio
async def test_read_file_mock_with_state(tmp_path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
        files=[{"original_name": "a.txt", "url": str(f), "content_type": "text/plain", "file_size": 1}],
    )
    out = _read_file_mock({"file_name": "a.txt"}, state)
    assert out["success"] is True
    assert out["file_name"] == "a.txt"
    assert out["page_count"] == 1


@pytest.mark.asyncio
async def test_read_file_integration_txt(tmp_path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
        files=[{"original_name": "a.txt", "url": str(f), "content_type": "text/plain", "file_size": 5}],
    )
    result = await read_file._run_impl(
        {"file_name": "a.txt", "include_asset_bytes": False},
        state,
    )
    assert result["success"] is True
    assert result["pages"][0]["text"] == "hello"


@pytest.mark.asyncio
async def test_read_file_matches_unicode_combining_marks(tmp_path) -> None:
    actual_name = "Договор наи\u0306ма жилого помещения.txt"
    requested_name = "Договор наи\u030bма жилого помещения.txt"
    f = tmp_path / "contract.txt"
    f.write_text("contract", encoding="utf-8")
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
        files=[{"original_name": actual_name, "url": str(f), "content_type": "text/plain", "file_size": 8}],
    )
    result = await read_file._run_impl(
        {"file_name": requested_name, "include_asset_bytes": False},
        state,
    )
    assert result["success"] is True
    assert result["file_name"] == actual_name
    assert result["pages"][0]["text"] == "contract"
