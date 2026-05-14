"""Тесты встроенного tool create_file."""

from __future__ import annotations

from apps.flows.tools.files import _create_file_mock, create_file


def test_create_file_tool_metadata() -> None:
    assert create_file.name == "create_file"
    params = create_file.parameters
    props = params.get("properties", {})
    assert "content" in props
    assert "original_name" in props


def test_create_file_mock() -> None:
    out = _create_file_mock({"original_name": "r.pdf"}, None)
    assert out["success"] is True
    assert out["file_id"]
