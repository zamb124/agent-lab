"""Тесты tool fill_docx_template."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.flows.tools.docx_template import fill_docx_template
from core.files.file_ref import FileRef
from core.state import ExecutionState
from core.types import require_json_object


def test_fill_docx_template_metadata() -> None:
    assert fill_docx_template.name == "fill_docx_template"
    props = require_json_object(
        fill_docx_template.parameters.get("properties", {}),
        "fill_docx_template.parameters.properties",
    )
    assert "variables" in props
    assert "output_original_name" in props
    assert "file_name" in props


@pytest.mark.asyncio
async def test_fill_docx_template_no_files() -> None:
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
        files=[],
    )
    out = require_json_object(
        await fill_docx_template.run(
            {"variables": {}, "output_original_name": "out.docx"},
            state,
        ),
        "fill_docx_template.result",
    )
    assert out["success"] is False
    assert "state.files пуст" in str(out["error"])


@pytest.mark.asyncio
async def test_fill_docx_template_bad_output_name(tmp_path: Path) -> None:
    p = tmp_path / "t.docx"
    _ = p.write_bytes(b"PK\x03\x04")
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
        files=[
            FileRef(
                original_name="t.docx",
                url=str(p),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                file_size=4,
            )
        ],
    )
    out = require_json_object(
        await fill_docx_template.run(
            {
                "variables": {},
                "output_original_name": "bad.txt",
                "file_name": "t.docx",
            },
            state,
        ),
        "fill_docx_template.result",
    )
    assert out["success"] is False
