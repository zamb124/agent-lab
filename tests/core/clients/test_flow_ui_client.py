"""Python SDK Flow UI: URL-схема A2A, сборка хода и декодирование артефактов Task по mediaType.

Задача собирается из той же фикстуры ``ui_artifacts.json``, что читает JS-декодер, — обе стороны
обязаны видеть одинаковые события и один и тот же свёрнутый ``state``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from core.clients.flow_ui_client import (
    FlowUIClient,
    FlowUIClientError,
    FlowUIDataEvent,
    FlowUIFileEvent,
    FlowUIStateEvent,
    FlowUITextEvent,
    a2a_endpoint_url,
    decode_task_events,
    interface_url,
    normalize_branch_id,
    task_state,
    task_text,
    task_ui_events,
)
from core.types import JsonObject, require_json_array, require_json_object
from core.ui_document.protocol import (
    FLOW_UI_MEDIA_TYPE,
    STATE_ARTIFACT_ID,
    UI_ARTIFACT_ID,
    FlowUIActionMessage,
    FlowUINavigate,
    FlowUIRender,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "flow_ui"


def _fixture_parts() -> list[JsonObject]:
    payload = require_json_object(
        cast(object, json.loads((FIXTURES / "ui_artifacts.json").read_text(encoding="utf-8"))),
        "ui_artifacts fixture",
    )
    return [
        require_json_object(part, "parts[]")
        for part in require_json_array(payload["parts"], "parts")
    ]


def _task_from_fixture() -> JsonObject:
    """Task с артефактами ``state`` (snapshot + patch), ``ui`` (render + navigate) и текстом ``response``."""
    parts = _fixture_parts()
    return {
        "id": "task-1",
        "contextId": "ctx-1",
        "status": {"state": "TASK_STATE_COMPLETED"},
        "artifacts": [
            {"artifactId": STATE_ARTIFACT_ID, "parts": parts[:2]},
            {"artifactId": UI_ARTIFACT_ID, "parts": parts[2:4]},
            {"artifactId": "response-1", "name": "response", "parts": [parts[4]]},
            {"artifactId": "response-2", "name": "response", "parts": [{"text": "!"}]},
        ],
    }


class TestUrls:
    def test_endpoint_and_interface_urls_follow_the_a2a_layout(self) -> None:
        assert (
            a2a_endpoint_url("https://acme.linnex.io/flows/", "lead")
            == "https://acme.linnex.io/flows/api/v1/lead"
        )
        assert interface_url("https://acme.linnex.io/flows", "lead", "default").endswith(
            "/api/v1/lead/interface"
        )
        assert interface_url("https://acme.linnex.io/flows", "lead", "beta").endswith(
            "/interface?branch_id=beta"
        )

    def test_branch_base_is_default(self) -> None:
        assert normalize_branch_id("base") == "default"
        assert normalize_branch_id("  ") == "default"
        assert normalize_branch_id("beta") == "beta"

    def test_missing_ids_fail_closed(self) -> None:
        with pytest.raises(FlowUIClientError, match="base_url"):
            _ = a2a_endpoint_url("", "lead")
        with pytest.raises(FlowUIClientError, match="flow_id"):
            _ = a2a_endpoint_url("https://acme.linnex.io/flows", " ")


class TestTaskDecoding:
    def test_events_follow_artifact_order_and_fold_state(self) -> None:
        events = decode_task_events(_task_from_fixture())
        kinds = [event.kind for event in events]
        assert kinds == ["state", "state", "render", "navigate", "text", "text"]
        first, second = events[0], events[1]
        assert isinstance(first, FlowUIStateEvent) and first.state == {
            "email": "a@b.c",
            "total": 1200,
        }
        assert isinstance(second, FlowUIStateEvent) and second.state == {
            "email": "a@b.c",
            "total": 1500,
        }
        render = events[2]
        assert isinstance(render, FlowUIRender) and render.slot_id == "result"
        navigate = events[3]
        assert isinstance(navigate, FlowUINavigate) and navigate.page_id == "done"
        assert [event.text for event in events if isinstance(event, FlowUITextEvent)] == [
            "Готово",
            "!",
        ]

    def test_state_text_and_ui_helpers(self) -> None:
        task = _task_from_fixture()
        assert task_state(task) == {"email": "a@b.c", "total": 1500}
        assert task_text(task, "response") == "Готово!"
        assert task_text(task, "reasoning") == ""
        assert [event.kind for event in task_ui_events(task)] == ["render", "navigate"]

    def test_platform_artifacts_decode_data_and_file_parts(self) -> None:
        """``tool_call:*`` и файловые артефакты читаются как data/file, не ломая текстовые."""
        task: JsonObject = {
            "id": "task-5",
            "artifacts": [
                {
                    "artifactId": "tc-1",
                    "name": "tool_call:call-1",
                    "parts": [{"data": {"tool": "search", "args": {"q": "a2a"}}}],
                },
                {
                    "artifactId": "files-1",
                    "name": "files",
                    "parts": [
                        {
                            "url": "https://files/report.pdf",
                            "mediaType": "application/pdf",
                            "filename": "report.pdf",
                        }
                    ],
                },
                {
                    "artifactId": "response-1",
                    "name": "response",
                    "parts": [{"text": "Го"}, {"text": "тово"}],
                },
            ],
        }
        events = decode_task_events(task)
        assert [event.kind for event in events] == ["data", "file", "text"]
        data_event = events[0]
        assert isinstance(data_event, FlowUIDataEvent)
        assert data_event.name == "tool_call:call-1"
        assert data_event.data == {"tool": "search", "args": {"q": "a2a"}}
        file_event = events[1]
        assert isinstance(file_event, FlowUIFileEvent)
        assert file_event.filename == "report.pdf" and file_event.media_type == "application/pdf"
        assert task_text(task, "response") == "Готово"

    def test_data_part_with_foreign_media_type_is_a_protocol_error(self) -> None:
        task: JsonObject = {
            "id": "task-6",
            "artifacts": [
                {
                    "artifactId": "tc-1",
                    "name": "tool_call:call-1",
                    "parts": [{"data": {"tool": "search"}, "mediaType": "application/x-unknown"}],
                }
            ],
        }
        with pytest.raises(FlowUIClientError, match="unexpected mediaType"):
            _ = decode_task_events(task)
        with pytest.raises(FlowUIClientError, match="requires url"):
            _ = decode_task_events(
                {
                    "id": "task-7",
                    "artifacts": [{"artifactId": "f", "name": "files", "parts": [{"raw": "AAA="}]}],
                }
            )

    def test_patch_before_snapshot_is_a_protocol_error(self) -> None:
        parts = _fixture_parts()
        task: JsonObject = {
            "id": "task-2",
            "artifacts": [{"artifactId": STATE_ARTIFACT_ID, "parts": [parts[1]]}],
        }
        with pytest.raises(FlowUIClientError, match="before state snapshot"):
            _ = decode_task_events(task)

    def test_unknown_media_types_are_rejected(self) -> None:
        task: JsonObject = {
            "id": "task-3",
            "artifacts": [
                {
                    "artifactId": UI_ARTIFACT_ID,
                    "parts": [{"data": {"kind": "render"}, "mediaType": "application/json"}],
                }
            ],
        }
        with pytest.raises(FlowUIClientError, match=FLOW_UI_MEDIA_TYPE.replace("+", r"\+")):
            _ = decode_task_events(task)
        with pytest.raises(FlowUIClientError, match="no state artifact"):
            _ = task_state({"id": "task-4", "artifacts": []})


class TestClientContract:
    @pytest.mark.asyncio
    async def test_send_and_cancel_require_open(self) -> None:
        client = FlowUIClient("https://acme.linnex.io/flows", flow_id="lead")
        assert client.endpoint == "https://acme.linnex.io/flows/api/v1/lead"
        with pytest.raises(FlowUIClientError, match="open"):
            _ = await client.send("hello")
        with pytest.raises(FlowUIClientError, match="open"):
            _ = await client.cancel("task-1")
        with pytest.raises(FlowUIClientError, match="send"):
            _ = client.state
        with pytest.raises(FlowUIClientError, match="send"):
            _ = client.events()

    @pytest.mark.asyncio
    async def test_action_cannot_be_combined_with_text(self) -> None:
        client = FlowUIClient("https://acme.linnex.io/flows", flow_id="lead", branch_id="base")
        client.context_id = "ctx-1"
        action = FlowUIActionMessage(
            action="submit", source="send_button", fields={"email": "a@b.c"}
        )
        with pytest.raises(FlowUIClientError, match="cannot be combined"):
            _ = await client.send("hello", action=action)
        with pytest.raises(FlowUIClientError, match="requires text, files or action"):
            _ = await client.send("   ")
        assert client.branch_id == "default"
