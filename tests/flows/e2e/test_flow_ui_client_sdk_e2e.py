"""E2E: платформенный SDK ``FlowUIClient`` против настоящего flows API (granian, 9001).

Клиент — тот же код, который используют интеграции и CRM worker: ``open`` берёт интерфейс,
``send`` ходит текстом или ui-action, ``events``/``state`` читают артефакты Task.
"""

from __future__ import annotations

import json

import pytest
from httpx2 import AsyncClient

from core.clients.flow_ui_client import (
    DEFAULT_BRANCH_ID,
    FlowUIClient,
    FlowUIClientError,
    FlowUIDataEvent,
    FlowUIStateEvent,
    FlowUITextEvent,
)
from core.ui_document.protocol import FlowUIActionMessage

pytestmark = [pytest.mark.e2e, pytest.mark.real_taskiq, pytest.mark.timeout(120, func_only=True)]

FLOWS_BASE_URL = "http://localhost:9001/flows"

INTERFACE = {
    "start_page_id": "main",
    "pages": [
        {
            "page_id": "main",
            "title": "Lead",
            "blocks": [
                {"type": "text_input", "block_id": "name-input", "field": "name", "label": "Имя", "required": True},
                {"type": "button", "block_id": "send", "label": "Отправить", "action": {"name": "submit"}},
                {"type": "text", "block_id": "greeting", "markdown": "{greeting}"},
                {"type": "conversation", "block_id": "conversation"},
            ],
        }
    ],
}

ECHO_CODE = (
    "async def run(args, state):\n"
    "    state['response'] = f\"ECHO:{state.get('content') or ''}\"\n"
    "    state['greeting'] = f\"Hi, {state.get('name') or 'stranger'}\"\n"
    "    return state\n"
)


async def _create_flow(flows_client_http: AsyncClient, auth_headers: dict[str, str], flow_id: str) -> None:
    response = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=auth_headers,
        json={
            "flow_id": flow_id,
            "name": "Flow UI SDK e2e",
            "entry": "main",
            "nodes": {"main": {"type": "code", "code": ECHO_CODE}},
            "edges": [{"from_node": "main", "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_flow_ui_client_open_send_action_and_state(
    flows_client_http: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    flow_id = f"flow_ui_sdk_{unique_id}"
    await _create_flow(flows_client_http, auth_headers_system, flow_id)
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=auth_headers_system, timeout=60.0)
    try:
        assert sdk.branch_id == DEFAULT_BRANCH_ID
        with pytest.raises(FlowUIClientError, match="call open\\(\\) before send"):
            _ = await sdk.send("hi")
        with pytest.raises(FlowUIClientError, match="no task yet"):
            _ = sdk.state

        interface = await sdk.open(context_id=f"ctx-sdk-{unique_id}")
        assert sdk.context_id == f"ctx-sdk-{unique_id}"
        assert interface.flow_id == flow_id
        assert interface.branch_id == DEFAULT_BRANCH_ID
        assert interface.document.start_page_id == "main"
        assert interface.viewer.auth_mode == "platform"
        assert interface.viewer.can_interact is True
        assert interface.look is None
        assert [block.block_id for block in interface.document.pages[0].blocks] == [
            "name-input",
            "send",
            "greeting",
            "conversation",
        ]

        with pytest.raises(FlowUIClientError, match="send requires text, files or action"):
            _ = await sdk.send("   ")

        text_turn = await sdk.send(f"hello-{unique_id}")
        assert text_turn.status == "completed"
        assert f"ECHO:hello-{unique_id}" in text_turn.response
        assert sdk.state == {"greeting": "Hi, stranger"}
        # Ответ code node приходит как обычный артефакт: text Part или data Part без mediaType
        answer_chunks = [
            event.text if isinstance(event, FlowUITextEvent) else json.dumps(event.data, ensure_ascii=False)
            for event in sdk.events()
            if isinstance(event, (FlowUITextEvent, FlowUIDataEvent))
        ]
        assert any(f"ECHO:hello-{unique_id}" in chunk for chunk in answer_chunks), sdk.events()
        state_events = [event for event in sdk.events() if isinstance(event, FlowUIStateEvent)]
        assert state_events and state_events[0].state == {"greeting": "Hi, stranger"}

        action_turn = await sdk.send(
            action=FlowUIActionMessage(action="submit", source="send", fields={"name": f"Ann-{unique_id}"})
        )
        assert action_turn.status == "completed"
        assert action_turn.task["id"] != text_turn.task["id"]
        assert sdk.state == {"name": f"Ann-{unique_id}", "greeting": f"Hi, Ann-{unique_id}"}
        assert len(sdk.tasks) == 2
        assert sdk.events(text_turn.task)[-1] != sdk.events()[-1]

        with pytest.raises(FlowUIClientError, match="cannot be combined with text"):
            _ = await sdk.send("text", action=FlowUIActionMessage(action="submit", source="send"))

        rejected = FlowUIActionMessage(action="submit", source="send", fields={"phone": "+7"})
        with pytest.raises(FlowUIClientError, match="phone"):
            _ = await sdk.send(action=rejected)
        assert len(sdk.tasks) == 2

        with pytest.raises(FlowUIClientError):
            _ = await sdk.cancel(str(action_turn.task["id"]))
    finally:
        _ = await flows_client_http.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)


@pytest.mark.asyncio
async def test_flow_ui_client_open_fails_closed_for_unknown_flow(
    flows_client_http: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = flows_client_http
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=f"missing_{unique_id}", headers=auth_headers_system)
    # Несуществующий flow не раскрывается: authz отвечает 403 до любой попытки прочитать документ
    with pytest.raises(FlowUIClientError, match="failed: 403"):
        _ = await sdk.open()
    assert sdk.interface is None
    assert sdk.context_id is not None
