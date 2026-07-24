"""Inbound HTTP webhook trigger: secret_header, envelope, TriggerExecutor e2e."""

import asyncio

import pytest

from apps.flows.src.models import FlowConfig, TriggerConfig, TriggerType
from apps.flows.src.models.channel_config import OutputAction
from apps.flows.src.models.enums import ChannelType
from apps.flows.src.triggers.input_mapper import InputMapper
from core.types import require_json_object


async def _await_completed_state(container, session_id: str, *, timeout_sec: float = 20.0):
    deadline = asyncio.get_running_loop().time() + timeout_sec
    last_state = None
    while asyncio.get_running_loop().time() < deadline:
        last_state = await container.workflow_runtime.get_state(session_id)
        if last_state is not None and last_state.terminal_task_state == "completed":
            return last_state
        await asyncio.sleep(0.1)
    raise AssertionError(
        f"session {session_id!r} not completed in {timeout_sec}s; "
        f"last_state={last_state!r} terminal={getattr(last_state, 'terminal_task_state', None)!r}"
    )


@pytest.mark.asyncio
async def test_generic_webhook_requires_secret_header(app, client, container, unique_id):
    """Без секрета / wrong → 403; верный X-Trigger-Secret → 202."""
    flow_id = f"wh_sec_{unique_id}"
    trigger = TriggerConfig(
        trigger_id="gh",
        name="G",
        type=TriggerType.WEBHOOK,
        enabled=True,
        config={"secret_token": "my-shared-secret"},
        output_mapping={"content": "body.text"},
    )
    agent = FlowConfig(
        flow_id=flow_id,
        name="Test Agent",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
        triggers={"gh": trigger},
    )
    await container.flow_repository.set(agent)

    r1 = await client.post(
        f"/flows/api/v1/triggers/webhook/{flow_id}/gh",
        json={"text": "hi"},
    )
    assert r1.status_code == 403

    r2 = await client.post(
        f"/flows/api/v1/triggers/webhook/{flow_id}/gh",
        json={"text": "hi"},
        headers={"X-Trigger-Secret": "wrong"},
    )
    assert r2.status_code == 403

    r3 = await client.post(
        f"/flows/api/v1/triggers/webhook/{flow_id}/gh",
        json={"text": "hi"},
        headers={"X-Trigger-Secret": "my-shared-secret"},
    )
    assert r3.status_code == 202
    body = require_json_object(r3.json(), "webhook response")
    assert body["status"] == "accepted"
    assert isinstance(body["task_id"], str) and body["task_id"].strip()
    assert isinstance(body["session_id"], str) and body["session_id"].startswith(f"{flow_id}:")
    assert isinstance(body["context_id"], str) and body["context_id"].strip()

    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_generic_webhook_custom_secret_header_and_query(
    app, client, container, unique_id
):
    """Кастомный secret_header и fallback ?secret=."""
    flow_id = f"wh_hdr_{unique_id}"
    secret = f"sec_{unique_id}"
    trigger = TriggerConfig(
        trigger_id="wh",
        name="Custom header",
        type=TriggerType.WEBHOOK,
        enabled=True,
        config={
            "secret_token": secret,
            "secret_header": "X-Hub-Token",
        },
        output_mapping={"content": "body.text"},
    )
    agent = FlowConfig(
        flow_id=flow_id,
        name="Webhook Header Agent",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
        triggers={"wh": trigger},
    )
    await container.flow_repository.set(agent)

    denied = await client.post(
        f"/flows/api/v1/triggers/webhook/{flow_id}/wh",
        json={"text": "nope"},
        headers={"X-Trigger-Secret": secret},
    )
    assert denied.status_code == 403

    ok_header = await client.post(
        f"/flows/api/v1/triggers/webhook/{flow_id}/wh",
        json={"text": "via-header"},
        headers={"X-Hub-Token": secret},
    )
    assert ok_header.status_code == 202

    ok_query = await client.post(
        f"/flows/api/v1/triggers/webhook/{flow_id}/wh?secret={secret}",
        json={"text": "via-query"},
    )
    assert ok_query.status_code == 202

    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_generic_webhook_allowed_ips_deny(app, client, container, unique_id):
    """Непустой allowed_ips отклоняет host TestClient (не IP)."""
    flow_id = f"wh_ip_{unique_id}"
    trigger = TriggerConfig(
        trigger_id="wh",
        name="IP filter",
        type=TriggerType.WEBHOOK,
        enabled=True,
        config={"allowed_ips": ["203.0.113.10"]},
        output_mapping={"content": "body.text"},
    )
    agent = FlowConfig(
        flow_id=flow_id,
        name="Webhook IP Agent",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
        triggers={"wh": trigger},
    )
    await container.flow_repository.set(agent)

    response = await client.post(
        f"/flows/api/v1/triggers/webhook/{flow_id}/wh",
        json={"text": "blocked"},
    )
    assert response.status_code == 403
    assert "IP" in response.json()["detail"]

    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_generic_webhook_persists_secret_header_and_ips(
    app, client, container, unique_id
):
    """API create сохраняет secret_header и allowed_ips как list."""
    flow_id = f"wh_persist_{unique_id}"
    agent = FlowConfig(
        flow_id=flow_id,
        name="Persist Agent",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Test"}},
    )
    await container.flow_repository.set(agent)

    create = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": "wh_persist",
            "name": "Persist Webhook",
            "type": "webhook",
            "enabled": True,
            "config": {
                "secret_token": "tok",
                "secret_header": "Authorization",
                "allowed_ips": ["127.0.0.1", "10.0.0.0/8"],
            },
            "output_mapping": {"content": "body.text"},
        },
    )
    assert create.status_code == 200
    created = require_json_object(create.json(), "create trigger")
    assert created["type"] == "webhook"
    assert created["status"] == "active"
    assert created["webhook_url"] is not None

    saved = await container.flow_repository.get(flow_id)
    assert saved is not None
    trigger = saved.triggers["wh_persist"]
    assert trigger.config["secret_header"] == "Authorization"
    assert trigger.config["allowed_ips"] == ["127.0.0.1", "10.0.0.0/8"]
    assert trigger.webhook_url is not None

    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_generic_webhook_e2e_envelope_and_mapping(
    app, client, container, unique_id, mock_llm_with_queue
):
    """POST → 202 → flow: envelope body/headers/query + content из mapping."""
    mock_llm_with_queue(["Webhook ok"])
    flow_id = f"wh_e2e_{unique_id}"
    trigger = TriggerConfig(
        trigger_id="warehouse",
        name="Warehouse",
        type=TriggerType.WEBHOOK,
        enabled=True,
        config={"secret_token": f"e2e_{unique_id}"},
        output_mapping={
            "content": "body.text",
            "context.event": "headers.X-Event",
            "context.ref": "query.ref",
        },
    )
    agent = FlowConfig(
        flow_id=flow_id,
        name="Webhook E2E Agent",
        entry="main",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "Событие: {content}",
            }
        },
        triggers={"warehouse": trigger},
    )
    await container.flow_repository.set(agent)

    response = await client.post(
        f"/flows/api/v1/triggers/webhook/{flow_id}/warehouse?ref=order-42",
        json={"text": "stock-updated"},
        headers={
            "X-Trigger-Secret": f"e2e_{unique_id}",
            "X-Event": "inventory.changed",
        },
    )
    assert response.status_code == 202
    data = require_json_object(response.json(), "webhook e2e response")
    assert data["status"] == "accepted"
    assert isinstance(data["task_id"], str) and data["task_id"].strip()
    assert isinstance(data["session_id"], str) and data["session_id"].startswith(f"{flow_id}:")
    assert isinstance(data["context_id"], str) and data["context_id"].strip()

    mapped = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers/warehouse/test",
        json={
            "body": {"text": "stock-updated"},
            "headers": {"X-Event": "inventory.changed"},
            "query": {"ref": "order-42"},
        },
    )
    assert mapped.status_code == 200
    mapped_body = require_json_object(mapped.json(), "trigger test")
    assert mapped_body["status"] == "ok"
    mapped_data = require_json_object(mapped_body["mapped_data"], "mapped_data")
    assert mapped_data["content"] == "stock-updated"
    triggers = require_json_object(mapped_data["triggers"], "triggers")
    snap = require_json_object(triggers["warehouse"], "warehouse snap")
    context = require_json_object(snap["context"], "context")
    assert context["event"] == "inventory.changed"
    assert context["ref"] == "order-42"

    # Hyphenated header path must resolve through InputMapper (Bot/webhook headers).
    mapped_direct = InputMapper().map(
        "warehouse",
        {
            "body": {"text": "stock-updated"},
            "headers": {"x-event": "inventory.changed"},
            "query": {"ref": "order-42"},
        },
        {
            "content": "body.text",
            "context.event": "headers.X-Event",
            "context.ref": "query.ref",
        },
    )
    assert mapped_direct["content"] == "stock-updated"
    direct_triggers = require_json_object(mapped_direct["triggers"], "direct triggers")
    direct_snap = require_json_object(direct_triggers["warehouse"], "direct snap")
    direct_ctx = require_json_object(direct_snap["context"], "direct context")
    assert direct_ctx["event"] == "inventory.changed"

    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_generic_webhook_awaits_completed_state(
    app, client, container, unique_id, mock_llm_with_queue
):
    """POST → 202 session_id → workflow_runtime.get_state → completed + mapping snapshot."""
    mock_llm_with_queue(["Webhook completed"])
    flow_id = f"wh_done_{unique_id}"
    secret = f"done_{unique_id}"
    trigger = TriggerConfig(
        trigger_id="done",
        name="Done",
        type=TriggerType.WEBHOOK,
        enabled=True,
        config={"secret_token": secret},
        output_mapping={
            "content": "body.text",
            "context.ref": "query.ref",
        },
        post_flow_output_enabled=False,
    )
    agent = FlowConfig(
        flow_id=flow_id,
        name="Webhook Completed Agent",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
        triggers={"done": trigger},
    )
    await container.flow_repository.set(agent)

    response = await client.post(
        f"/flows/api/v1/triggers/webhook/{flow_id}/done?ref=abc",
        json={"text": "payload-text"},
        headers={"X-Trigger-Secret": secret},
    )
    assert response.status_code == 202
    body = require_json_object(response.json(), "webhook completed response")
    session_id = body["session_id"]
    assert isinstance(session_id, str)

    state = await _await_completed_state(container, session_id)
    assert state.content == "payload-text"
    snap = state.triggers["done"]
    assert snap.context["ref"] == "abc"
    assert state.response == "Webhook completed"

    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_generic_webhook_output_action_callback(
    app, client, container, unique_id, mock_llm_with_queue, notification_server
):
    """Inbound webhook → completed → output_actions webhook callback на NotificationServer."""
    (server, base_url) = notification_server
    mock_llm_with_queue(["Callback ready"])
    flow_id = f"wh_cb_{unique_id}"
    secret = f"cb_{unique_id}"
    output_action = OutputAction(
        channel=ChannelType.WEBHOOK,
        action="send_message",
        mapping={
            "recipient": f"@const:{base_url}/notify",
            "text": "@state:response",
        },
    )
    trigger = TriggerConfig(
        trigger_id="cb",
        name="Callback",
        type=TriggerType.WEBHOOK,
        enabled=True,
        config={"secret_token": secret},
        output_mapping={"content": "body.text"},
        output_actions=[output_action],
        post_flow_output_enabled=True,
    )
    agent = FlowConfig(
        flow_id=flow_id,
        name="Webhook Callback Agent",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
        triggers={"cb": trigger},
    )
    await container.flow_repository.set(agent)
    server.clear()

    response = await client.post(
        f"/flows/api/v1/triggers/webhook/{flow_id}/cb",
        json={"text": "fire"},
        headers={"X-Trigger-Secret": secret},
    )
    assert response.status_code == 202
    body = require_json_object(response.json(), "webhook callback response")
    session_id = body["session_id"]
    assert isinstance(session_id, str)

    state = await _await_completed_state(container, session_id)
    assert state.terminal_task_state == "completed"
    assert state.response == "Callback ready"

    notify: list[object] = []
    for _ in range(50):
        notify = server.get_requests("notify")
        if len(notify) >= 1:
            break
        await asyncio.sleep(0.1)
    assert len(notify) >= 1, f"no notify; got={server.received_requests!r}"
    last = notify[-1]
    assert isinstance(last, dict)
    assert last["data"]["text"] == "Callback ready"

    await container.flow_repository.delete(flow_id)
