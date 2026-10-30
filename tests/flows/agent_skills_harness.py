"""Харнесс для надёжных тестов Agent Skills (без monkeypatch)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from apps.flows.di import FlowsDi
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.services.flows_loader import FlowsLoader
from apps.flows.src.services.platform_assistant_skills import (
    LARA_PLATFORM_SKILL_ROOTS,
)
from apps.flows.src.state import ExecutionState
from core.authz.company_sync import sync_company_member_roles
from core.context import Context, clear_context, get_context, set_context
from core.models.identity_models import Company, User
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
async def company_scope(company_id: str, unique_id: str, di) -> AsyncIterator[None]:
    previous = get_context()
    ctx = company_context(company_id, unique_id)
    set_context(ctx)
    await sync_company_member_roles(
        di.authz_service,
        company_id=company_id,
        user_id=ctx.user.user_id,
        roles=["owner", "admin"],
    )
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


async def ensure_platform_assistant_flow(di: FlowsDi) -> FlowConfig:
    return await ensure_flow_bundle(di, "platform_assistant")


async def ensure_lara_flow(di: FlowsDi) -> FlowConfig:
    return await ensure_flow_bundle(di, "lara")


async def ensure_flow_bundle(di: FlowsDi, flow_id: str) -> FlowConfig:
    loader = FlowsLoader(
        bundles_dir=_BUNDLES_DIR,
        registry_path=_REGISTRY_PATH,
        flow_access_service=di.flow_access_service,
    )
    loader.load_registry_yaml()
    await loader.preload_nodes_to_cache(flow_id)
    loaded_id = await loader._load_flow_bundle(flow_id)
    if loaded_id is None:
        raise AssertionError(f"Failed to load {flow_id} bundle")
    loaded = await FlowConfig.current_for_flow(flow_id)
    if loaded is None:
        raise AssertionError(f"{flow_id} missing after bundle load")
    return loaded


def assert_platform_assistant_attach(flow: FlowConfig) -> None:
    _assert_skill_roots_attach(flow, flow_id_label="platform_assistant")


def assert_lara_attach(flow: FlowConfig) -> None:
    _assert_skill_roots_attach(flow, flow_id_label="lara")
    forbidden_tools = {
        "crm_search_entities",
        "crm_create_entity",
        "flows_patch_node",
        "flows_patch_flow",
        "flows_read_context",
        "flows_get_node",
        "flows_list_nodes",
        "create_file",
        "read_file",
        "ui_render",
        "create_viz",
        "docs_search",
    }
    nodes = flow.nodes
    if nodes is None:
        raise AssertionError("lara has no nodes")
    main = nodes.get("main")
    if main is None:
        raise AssertionError("lara missing main node")
    tool_ids = set(node_tool_ids(main))
    assert tool_ids == {"ask_user"}
    assert not (tool_ids & forbidden_tools)
    device_standing = {"ask_user"}
    for branch_id, branch in (flow.branches or {}).items():
        if branch.nodes is None:
            continue
        branch_main = branch.nodes.get("main")
        if branch_main is None:
            continue
        branch_tools = set(node_tool_ids(branch_main))
        if not branch_tools:
            continue
        if branch_tools != device_standing:
            raise AssertionError(
                f"lara branch {branch_id} standing tools mismatch: {sorted(branch_tools)}"
            )


def _assert_skill_roots_attach(flow: FlowConfig, *, flow_id_label: str) -> None:
    nodes = flow.nodes
    if nodes is None:
        raise AssertionError(f"{flow_id_label} has no nodes")
    main = nodes.get("main")
    if main is None:
        raise AssertionError(f"{flow_id_label} missing main node")
    assert node_agent_skills(main) == list(LARA_PLATFORM_SKILL_ROOTS)
    tool_ids = node_tool_ids(main)
    assert "ask_user" in tool_ids
    assert "create_file" not in tool_ids
    assert "create_viz" not in tool_ids
    assert "load_agent_skill" not in tool_ids


__all__ = [
    "assert_lara_attach",
    "assert_platform_assistant_attach",
    "company_scope",
    "ensure_flow_bundle",
    "ensure_lara_flow",
    "ensure_platform_assistant_flow",
    "make_skill_state",
    "mock_load_skill_then_calculator",
    "node_agent_skills",
    "node_tool_ids",
]
