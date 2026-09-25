"""
gdocs_* tools via tool.run against Google API emulator.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.flows.src.clients.google_workspace_client import GoogleWorkspaceClient
from apps.flows.tools.google_docs.google_docs import (
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
    client = GoogleWorkspaceClient(oauth_service=AsyncMock(), company_credentials=AsyncMock())
    gdocs_create_document_bound = gdocs_create_document.with_dependencies([client])
    gdocs_append_text_bound = gdocs_append_text.with_dependencies([client])
    gdocs_read_document_bound = gdocs_read_document.with_dependencies([client])
    gdocs_insert_text_bound = gdocs_insert_text.with_dependencies([client])
    gdocs_find_replace_bound = gdocs_find_replace.with_dependencies([client])
    gdocs_delete_range_bound = gdocs_delete_range.with_dependencies([client])
    gdocs_share_document_bound = gdocs_share_document.with_dependencies([client])

    created = _as_payload(
        await gdocs_create_document_bound.run(
            {"title": f"tool-doc-{unique_id}"},
            state,
        )
    )
    doc_id = created["document_id"]
    assert isinstance(doc_id, str)

    _ = _as_payload(
        await gdocs_append_text_bound.run(
            {"document_id": doc_id, "text": "Hello world."},
            state,
        )
    )

    read = _as_payload(
        await gdocs_read_document_bound.run({"document_id": doc_id}, state)
    )
    assert "Hello world." in str(read["text"])

    _ = _as_payload(
        await gdocs_insert_text_bound.run(
            {"document_id": doc_id, "text": "X", "index": 1},
            state,
        )
    )

    _ = _as_payload(
        await gdocs_find_replace_bound.run(
            {"document_id": doc_id, "find": "world", "replace": "planet"},
            state,
        )
    )

    _ = _as_payload(
        await gdocs_delete_range_bound.run(
            {"document_id": doc_id, "start_index": 1, "end_index": 2},
            state,
        )
    )

    _ = _as_payload(
        await gdocs_share_document_bound.run(
            {"document_id": doc_id, "email": "share@example.com", "role": "reader"},
            state,
        )
    )

    _ = _as_payload(
        await gdocs_share_document_bound.run(
            {"document_id": doc_id, "anyone": True, "role": "reader"},
            state,
        )
    )
