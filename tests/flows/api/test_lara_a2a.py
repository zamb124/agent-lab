"""A2A contract for Lara: stream path, skill load, real domain tool."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable

import pytest

from apps.flows.src.container import FlowContainer
from apps.flows.src.runtime.nodes import LlmNode
from apps.flows.src.services.platform_assistant_skills import (
    LARA_PLATFORM_SKILL_ROOTS,
    PLATFORM_ASSISTANT_SEED_SKILL_IDS,
    seed_platform_assistant_skills,
)
from core.clients.llm.mock import MockLLM, MockLLMQueuedResponse
from core.context import clear_context, get_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from tests.fixtures.crm_test_setup import wait_for_crm_semantic_search_hit
from tests.flows.agent_skills_harness import ensure_lara_flow

MockLLMQueue = Callable[[list[MockLLMQueuedResponse]], MockLLM]


def _message(text: str, context_id: str) -> dict[str, object]:
    return {
        "messageId": str(uuid.uuid4()),
        "role": "ROLE_USER",
        "parts": [{"text": text}],
        "contextId": context_id,
    }


def _parse_sse(text: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            continue
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise AssertionError("SSE data frame must be an object")
        events.append(parsed)
    return events


def _event_state(event: dict[str, object]) -> str:
    result = event.get("result")
    if not isinstance(result, dict):
        return ""
    status_update = result.get("statusUpdate")
    if not isinstance(status_update, dict):
        return ""
    status = status_update.get("status")
    if not isinstance(status, dict):
        return ""
    state = status.get("state")
    return state if isinstance(state, str) else ""


def _events_text(events: list[dict[str, object]]) -> str:
    return json.dumps(events, ensure_ascii=False)


@pytest.mark.asyncio
async def test_lara_a2a_stream_loads_skill_and_runs_crm_tool(
    client,
    container: FlowContainer,
    crm_service,
    crm_client,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = crm_service
    marker = f"lara_a2a_crm_marker_{unique_id}"
    created = await crm_client.post(
        "/crm/api/v1/entities",
        json={
            "entity_type": "organization",
            "name": f"Lara A2A Org {unique_id}",
            "description": f"A2A CRM marker {marker} " + ("context " * 40),
            "namespace": "default",
        },
        headers=auth_headers_system,
    )
    assert created.status_code in (200, 201), created.text
    await wait_for_crm_semantic_search_hit(
        crm_client,
        auth_headers_system,
        query=marker,
        entity_type="organization",
        namespace="default",
    )

    previous = get_context()
    set_context(
        Context(
            user=User(user_id=system_user_id, name="Lara A2A seed"),
            active_company=Company(company_id="system", name="System"),
            auth_token=auth_token_system,
            channel="test",
            active_namespace="default",
            metadata={"user_id": system_user_id, "email": "test@example.com", "grps": []},
        )
    )
    try:
        loaded = await ensure_lara_flow(container)
        seeded = await seed_platform_assistant_skills(
            container.agent_skill_service,
            container.files_service,
            "system",
        )
        assert seeded == len(PLATFORM_ASSISTANT_SEED_SKILL_IDS)
        flow = await container.flow_factory.get_flow("lara", branch_id="crm")
        assert flow is not None
        main_node = flow.nodes["main"]
        assert isinstance(main_node, LlmNode)
        assert main_node.agent_skill_ids == list(LARA_PLATFORM_SKILL_ROOTS)
        pre_tools = {tool.name for tool in await main_node.get_tools(None)}
        assert "load_agent_skill" in pre_tools, pre_tools
        assert "ask_user" in pre_tools
        _ = loaded
    finally:
        clear_context()
        if previous is not None:
            set_context(previous)

    _ = mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "networkle"}},
            {"type": "tool_call", "tool": "load_agent_skill", "args": {"agent_skill_id": "crm-entities"}},
            {
                "type": "tool_call",
                "tool": "crm_search_entities",
                "args": {
                    "query": marker,
                    "entity_type": "organization",
                    "namespace": "default",
                    "limit": 5,
                },
            },
            {"type": "text", "content": f"A2A found {marker}"},
        ]
    )
    context_id = f"lara-a2a-{unique_id}"
    response = await client.post(
        "/flows/api/v1/lara",
        headers=auth_headers_system,
        json={
            "jsonrpc": "2.0",
            "id": f"lara-a2a-{unique_id}",
            "method": "SendStreamingMessage",
            "params": {
                "message": _message(f"Find {marker}", context_id),
                "metadata": {"branch": "crm"},
            },
        },
    )
    assert response.status_code == 200, response.text
    assert "text/event-stream" in response.headers.get("content-type", "")
    events = _parse_sse(response.text)
    events_text = _events_text(events)
    assert any(_event_state(event) == "TASK_STATE_COMPLETED" for event in events), events_text
    assert "platform.skill_loaded" in events_text
    assert "crm_search_entities" in events_text
    assert marker in events_text
