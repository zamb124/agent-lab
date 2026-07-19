"""Part oneof: text / raw / url (fetched) / data."""

from __future__ import annotations

import asyncio
import base64
import uuid

import pytest

from core.a2a.methods import GET_TASK, SEND_MESSAGE
from tests.flows._a2a_v1 import a2a_rpc
from tests.flows.a2a_conformance.helpers.file_host import serve_file
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow
from tests.flows.a2a_conformance.helpers.rpc import post_rpc
from tests.flows.a2a_conformance.helpers.schema import assert_valid_part_dict, assert_valid_task

pytestmark = [pytest.mark.asyncio, pytest.mark.real_taskiq, pytest.mark.timeout(90, func_only=True)]


async def _wait_completed(client, flow_id: str, task_id: str) -> dict[str, object]:
    for _ in range(40):
        envelope = await post_rpc(
            client, flow_id, GET_TASK, {"id": task_id, "historyLength": 5}
        )
        result = envelope.get("result")
        if isinstance(result, dict):
            _ = assert_valid_task(result)
            state = result.get("status", {}).get("state") if isinstance(result.get("status"), dict) else None
            if state in {
                "TASK_STATE_COMPLETED",
                "TASK_STATE_FAILED",
                "TASK_STATE_REJECTED",
            }:
                return result
        await asyncio.sleep(0.25)
    raise AssertionError("task did not complete")


async def test_official_example_parts_parse() -> None:
    import json
    from pathlib import Path

    examples = Path(__file__).resolve().parent / "fixtures" / "official" / "examples"
    for name in ("part_text.json", "part_file_raw.json", "part_file_url.json"):
        payload = json.loads((examples / name).read_text(encoding="utf-8"))
        assert_valid_part_dict(payload)


async def test_part_raw_bytes_accepted(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_raw_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        raw_b64 = base64.b64encode(b"hello-bytes").decode("ascii")
        envelope = await post_rpc(
            client,
            flow_id,
            SEND_MESSAGE,
            {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_USER",
                    "contextId": f"ctx-raw-{unique_id}",
                    "parts": [
                        {"text": "with-file"},
                        {
                            "raw": raw_b64,
                            "filename": "hello.txt",
                            "mediaType": "text/plain",
                        },
                    ],
                }
            },
        )
        assert "error" not in envelope, envelope
        task = assert_valid_task(envelope["result"])
        final = await _wait_completed(client, flow_id, task.id)
        status = final.get("status")
        assert isinstance(status, dict)
        assert status.get("state") == "TASK_STATE_COMPLETED"
    finally:
        await delete_flow(client, flow_id)


async def test_part_url_external_is_fetched(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_url_{unique_id}"
    await create_echo_flow(client, flow_id)
    body = b"remote-file-body"
    try:
        async with serve_file(body=body, content_type="text/plain", path="/doc.txt") as host:
            envelope = await post_rpc(
                client,
                flow_id,
                SEND_MESSAGE,
                {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "ROLE_USER",
                        "contextId": f"ctx-url-{unique_id}",
                        "parts": [
                            {"text": "with-url"},
                            {
                                "url": host.url,
                                "filename": "doc.txt",
                                "mediaType": "text/plain",
                            },
                        ],
                    }
                },
            )
            assert "error" not in envelope, envelope
            task = assert_valid_task(envelope["result"])
            final = await _wait_completed(client, flow_id, task.id)
            status = final.get("status")
            assert isinstance(status, dict)
            assert status.get("state") == "TASK_STATE_COMPLETED"
    finally:
        await delete_flow(client, flow_id)


async def test_send_message_rpc_helper_uses_pascal_case() -> None:
    body = a2a_rpc(
        SEND_MESSAGE,
        {
            "message": {
                "messageId": "m",
                "role": "ROLE_USER",
                "parts": [{"text": "t"}],
            }
        },
        rpc_id=1,
    )
    assert body["method"] == "SendMessage"
