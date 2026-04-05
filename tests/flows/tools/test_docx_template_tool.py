"""Тесты tool fill_docx_template."""

from __future__ import annotations

import pytest

from apps.flows.tools.docx_template import _fill_docx_mock, fill_docx_template


def test_fill_docx_template_metadata() -> None:
    assert fill_docx_template.name == "fill_docx_template"
    props = fill_docx_template.parameters.get("properties", {})
    assert "variables" in props
    assert "output_original_name" in props
    assert "file_name" in props


def test_fill_docx_mock() -> None:
    out = _fill_docx_mock({"output_original_name": "x.docx"}, None)
    assert out["success"] is True
    assert out["file_id"]


@pytest.mark.asyncio
async def test_fill_docx_template_no_files(monkeypatch) -> None:
    monkeypatch.delenv("TESTING", raising=False)
    from core.state import ExecutionState

    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
        files=[],
    )
    out = await fill_docx_template.run(
        {"variables": {}, "output_original_name": "out.docx"},
        state,
    )
    assert out["success"] is False
    assert "Нет файлов" in out["error"]


@pytest.mark.asyncio
async def test_fill_docx_template_bad_output_name(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TESTING", raising=False)
    from core.state import ExecutionState

    p = tmp_path / "t.docx"
    p.write_bytes(b"PK\x03\x04")
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
        files=[{"name": "t.docx", "path": str(p)}],
    )
    out = await fill_docx_template.run(
        {
            "variables": {},
            "output_original_name": "bad.txt",
            "file_name": "t.docx",
        },
        state,
    )
    assert out["success"] is False
