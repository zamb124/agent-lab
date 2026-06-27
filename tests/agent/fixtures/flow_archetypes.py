"""Flow fixtures для HumanitecAgent Platform MCP E2E."""

from __future__ import annotations

from httpx import AsyncClient

ASK_USER_INLINE_CODE = (
    "\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\n"
    "async def run(args, state):\n"
    '    question = args.get("question", "")\n'
    "    if not question:\n"
    '        raise ValueError("question is required")\n'
    "    raise FlowInterrupt(question=question)\n"
)

CALCULATOR_INLINE_CODE = (
    "async def run(args, state):\n"
    "    expression = args.get('expression', '')\n"
    "    if not expression:\n"
    '        raise ValueError("expression is required")\n'
    "    if expression == '2+2':\n"
    "        return {'result': '4'}\n"
    '    raise ValueError(f"unsupported expression: {expression}")\n'
)

FAILED_CODE_NODE = (
    "async def run(args, state):\n"
    '    raise RuntimeError("agent mcp flow failed on purpose")\n'
)


async def _create_flow(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    flow_id: str,
    name: str,
    nodes: dict[str, object],
    description: str | None = None,
    entry: str = "main",
) -> str:
    payload: dict[str, object] = {
        "flow_id": flow_id,
        "name": name,
        "entry": entry,
        "nodes": nodes,
        "edges": [{"from_node": entry, "to_node": None}],
    }
    if description is not None:
        payload["description"] = description
    response = await flows_client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    return flow_id


async def ensure_react_flow(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> str:
    flow_id = f"agent_mcp_react_{unique_id}"
    return await _create_flow(
        flows_client,
        auth_headers,
        flow_id=flow_id,
        name=f"Agent MCP React {unique_id}",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "Reply briefly to the user.",
                "llm": {"provider": "mock", "model": "mock-gpt-4"},
            }
        },
    )


async def ensure_react_flow_with_description(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
    *,
    description: str,
) -> str:
    flow_id = f"agent_mcp_desc_{unique_id}"
    return await _create_flow(
        flows_client,
        auth_headers,
        flow_id=flow_id,
        name=f"Agent MCP Desc {unique_id}",
        description=description,
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "Reply briefly to the user.",
                "llm": {"provider": "mock", "model": "mock-gpt-4"},
            }
        },
    )


async def ensure_interrupt_flow(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> str:
    flow_id = f"agent_mcp_interrupt_{unique_id}"
    return await _create_flow(
        flows_client,
        auth_headers,
        flow_id=flow_id,
        name=f"Agent MCP Interrupt {unique_id}",
        description="Flow with ask_user interrupt for Platform MCP two-call resume",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "Ask the user name via ask_user tool.",
                "llm": {"provider": "mock", "model": "mock-gpt-4"},
                "tools": [
                    {
                        "tool_id": "ask_user",
                        "description": "Ask the user a question",
                        "code": ASK_USER_INLINE_CODE,
                        "parameters_schema": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string", "description": "Question"},
                            },
                            "required": ["question"],
                        },
                    }
                ],
            }
        },
    )


async def ensure_tool_only_flow(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> str:
    flow_id = f"agent_mcp_tool_{unique_id}"
    return await _create_flow(
        flows_client,
        auth_headers,
        flow_id=flow_id,
        name=f"Agent MCP Tool {unique_id}",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "Use calculator for math.",
                "llm": {"provider": "mock", "model": "mock-gpt-4"},
                "tools": [
                    {
                        "tool_id": "calculator",
                        "description": "Calculator",
                        "code": CALCULATOR_INLINE_CODE,
                        "parameters_schema": {
                            "type": "object",
                            "properties": {
                                "expression": {
                                    "type": "string",
                                    "description": "Math expression",
                                },
                            },
                            "required": ["expression"],
                        },
                    }
                ],
            }
        },
    )


async def ensure_multi_node_flow(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> str:
    flow_id = f"agent_mcp_multi_{unique_id}"
    payload: dict[str, object] = {
        "flow_id": flow_id,
        "name": f"Agent MCP Multi {unique_id}",
        "entry": "first",
        "description": "Two sequential llm nodes",
        "nodes": {
            "first": {
                "type": "llm_node",
                "prompt": "First step.",
                "llm": {"provider": "mock", "model": "mock-gpt-4"},
            },
            "second": {
                "type": "llm_node",
                "prompt": "Second step.",
                "llm": {"provider": "mock", "model": "mock-gpt-4"},
            },
        },
        "edges": [
            {"from_node": "first", "to_node": "second"},
            {"from_node": "second", "to_node": None},
        ],
    }
    response = await flows_client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    return flow_id


async def ensure_failed_flow(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> str:
    flow_id = f"agent_mcp_failed_{unique_id}"
    return await _create_flow(
        flows_client,
        auth_headers,
        flow_id=flow_id,
        name=f"Agent MCP Failed {unique_id}",
        entry="fail",
        nodes={
            "fail": {
                "type": "code",
                "code": FAILED_CODE_NODE,
            }
        },
    )


async def ensure_handoff_parent_child(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> tuple[str, str]:
    child_fid = f"agent_mcp_handoff_child_{unique_id}"
    parent_fid = f"agent_mcp_handoff_parent_{unique_id}"
    await _create_flow(
        flows_client,
        auth_headers,
        flow_id=child_fid,
        name=f"Handoff Child {unique_id}",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "child handback",
                "llm": {"provider": "mock", "model": "mock-gpt-4"},
                "tools": [
                    {"tool_id": "handback_to_parent", "description": "Handback"},
                ],
            }
        },
    )
    await _create_flow(
        flows_client,
        auth_headers,
        flow_id=parent_fid,
        name=f"Handoff Parent {unique_id}",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "parent handoff",
                "llm": {"provider": "mock", "model": "mock-gpt-4"},
                "tools": [
                    {"tool_id": "handoff_to_flow", "description": "Handoff"},
                ],
            }
        },
    )
    return parent_fid, child_fid


async def ensure_handoff_demo_bundles(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> tuple[str, str]:
    parent_fid = "handoff_demo_parent"
    child_fid = "handoff_demo_child"
    for flow_id in (parent_fid, child_fid):
        existing = await flows_client.get(
            f"/flows/api/v1/flows/{flow_id}",
            headers=auth_headers,
        )
        if existing.status_code == 200:
            delete = await flows_client.delete(
                f"/flows/api/v1/flows/{flow_id}",
                headers=auth_headers,
            )
            assert delete.status_code == 200, delete.text
    response = await flows_client.post(
        f"/flows/api/v1/flows/{parent_fid}/reload-from-bundle",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    child = await flows_client.get(
        f"/flows/api/v1/flows/{child_fid}",
        headers=auth_headers,
    )
    assert child.status_code == 200, child.text
    return parent_fid, child_fid
