"""Deterministic code_node flows for A2A conformance (no MockLLM)."""

from __future__ import annotations

from typing import Any

from tests.flows._a2a_v1 import A2A_HEADERS


async def create_echo_flow(client: Any, flow_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        headers=A2A_HEADERS,
        json={
            "flow_id": flow_id,
            "name": "A2A Conformance Echo",
            "entry": "echo",
            "nodes": {
                "echo": {
                    "type": "code",
                    "code": (
                        "async def run(args, state):\n"
                        "    content = state.get('content') or ''\n"
                        "    state['response'] = f'ECHO:{content}'\n"
                        "    return state\n"
                    ),
                },
            },
            "edges": [{"from_node": "echo", "to_node": None}],
        },
    )
    assert response.status_code == 200, response.text


async def create_json_response_flow(client: Any, flow_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        headers=A2A_HEADERS,
        json={
            "flow_id": flow_id,
            "name": "A2A Conformance JSON",
            "entry": "compose",
            "nodes": {
                "compose": {
                    "type": "code",
                    "code": (
                        "async def run(args, state):\n"
                        "    state['response'] = '{\"res\": \"ok\", \"n\": 1}'\n"
                        "    return state\n"
                    ),
                },
            },
            "edges": [{"from_node": "compose", "to_node": None}],
        },
    )
    assert response.status_code == 200, response.text


async def delete_flow(client: Any, flow_id: str) -> None:
    response = await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=A2A_HEADERS)
    assert response.status_code in {200, 204, 404}, response.text
