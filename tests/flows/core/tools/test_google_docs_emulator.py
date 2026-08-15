"""
gdocs_* tools via tool.run against Google API emulator.
"""

from __future__ import annotations

import pytest

from apps.flows.tools.google_docs import (
    gdocs_append_text,
    gdocs_create_document,
    gdocs_delete_range,
    gdocs_find_replace,
    gdocs_insert_text,
    gdocs_read_document,
    gdocs_share_document,
)
from core.state import ExecutionState
from core.types import JsonObject, require_json_object
from tests.fixtures.google_api_emulator import GoogleApiEmulatorHandle

_ALL_GDOCS_TOOLS = [
    gdocs_create_document,
    gdocs_read_document,
    gdocs_append_text,
    gdocs_insert_text,
    gdocs_find_replace,
    gdocs_delete_range,
    gdocs_share_document,
]


def _make_state(
    unique_id: str,
    google_api_emulator: GoogleApiEmulatorHandle,
) -> ExecutionState:
    return ExecutionState(
        task_id=f"task-gdocs-emu-{unique_id}",
        context_id=f"ctx-gdocs-emu-{unique_id}",
        user_id="u1",
        session_id=f"flow-gdocs-emu:{unique_id}",
        variables={"google_access_token": google_api_emulator.oauth_token},
    )


def _as_payload(raw: object) -> JsonObject:
    return require_json_object(raw, "gdocs.emulator.tool_result")


def test_all_gdocs_tools_registered() -> None:
    assert {tool.name for tool in _ALL_GDOCS_TOOLS} == {
        "gdocs_create_document",
        "gdocs_read_document",
        "gdocs_append_text",
        "gdocs_insert_text",
        "gdocs_find_replace",
        "gdocs_delete_range",
        "gdocs_share_document",
    }


@pytest.mark.asyncio
async def test_all_gdocs_tools_via_run(
    google_api_emulator: GoogleApiEmulatorHandle,
    unique_id: str,
) -> None:
    state = _make_state(unique_id, google_api_emulator)

    created = _as_payload(
        await gdocs_create_document.run(
            {"title": f"tool-doc-{unique_id}"},
            state,
        )
    )
    doc_id = created["document_id"]
    assert isinstance(doc_id, str)

    appended = _as_payload(
        await gdocs_append_text.run(
            {"document_id": doc_id, "text": "Hello world."},
            state,
        )
    )

    read = _as_payload(
        await gdocs_read_document.run({"document_id": doc_id}, state)
    )
    assert "Hello world." in str(read["text"])

    inserted = _as_payload(
        await gdocs_insert_text.run(
            {"document_id": doc_id, "text": "X", "index": 1},
            state,
        )
    )

    replaced = _as_payload(
        await gdocs_find_replace.run(
            {"document_id": doc_id, "find": "world", "replace": "planet"},
            state,
        )
    )

    deleted = _as_payload(
        await gdocs_delete_range.run(
            {"document_id": doc_id, "start_index": 1, "end_index": 2},
            state,
        )
    )

    shared = _as_payload(
        await gdocs_share_document.run(
            {"document_id": doc_id, "email": "share@example.com", "role": "reader"},
            state,
        )
    )

    anyone = _as_payload(
        await gdocs_share_document.run(
            {"document_id": doc_id, "anyone": True, "role": "reader"},
            state,
        )
    )
