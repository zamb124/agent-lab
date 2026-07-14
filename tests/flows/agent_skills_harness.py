"""Харнесс для надёжных тестов Agent Skills (без monkeypatch)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from apps.flows.src.container import FlowContainer
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.services.flows_loader import FlowsLoader
from apps.flows.src.services.platform_assistant_skills import (
    PLATFORM_ASSISTANT_ATTACHED_SKILL_IDS,
)
from core.context import Context, clear_context, get_context, set_context
from core.models.identity_models import Company, User
from core.state import ExecutionState
from core.types import JsonObject, JsonValue, require_json_array, require_json_object

_BUNDLES_DIR = Path(__file__).resolve().parents[2] / "apps" / "flows" / "bundles"
_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "apps" / "flows" / "registry.yaml"


def company_context(company_id: str, unique_id: str) -> Context:
    return Context(
        user=User(user_id=f"user_{unique_id}", name="Test User"),
        active_company=Company(
            company_id=company_id,
            name=f"Company {company_id}",
            subdomain=f"sub-{unique_id}",
        ),
        session_id=f"session_{unique_id}",
        channel="test",
        metadata={},
    )


@asynccontextmanager
async def company_scope(company_id: str, unique_id: str) -> AsyncIterator[None]:
    previous = get_context()
    set_context(company_context(company_id, unique_id))
    try:
        yield
    finally:
        clear_context()
        if previous is not None:
            set_context(previous)


def make_skill_state(*, flow_id: str, unique_id: str, content: str = "run") -> ExecutionState:
    context_id = f"ctx_{unique_id}"
    return ExecutionState(
        task_id=f"task_{unique_id}",
        context_id=context_id,
        user_id=f"user_{unique_id}",
        session_id=f"{flow_id}:{context_id}",
        content=content,
    )


def mock_load_skill_then_calculator(
    *,
    agent_skill_id: str,
    expression: str = "2+2",
    final_text: str = "done",
) -> list[JsonObject]:
    return [
        {
            "type": "tool_calls",
            "calls": [
                {
                    "tool": "load_agent_skill",
                    "args": {"agent_skill_id": agent_skill_id},
                }
            ],
        },
        {
            "type": "tool_calls",
            "calls": [
                {
                    "tool": "calculator",
                    "args": {"expression": expression},
                }
            ],
        },
        {"type": "text", "content": final_text},
    ]


def node_agent_skills(main_node: JsonObject | object) -> list[str]:
    if isinstance(main_node, dict):
        raw = main_node.get("agent_skills", [])
        return [str(item) for item in require_json_array(raw, "main.agent_skills")]
    skills = getattr(main_node, "agent_skills", [])
    return [str(item) for item in skills]


def node_tool_ids(main_node: JsonObject | object) -> list[str]:
    if isinstance(main_node, dict):
        tools_raw: JsonValue = main_node.get("tools", [])
    else:
        tools_raw = getattr(main_node, "tools", [])
    tools = require_json_array(tools_raw, "main.tools")
    ids: list[str] = []
    for tool in tools:
        if isinstance(tool, str):
            ids.append(tool)
            continue
        tool_obj = require_json_object(tool, "main.tools[]")
        tool_id = tool_obj.get("tool_id")
        if isinstance(tool_id, str) and tool_id.strip():
            ids.append(tool_id)
    return ids


async def ensure_platform_assistant_flow(container: FlowContainer) -> FlowConfig:
    existing = await container.flow_repository.get("platform_assistant")
    if existing is not None:
        return existing
    loader = FlowsLoader(
        bundles_dir=_BUNDLES_DIR,
        flow_repository=container.flow_repository,
        node_repository=container.node_repository,
        tool_repository=container.tool_repository,
        registry_path=_REGISTRY_PATH,
    )
    loader.load_registry_yaml()
    await loader.preload_nodes_to_cache("platform_assistant")
    flow_id = await loader._load_flow_bundle("platform_assistant")
    if flow_id is None:
        raise AssertionError("Failed to load platform_assistant bundle")
    loaded = await container.flow_repository.get("platform_assistant")
    if loaded is None:
        raise AssertionError("platform_assistant missing after bundle load")
    return loaded


def assert_platform_assistant_attach(flow: FlowConfig) -> None:
    nodes = flow.nodes
    if nodes is None:
        raise AssertionError("platform_assistant has no nodes")
    main = nodes.get("main")
    if main is None:
        raise AssertionError("platform_assistant missing main node")
    assert node_agent_skills(main) == list(PLATFORM_ASSISTANT_ATTACHED_SKILL_IDS)
    tool_ids = node_tool_ids(main)
    assert "ask_user" in tool_ids
    assert "create_file" not in tool_ids
    assert "create_viz" not in tool_ids
    assert "load_agent_skill" not in tool_ids


__all__ = [
    "assert_platform_assistant_attach",
    "company_scope",
    "ensure_platform_assistant_flow",
    "make_skill_state",
    "mock_load_skill_then_calculator",
    "node_agent_skills",
    "node_tool_ids",
]
