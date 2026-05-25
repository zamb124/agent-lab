"""Тесты встроенного tool create_file."""

from __future__ import annotations

import pytest

from apps.flows.tools.files import create_file
from core.state import ExecutionState
from core.types import require_json_object


def test_create_file_tool_metadata() -> None:
    assert create_file.name == "create_file"
    params = create_file.parameters
    props = require_json_object(params.get("properties", {}), "create_file.parameters.properties")
    assert "content" in props
    assert "original_name" in props


@pytest.mark.asyncio
async def test_create_file_rejects_name_without_extension_before_upload() -> None:
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
    )
    out = require_json_object(
        await create_file.run(
            {"content": "report", "original_name": "report", "content_mode": "raw"},
            state,
        ),
        "create_file.result",
    )
    assert out["success"] is False
    assert "расширение" in str(out["error"])
