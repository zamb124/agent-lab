"""Push notification config + webhook delivery (A2A 1.0 StreamResponse body)."""

from __future__ import annotations

import uuid

import pytest

from core.a2a.methods import (
    DELETE_TASK_PUSH_NOTIFICATION_CONFIG,
    GET_TASK_PUSH_NOTIFICATION_CONFIG,
    LIST_TASK_PUSH_NOTIFICATION_CONFIGS,
    SEND_MESSAGE,
)
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow
from tests.flows.a2a_conformance.helpers.rpc import post_rpc
from tests.flows.a2a_conformance.helpers.schema import assert_valid_stream_result
from tests.flows.a2a_conformance.helpers.webhook_host import serve_webhook

pytestmark = [pytest.mark.asyncio, pytest.mark.real_taskiq, pytest.mark.timeout(120, func_only=True)]


async def test_push_config_crud_and_webhook_stream_response(
    client, unique_id: str
) -> None:
    """Push регистрируется в SendMessage.configuration до старта task (иначе race с completed)."""
    flow_id = f"a2a_conf_push_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        async with serve_webhook() as webhook:
            context_id = f"ctx-push-{unique_id}"
            send = await post_rpc(
                client,
                flow_id,
                SEND_MESSAGE,
                {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "ROLE_USER",
                        "contextId": context_id,
                        "parts": [{"text": "push-me"}],
                    },
                    "configuration": {
                        "taskPushNotificationConfig": {
                            "url": webhook.url,
                        }
                    },
                },
            )
            assert "error" not in send, send
            task_id = send["result"]["id"]
            assert isinstance(task_id, str) and task_id.strip()

            listed = await post_rpc(
                client,
                flow_id,
                LIST_TASK_PUSH_NOTIFICATION_CONFIGS,
                {"taskId": task_id},
            )
            assert "error" not in listed, listed
            listed_result = listed["result"]
            assert isinstance(listed_result, dict)
            configs = listed_result.get("configs")
            assert isinstance(configs, list) and len(configs) >= 1
            first_config = configs[0]
            assert isinstance(first_config, dict)
            config_id = first_config.get("id")
            assert isinstance(config_id, str) and config_id.strip()

            got = await post_rpc(
                client,
                flow_id,
                GET_TASK_PUSH_NOTIFICATION_CONFIG,
                {"taskId": task_id, "id": config_id},
            )
            assert "error" not in got, got

            payload = await webhook.wait_payload(timeout=20.0)
            assert "method" not in payload or payload.get("method") != "tasks/pushNotification"
            # Payload is StreamResponse ProtoJSON (statusUpdate) or wrapped.
            body = payload.get("result", payload)
            if isinstance(body, dict) and (
                "statusUpdate" in body or "task" in body or "artifactUpdate" in body
            ):
                _ = assert_valid_stream_result(body)
            else:
                # Some deliveries send statusUpdate at top level.
                assert "statusUpdate" in payload or "status" in payload, payload

            deleted = await post_rpc(
                client,
                flow_id,
                DELETE_TASK_PUSH_NOTIFICATION_CONFIG,
                {"taskId": task_id, "id": config_id},
            )
            assert "error" not in deleted or deleted["error"]["code"] in {-32001}, deleted
    finally:
        await delete_flow(client, flow_id)
