"""Live Centrifugo RPC + REST identity для всех FLOWS_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /flows/api/internal/realtime/command` → тот же `op_*`.
REST — Granian :9001, префикс `/flows/api/v1`.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import pytest
from httpx2 import AsyncClient, Response

from apps.flows.realtime.command_router import FLOWS_OPERATIONS
from apps.flows.src.services.browser_preview import create_browser_preview_token
from core.capabilities import CapabilityExecutionContext
from core.capabilities.tokens import (
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event

_API = "/flows/api/v1"
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_TRANSPORT_MARKER = re.compile(r"(?:-|\s)(?:ws|rest)-|(?:ws|rest)(?=[0-9a-f]{8,})")
_VOLATILE_KEYS = frozenset(
    {
        "flow_id",
        "version",
        "suite_id",
        "case_id",
        "case_ids",
        "run_id",
        "case_run_id",
        "rubric_id",
        "rubric_version_id",
        "annotation_id",
        "monitor_id",
        "gate_policy_id",
        "grant_id",
        "share_url",
        "file_id",
        "resource_id",
        "tool_id",
        "trigger_id",
        "node_id",
        "agent_skill_id",
        "toolkit_id",
        "server_id",
        "catalog_id",
        "datasource_id",
        "session_id",
        "task_id",
        "context_id",
        "user_id",
        "initiator_user_id",
        "flow_config_version",
        "suite_version_id",
        "duration_ms",
        "guest_runtime_id",
        "image_digest",
        "image_bytes",
        "original_name",
        "s3_key",
        "download_url",
        "taskiq_task_id",
        "webhook_url",
        "event_id",
        "request_id",
        "trace_id",
        "service",
        "observability",
        "detail",
        "created_at",
        "updated_at",
        "expires_at",
        "revoked_at",
        "started_at",
        "finished_at",
        "sampled_at",
        "queued_at",
        "checksum",
        "file_size",
        "storage_url",
        "public_url",
        "url",
        "state",
        "seeded",
    }
)

CompareMode = Literal["normalized", "marker_row", "error_code", "succeeded_only", "failed_only"]
PayloadStrategy = Literal["body", "body_minus_path", "query", "none"]
ExpectMode = Literal["succeeded", "failed"]
SetupFn = Callable[["LiveCtx"], Awaitable[JsonObject]]


@dataclass(frozen=True)
class RestMirror:
    method: str
    url: str
    strategy: PayloadStrategy
    query_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpCase:
    rest: RestMirror
    setup: SetupFn
    same_resource: bool
    compare: CompareMode
    expect: ExpectMode = "succeeded"
    marker_field: str = "name"
    list_key: str = "items"


@dataclass
class LiveCtx:
    client: AsyncClient
    headers: dict[str, str]
    unique_id: str
    suffix: str
    system_user2_id: str
    marker: str | None = None


def _json(response: Response, label: str) -> JsonObject:
    return require_json_object(response.json(), label)


def _str_field(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{key} is required, got {value!r}")
    return value


def _token(ctx: LiveCtx) -> str:
    return f"{ctx.suffix}-{ctx.unique_id}"


def _strip_transport_marker(text: str) -> str:
    return _TRANSPORT_MARKER.sub("", text)


def _normalize(value: JsonValue | None) -> JsonValue | None:
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items() if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _strip_transport_marker(text=value)
    return value


def _event_payload(event: JsonObject) -> JsonObject:
    raw = event.get("payload")
    if raw is None:
        return {}
    return require_json_object(raw, "event.payload")


async def _expect_json(response: Response, *, ok: tuple[int, ...], label: str) -> JsonObject:
    assert response.status_code in ok, f"{label} {response.status_code}: {response.text}"
    if response.status_code == 204:
        return {}
    return _json(response, label)


def _echo_graph(*, name: str, flow_id: str) -> JsonObject:
    return {
        "flow_id": flow_id,
        "name": name,
        "entry": "echo",
        "nodes": {
            "echo": {
                "type": "code",
                "code": (
                    "async def run(args, state):\n"
                    "    state['answer'] = '42'\n"
                    "    return state\n"
                ),
            }
        },
        "edges": [{"from_node": "echo", "to_node": None}],
    }


async def _create_flow(ctx: LiveCtx, *, extra_nodes: JsonObject | None = None) -> JsonObject:
    flow_id = f"live-flow-{_token(ctx)}"
    name = f"Live flow {_token(ctx)}"
    body = _echo_graph(name=name, flow_id=flow_id)
    if extra_nodes is not None:
        nodes = require_json_object(body["nodes"], "nodes")
        nodes.update(extra_nodes)
        body["nodes"] = nodes
    response = await ctx.client.post(f"{_API}/flows/", headers=ctx.headers, json=body)
    created = await _expect_json(response, ok=(200, 201), label="flow_create")
    ctx.marker = name
    return created


async def _get_flow(ctx: LiveCtx, flow_id: str) -> JsonObject:
    response = await ctx.client.get(f"{_API}/flows/{flow_id}", headers=ctx.headers)
    return await _expect_json(response, ok=(200,), label="flow_item")


async def _create_suite(ctx: LiveCtx, flow_id: str) -> JsonObject:
    name = f"Live suite {_token(ctx)}"
    response = await ctx.client.post(
        f"{_API}/evaluation/suites",
        headers=ctx.headers,
        json={"flow_id": flow_id, "name": name, "description": name, "tags": ["live"]},
    )
    body = await _expect_json(response, ok=(200, 201), label="suite_create")
    ctx.marker = name
    return body


def _case_turns() -> list[JsonObject]:
    return [
        {
            "input": {"type": "text", "content": "ping"},
            "checks": [
                {
                    "type": "contains",
                    "source": "response",
                    "values": ["42"],
                    "mode": "any",
                    "case_sensitive": False,
                    "state_path": None,
                }
            ],
        }
    ]


async def _create_case(ctx: LiveCtx, suite_id: str) -> JsonObject:
    name = f"Live case {_token(ctx)}"
    response = await ctx.client.post(
        f"{_API}/evaluation/suites/{suite_id}/cases",
        headers=ctx.headers,
        json={
            "name": name,
            "description": name,
            "branch_ids": "*",
            "target": {"type": "flow"},
            "turns": _case_turns(),
            "max_turns": 10,
            "enabled": True,
            "tags": ["live"],
            "sort_order": 0,
        },
    )
    body = await _expect_json(response, ok=(200, 201), label="case_create")
    ctx.marker = name
    return body


async def _create_rubric(ctx: LiveCtx, flow_id: str) -> JsonObject:
    name = f"Live rubric {_token(ctx)}"
    response = await ctx.client.post(
        f"{_API}/evaluation/rubrics",
        headers=ctx.headers,
        json={
            "flow_id": flow_id,
            "name": name,
            "prompt": "Score strictly.",
            "pass_threshold": 7.0,
            "description": name,
            "tags": ["live"],
        },
    )
    body = await _expect_json(response, ok=(200, 201), label="rubric_create")
    ctx.marker = name
    return require_json_object(body.get("rubric"), "rubric")


async def _empty(_ctx: LiveCtx) -> JsonObject:
    return {}


async def _limit(_ctx: LiveCtx) -> JsonObject:
    return {"limit": 50, "offset": 0}


async def _setup_flows_list(ctx: LiveCtx) -> JsonObject:
    _ = await _create_flow(ctx)
    return {"limit": 50, "offset": 0}


async def _setup_sessions_list(ctx: LiveCtx) -> JsonObject:
    return {"limit": 50, "offset": 0, "flow_id": f"live-sessions-{ctx.unique_id}"}


async def _limit_tools_all(_ctx: LiveCtx) -> JsonObject:
    return {"limit": 20, "offset": 0, "q": "agent_plan_write"}


async def _setup_flow_create(ctx: LiveCtx) -> JsonObject:
    flow_id = f"live-flow-{_token(ctx)}"
    name = f"Live flow {_token(ctx)}"
    ctx.marker = name
    return _echo_graph(name=name, flow_id=flow_id)


async def _setup_flow_id(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {"flow_id": _str_field(created, "flow_id")}


async def _setup_flow_update(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    flow_id = _str_field(created, "flow_id")
    current = await _get_flow(ctx, flow_id)
    name = f"Live flow upd {_token(ctx)}"
    ctx.marker = name
    return {
        "flow_id": flow_id,
        "name": name,
        "description": current.get("description"),
        "entry": _str_field(current, "entry"),
        "nodes": current.get("nodes"),
        "edges": current.get("edges"),
        "variables": {},
        "tags": current.get("tags") if isinstance(current.get("tags"), list) else [],
        "branches": current.get("branches") if isinstance(current.get("branches"), dict) else {},
    }


async def _setup_flow_validate(ctx: LiveCtx) -> JsonObject:
    graph = await _setup_flow_create(ctx)
    return {
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "entry": graph["entry"],
        "variables": {},
    }


async def _setup_reload_bundle(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {"flow_id": _str_field(created, "flow_id")}


async def _setup_version(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    flow_id = _str_field(created, "flow_id")
    update = await _setup_flow_update(ctx) if False else None
    _ = update
    current = await _get_flow(ctx, flow_id)
    put = await ctx.client.put(
        f"{_API}/flows/{flow_id}",
        headers=ctx.headers,
        json={
            "flow_id": flow_id,
            "name": f"Live flow ver {_token(ctx)}",
            "entry": _str_field(current, "entry"),
            "nodes": current.get("nodes"),
            "edges": current.get("edges"),
            "variables": {},
            "tags": [],
            "branches": {},
        },
    )
    await _expect_json(put, ok=(200,), label="flow_version_seed")
    listed = await ctx.client.get(f"{_API}/flows/{flow_id}/versions", headers=ctx.headers)
    page = await _expect_json(listed, ok=(200,), label="versions_list")
    items = page.get("items")
    if not isinstance(items, list) or not items:
        raise AssertionError("flow versions required")
    version = items[0]
    if not isinstance(version, str) or not version:
        raise AssertionError(f"version string required, got {version!r}")
    return {"flow_id": flow_id, "version": version}


async def _setup_branch_create(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    branch_id = f"live-br-{_token(ctx)}"
    name = f"Live branch {_token(ctx)}"
    ctx.marker = name
    return {
        "flow_id": _str_field(created, "flow_id"),
        "branch_id": branch_id,
        "name": name,
        "description": name,
    }


async def _setup_branch_update(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_branch_create(ctx)
    created = await ctx.client.post(
        f"{_API}/{_str_field(payload, 'flow_id')}/branches",
        headers=ctx.headers,
        json={k: v for k, v in payload.items() if k != "flow_id"},
    )
    await _expect_json(created, ok=(200, 201), label="branch_create")
    name = f"Live branch upd {_token(ctx)}"
    ctx.marker = name
    return {**payload, "name": name, "description": name}


async def _setup_branch_remove(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_branch_create(ctx)
    created = await ctx.client.post(
        f"{_API}/{_str_field(payload, 'flow_id')}/branches",
        headers=ctx.headers,
        json={k: v for k, v in payload.items() if k != "flow_id"},
    )
    await _expect_json(created, ok=(200, 201), label="branch_create")
    return {"flow_id": _str_field(payload, "flow_id"), "branch_id": _str_field(payload, "branch_id")}


async def _setup_preview_share(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {
        "flow_id": _str_field(created, "flow_id"),
        "branch_id": "default",
    }


async def _setup_bulk_delete(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(
        ctx,
        extra_nodes={
            "extra": {
                "type": "code",
                "code": "async def run(args, state):\n    return state\n",
            }
        },
    )
    return {"flow_id": _str_field(created, "flow_id"), "node_ids": ["extra"]}


async def _setup_metadata(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {"flow_id": _str_field(created, "flow_id"), "sticky_notes": []}


async def _setup_dataflow(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    current = await _get_flow(ctx, _str_field(created, "flow_id"))
    return {
        "flow_id": _str_field(created, "flow_id"),
        "branch_id": "default",
        "entry": current.get("entry"),
        "nodes": current.get("nodes"),
        "edges": current.get("edges"),
    }


async def _setup_tool_id(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_tool_create(ctx)
    created = await ctx.client.post(f"{_API}/tools/", headers=ctx.headers, json=payload)
    await _expect_json(created, ok=(200, 201), label="tool_create")
    return {"tool_id": _str_field(payload, "tool_id")}


async def _setup_tool_create(ctx: LiveCtx) -> JsonObject:
    tool_id = f"live_tool_{_token(ctx).replace('-', '_')}"
    title = f"Live tool {_token(ctx)}"
    ctx.marker = title
    return {
        "tool_id": tool_id,
        "title": title,
        "description": title,
        "code": "async def run(args, state):\n    return {'ok': True}\n",
        "language": "python",
        "parameters_schema": {"type": "object", "properties": {}, "required": []},
        "tags": ["live"],
    }


async def _setup_tool_remove(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_tool_create(ctx)
    created = await ctx.client.post(f"{_API}/tools/", headers=ctx.headers, json=payload)
    await _expect_json(created, ok=(200, 201), label="tool_create")
    return {"tool_id": _str_field(payload, "tool_id")}


async def _setup_tool_preview(ctx: LiveCtx) -> JsonObject:
    return await _setup_tool_id(ctx)


async def _setup_trigger_create(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    trigger_id = f"live_wh_{_token(ctx).replace('-', '_')}"
    name = f"Live trigger {_token(ctx)}"
    ctx.marker = name
    return {
        "flow_id": _str_field(created, "flow_id"),
        "trigger_id": trigger_id,
        "name": name,
        "type": "webhook",
        "enabled": True,
        "config": {},
        "branch_id": "default",
    }


async def _setup_trigger_item(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_trigger_create(ctx)
    created = await ctx.client.post(
        f"{_API}/flows/{_str_field(payload, 'flow_id')}/triggers",
        headers=ctx.headers,
        json={k: v for k, v in payload.items() if k != "flow_id"},
    )
    await _expect_json(created, ok=(200, 201), label="trigger_create")
    return {"flow_id": _str_field(payload, "flow_id"), "trigger_id": _str_field(payload, "trigger_id")}


async def _setup_trigger_update(ctx: LiveCtx) -> JsonObject:
    item = await _setup_trigger_item(ctx)
    name = f"Live trigger upd {_token(ctx)}"
    ctx.marker = name
    return {**item, "name": name, "enabled": True, "config": {}, "branch_id": "default"}


async def _setup_trigger_verify(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {
        "flow_id": _str_field(created, "flow_id"),
        "type": "webhook",
        "config": {},
    }


async def _setup_trigger_test(ctx: LiveCtx) -> JsonObject:
    item = await _setup_trigger_item(ctx)
    return {**item, "payload": {"hello": "world"}}


async def _setup_code_docs(_ctx: LiveCtx) -> JsonObject:
    return {"language": "python", "perspective": "editor", "include_runtime_namespace_extras": False}


async def _setup_code_templates(_ctx: LiveCtx) -> JsonObject:
    return {"language": "python"}


async def _setup_code_editor(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {"flow_id": _str_field(created, "flow_id"), "branch_id": "default"}


async def _setup_code_source(_ctx: LiveCtx) -> JsonObject:
    return {"function_path": "apps.flows.src.runtime.missing_fn"}


async def _setup_code_functions(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {"flow_id": _str_field(created, "flow_id")}


async def _setup_code_tool_source(_ctx: LiveCtx) -> JsonObject:
    return {"tool_path": "missing.tool.path"}


async def _setup_code_parse(_ctx: LiveCtx) -> JsonObject:
    return {
        "code": "async def run(args, state):\n    return state\n",
        "func_name": "run",
    }


async def _setup_code_validate(_ctx: LiveCtx) -> JsonObject:
    return {
        "code": "async def run(args, state):\n    return state\n",
        "node_type": "code",
        "language": "python",
    }


async def _setup_code_execute(_ctx: LiveCtx) -> JsonObject:
    return {
        "node_type": "code",
        "code": "async def run(args, state):\n    state['ok'] = True\n    return state\n",
        "state": {},
        "args": {},
    }


async def _setup_datasource_missing(_ctx: LiveCtx) -> JsonObject:
    return {"datasource_id": "missing-live-datasource"}


async def _setup_datasource_create(ctx: LiveCtx) -> JsonObject:
    return {
        "connector_id": "missing-live-connector",
        "name": f"Live ds {_token(ctx)}",
    }


async def _setup_datasource_patch(_ctx: LiveCtx) -> JsonObject:
    return {"datasource_id": "missing-live-datasource", "name": "x"}


async def _setup_datasource_sql(_ctx: LiveCtx) -> JsonObject:
    return {"datasource_id": "missing-live-datasource", "sql": "select 1"}


async def _setup_connector_upsert(ctx: LiveCtx) -> JsonObject:
    connector_id = f"live-ds-{_token(ctx)}"
    return {
        "connector_id": connector_id,
        "name": f"Live connector {_token(ctx)}",
        "description": "live",
        "executor": "platform",
        "credential_schema": {"type": "object", "properties": {}},
        "operations": ["query"],
    }


async def _setup_flow_ui_templates(_ctx: LiveCtx) -> JsonObject:
    return {"limit": 100, "offset": 0}


async def _setup_flow_ui_assist(_ctx: LiveCtx) -> JsonObject:
    return {
        "flow_id": "missing-live-flow",
        "branch_id": "default",
        "instruction": "Do not change the page.",
        "document": {
            "start_page_id": "main",
            "pages": [
                {
                    "page_id": "main",
                    "title": "Live",
                    "blocks": [
                        {"block_id": "title", "type": "heading", "text": "Live", "level": 2},
                    ],
                }
            ],
        },
        "page_id": "missing-live-page",
    }


async def _setup_share_list(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {
        "flow_id": _str_field(created, "flow_id"),
        "context_id": f"live-ctx-{_token(ctx)}",
    }


async def _setup_share_create(ctx: LiveCtx) -> JsonObject:
    listed = await _setup_share_list(ctx)
    return {
        **listed,
        "permission": "viewer",
        "public_host": "localhost:9001",
        "expires_in_seconds": 3600,
    }


async def _setup_share_remove(_ctx: LiveCtx) -> JsonObject:
    return {"grant_id": "missing-live-share-grant-id-24"}


async def _setup_data_table(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {
        "original_name": f"live-table-{_token(ctx)}.sqlite",
        "scope": "flow_asset",
        "flow_id": _str_field(created, "flow_id"),
        "tables": [
            {
                "name": "leads",
                "columns": [{"name": "title", "column_type": "text"}],
            }
        ],
    }


async def _setup_llm_context(_ctx: LiveCtx) -> JsonObject:
    return {"llm_context_resource_key": None, "flow_resources": {}, "node_resources": {}}


async def _setup_prompt(_ctx: LiveCtx) -> JsonObject:
    return {"prompt": "Hello {name}", "variables": {"name": "live"}}


async def _setup_resource_create(ctx: LiveCtx) -> JsonObject:
    resource_id = f"live-res-{_token(ctx)}"
    name = f"Live resource {_token(ctx)}"
    ctx.marker = name
    return {
        "resource_id": resource_id,
        "type": "llm_context",
        "name": name,
        "description": name,
        "config": {},
        "tags": ["live"],
    }


async def _setup_resource_item(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_resource_create(ctx)
    created = await ctx.client.post(f"{_API}/resources/", headers=ctx.headers, json=payload)
    body = await _expect_json(created, ok=(200, 201), label="resource_create")
    return {"resource_id": _str_field(body, "resource_id")}


async def _setup_resource_update(ctx: LiveCtx) -> JsonObject:
    item = await _setup_resource_item(ctx)
    name = f"Live resource upd {_token(ctx)}"
    ctx.marker = name
    return {"resource_id": _str_field(item, "resource_id"), "name": name, "description": name, "config": {}}


async def _setup_session_missing(_ctx: LiveCtx) -> JsonObject:
    return {"session_id": "missing-flow:missing-live-session"}


async def _setup_session_state(_ctx: LiveCtx) -> JsonObject:
    return {"session_id": "missing-flow:missing-live-session"}


async def _setup_session_state_update(_ctx: LiveCtx) -> JsonObject:
    return {
        "session_id": "missing-flow:missing-live-session",
        "state": {
            "task_id": "missing-live-task",
            "context_id": "missing-live-context",
            "user_id": "missing-live-user",
            "session_id": "missing-flow:missing-live-session",
        },
    }


async def _setup_durable_history(_ctx: LiveCtx) -> JsonObject:
    return {"session_id": "missing-flow:missing-live-session", "limit": 50, "offset": 0}


async def _setup_durable_state_at(_ctx: LiveCtx) -> JsonObject:
    return {"session_id": "missing-flow:missing-live-session", "sequence": 0}


async def _setup_durable_fork(_ctx: LiveCtx) -> JsonObject:
    return {"session_id": "missing-flow:missing-live-session", "sequence": 0, "activate": False}


async def _setup_durable_rewind(_ctx: LiveCtx) -> JsonObject:
    return {"session_id": "missing-flow:missing-live-session", "sequence": 0}


async def _setup_durable_retry(_ctx: LiveCtx) -> JsonObject:
    return {"session_id": "missing-flow:missing-live-session", "failed_sequence": 1}


async def _setup_durable_patch(_ctx: LiveCtx) -> JsonObject:
    return {
        "session_id": "missing-flow:missing-live-session",
        "sequence": 0,
        "activate": True,
        "state": {
            "task_id": "missing-live-task",
            "context_id": "missing-live-context",
            "user_id": "missing-live-user",
            "session_id": "missing-flow:missing-live-session",
        },
    }


async def _setup_skill_create(ctx: LiveCtx) -> JsonObject:
    skill_id = f"live-skill-{_token(ctx)}"
    name = f"live-skill-{_token(ctx)}"
    ctx.marker = name
    return {
        "agent_skill_id": skill_id,
        "name": name,
        "description": "Live skill for command identity",
        "body_markdown": "# Live\nDo the thing.",
    }


async def _setup_skill_item(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_skill_create(ctx)
    created = await ctx.client.post(f"{_API}/agent-skills", headers=ctx.headers, json=payload)
    body = await _expect_json(created, ok=(200, 201), label="skill_create")
    return {"agent_skill_id": _str_field(body, "agent_skill_id")}


async def _setup_skill_update(ctx: LiveCtx) -> JsonObject:
    item = await _setup_skill_item(ctx)
    name = f"live-skill-upd-{_token(ctx)}"
    ctx.marker = name
    return {
        "agent_skill_id": _str_field(item, "agent_skill_id"),
        "name": name,
        "description": "Updated live skill",
        "body_markdown": "# Updated\nDo the thing.",
    }


async def _setup_skill_import(ctx: LiveCtx) -> JsonObject:
    skill_id = f"live-imp-{_token(ctx)}"
    return {
        "agent_skill_id": skill_id,
        "persist": True,
        "markdown": (
            "---\n"
            f"name: {skill_id}\n"
            "description: Imported live skill\n"
            "---\n\n"
            "# Body\n"
            "Do the imported thing.\n"
        ),
    }


async def _setup_mcp_list(_ctx: LiveCtx) -> JsonObject:
    return {"search": "", "limit": 50, "offset": 0}


async def _setup_mcp_missing(_ctx: LiveCtx) -> JsonObject:
    return {"server_id": "missing-live-mcp"}


async def _setup_mcp_create(ctx: LiveCtx) -> JsonObject:
    token = _token(ctx).replace("-", "")
    return {
        "server_id": f"liveMcp{token}",
        "name": f"Live MCP {_token(ctx)}",
        "url": "http://127.0.0.1:1/mcp",
        "transport_type": "http",
    }


async def _setup_mcp_catalog(_ctx: LiveCtx) -> JsonObject:
    return {"tier": "store", "search": "", "limit": 20, "offset": 0}


async def _setup_mcp_catalog_id(_ctx: LiveCtx) -> JsonObject:
    return {"catalog_id": "missing-live-catalog"}


async def _setup_branding_upsert(_ctx: LiveCtx) -> JsonObject:
    return {"server_id": "missing-live-mcp", "icon_file_id": "missing-live-file"}


async def _setup_branding_suggest(_ctx: LiveCtx) -> JsonObject:
    return {"search": "", "limit": 15}


async def _setup_mcp_update(_ctx: LiveCtx) -> JsonObject:
    return {"server_id": "missing-live-mcp", "name": "missing"}


async def _setup_node_list(_ctx: LiveCtx) -> JsonObject:
    return {"limit": 50, "offset": 0}


async def _setup_node_create(ctx: LiveCtx) -> JsonObject:
    node_id = f"live-node-{_token(ctx)}"
    return {
        "node_id": node_id,
        "type": "code",
        "code": "async def run(args, state):\n    return state\n",
    }


async def _setup_node_item(_ctx: LiveCtx) -> JsonObject:
    return {"node_id": "missing-live-node"}


async def _setup_eval_flow_id(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {"flow_id": _str_field(created, "flow_id")}


async def _setup_suite_create(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    name = f"Live suite {_token(ctx)}"
    ctx.marker = name
    return {"flow_id": _str_field(created, "flow_id"), "name": name, "description": name, "tags": ["live"]}


async def _setup_suite_item(ctx: LiveCtx) -> JsonObject:
    flow = await _create_flow(ctx)
    suite = await _create_suite(ctx, _str_field(flow, "flow_id"))
    return {"suite_id": _str_field(suite, "suite_id")}


async def _setup_suite_update(ctx: LiveCtx) -> JsonObject:
    item = await _setup_suite_item(ctx)
    name = f"Live suite upd {_token(ctx)}"
    ctx.marker = name
    return {**item, "name": name, "description": name, "tags": ["live"]}


async def _setup_case_create(ctx: LiveCtx) -> JsonObject:
    item = await _setup_suite_item(ctx)
    name = f"Live case {_token(ctx)}"
    ctx.marker = name
    return {
        "suite_id": _str_field(item, "suite_id"),
        "name": name,
        "description": name,
        "branch_ids": "*",
        "target": {"type": "flow"},
        "turns": _case_turns(),
        "max_turns": 10,
        "enabled": True,
        "tags": ["live"],
        "sort_order": 0,
    }


async def _setup_case_item(ctx: LiveCtx) -> JsonObject:
    suite = await _setup_suite_item(ctx)
    case = await _create_case(ctx, _str_field(suite, "suite_id"))
    return {
        "suite_id": _str_field(suite, "suite_id"),
        "case_id": _str_field(case, "case_id"),
    }


async def _setup_case_update(ctx: LiveCtx) -> JsonObject:
    item = await _setup_case_item(ctx)
    name = f"Live case upd {_token(ctx)}"
    ctx.marker = name
    return {
        **item,
        "name": name,
        "description": name,
        "branch_ids": "*",
        "target": {"type": "flow"},
        "turns": _case_turns(),
        "max_turns": 10,
        "enabled": True,
        "tags": ["live"],
        "sort_order": 0,
    }


async def _setup_case_import(ctx: LiveCtx) -> JsonObject:
    suite = await _setup_suite_item(ctx)
    return {
        "suite_id": _str_field(suite, "suite_id"),
        "format": "jsonl",
        "content": (
            '{"name":"imported","branch_ids":"*","turns":'
            '[{"input":{"type":"text","content":"x"},"checks":[]}]}'
        ),
    }


async def _setup_case_from_dialog(ctx: LiveCtx) -> JsonObject:
    suite = await _setup_suite_item(ctx)
    return {
        "suite_id": _str_field(suite, "suite_id"),
        "name": f"Live dialog {_token(ctx)}",
        "description": "dialog",
        "branch_ids": "*",
        "dialog": [{"role": "user", "content": "hello"}],
        "checks": [],
        "tags": ["live"],
        "sort_order": 0,
    }


async def _setup_case_from_case_run(ctx: LiveCtx) -> JsonObject:
    suite = await _setup_suite_item(ctx)
    return {
        "suite_id": _str_field(suite, "suite_id"),
        "name": f"Live from run {_token(ctx)}",
        "description": "from run",
        "case_run_id": "missing-live-case-run",
        "checks": [],
        "tags": ["live"],
        "sort_order": 0,
    }


async def _setup_case_from_trace(ctx: LiveCtx) -> JsonObject:
    suite = await _setup_suite_item(ctx)
    return {
        "suite_id": _str_field(suite, "suite_id"),
        "name": f"Live from trace {_token(ctx)}",
        "description": "from trace",
        "trace_id": "missing-live-trace",
        "branch_ids": "*",
        "dialog": [{"role": "user", "content": "hello"}],
        "checks": [],
        "tags": ["live"],
        "sort_order": 0,
    }


async def _setup_run_create(ctx: LiveCtx) -> JsonObject:
    suite = await _setup_suite_item(ctx)
    case = await _create_case(ctx, _str_field(suite, "suite_id"))
    return {
        "suite_id": _str_field(suite, "suite_id"),
        "branch_id": "default",
        "scope": {"type": "cases", "case_ids": [_str_field(case, "case_id")]},
        "trials": 1,
        "max_concurrency": 1,
    }


async def _setup_run_id(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_run_create(ctx)
    created = await ctx.client.post(f"{_API}/evaluation/runs", headers=ctx.headers, json=payload)
    body = await _expect_json(created, ok=(200, 201), label="run_create")
    run = require_json_object(body.get("run"), "run")
    return {"run_id": _str_field(run, "run_id")}


async def _setup_run_events_page(ctx: LiveCtx) -> JsonObject:
    run = await _setup_run_id(ctx)
    return {**run, "after_sequence": 0, "limit": 50}


async def _setup_jobs(_ctx: LiveCtx) -> JsonObject:
    return {"limit": 20}


async def _setup_matrix(ctx: LiveCtx) -> JsonObject:
    suite = await _setup_suite_item(ctx)
    return {"suite_id": _str_field(suite, "suite_id"), "branch_id": "default", "limit": 20}


async def _setup_compare_runs(_ctx: LiveCtx) -> JsonObject:
    return {"left_run_id": "missing-live-run-a", "right_run_id": "missing-live-run-b"}


async def _setup_case_run_trace(_ctx: LiveCtx) -> JsonObject:
    return {"case_run_id": "missing-live-case-run"}


async def _setup_annotation_create(ctx: LiveCtx) -> JsonObject:
    run = await _setup_run_id(ctx)
    return {
        "run_id": _str_field(run, "run_id"),
        "annotation_type": "comment",
        "comment": f"Live note {_token(ctx)}",
        "payload": {},
    }


async def _setup_annotation_item(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_annotation_create(ctx)
    created = await ctx.client.post(
        f"{_API}/evaluation/runs/{_str_field(payload, 'run_id')}/annotations",
        headers=ctx.headers,
        json={k: v for k, v in payload.items() if k != "run_id"},
    )
    body = await _expect_json(created, ok=(200, 201), label="annotation_create")
    return {
        "annotation_id": _str_field(body, "annotation_id"),
        "annotation_type": "comment",
        "comment": f"Live note upd {_token(ctx)}",
        "payload": {},
    }


async def _setup_annotation_id(ctx: LiveCtx) -> JsonObject:
    item = await _setup_annotation_item(ctx)
    return {"annotation_id": _str_field(item, "annotation_id")}


async def _setup_baseline_set(ctx: LiveCtx) -> JsonObject:
    created = await _setup_run_create(ctx)
    posted = await ctx.client.post(f"{_API}/evaluation/runs", headers=ctx.headers, json=created)
    body = await _expect_json(posted, ok=(200, 201), label="run_create")
    run = require_json_object(body.get("run"), "run")
    return {
        "suite_id": _str_field(created, "suite_id"),
        "branch_id": "default",
        "run_id": _str_field(run, "run_id"),
    }


async def _setup_baseline_item(ctx: LiveCtx) -> JsonObject:
    suite = await _setup_suite_item(ctx)
    return {"suite_id": _str_field(suite, "suite_id"), "branch_id": "default"}


async def _setup_baseline_compare(ctx: LiveCtx) -> JsonObject:
    return await _setup_baseline_set(ctx)


async def _setup_gate_create(ctx: LiveCtx) -> JsonObject:
    suite = await _setup_suite_item(ctx)
    name = f"Live gate {_token(ctx)}"
    ctx.marker = name
    return {
        "suite_id": _str_field(suite, "suite_id"),
        "branch_id": "default",
        "name": name,
        "min_pass_rate": 1.0,
        "max_failed_case_runs": 0,
        "max_error_case_runs": 0,
        "require_baseline": False,
    }


async def _setup_gate_item(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_gate_create(ctx)
    created = await ctx.client.post(
        f"{_API}/evaluation/suites/{_str_field(payload, 'suite_id')}/gate-policies",
        headers=ctx.headers,
        json={k: v for k, v in payload.items() if k != "suite_id"},
    )
    body = await _expect_json(created, ok=(200, 201), label="gate_create")
    return {"gate_policy_id": _str_field(body, "gate_policy_id")}


async def _setup_gate_update(ctx: LiveCtx) -> JsonObject:
    item = await _setup_gate_item(ctx)
    name = f"Live gate upd {_token(ctx)}"
    ctx.marker = name
    return {
        **item,
        "suite_id": "",
        "branch_id": "default",
        "name": name,
        "min_pass_rate": 1.0,
        "max_failed_case_runs": 0,
        "max_error_case_runs": 0,
        "require_baseline": False,
    }


async def _setup_gate_run(ctx: LiveCtx) -> JsonObject:
    item = await _setup_gate_item(ctx)
    return {
        **item,
        "trigger": "manual",
        "trials": 1,
        "max_concurrency": 1,
    }


async def _setup_monitor_create(ctx: LiveCtx) -> JsonObject:
    suite = await _setup_suite_item(ctx)
    name = f"Live monitor {_token(ctx)}"
    ctx.marker = name
    return {
        "suite_id": _str_field(suite, "suite_id"),
        "branch_id": "default",
        "name": name,
        "description": name,
        "sampling_rate": 1.0,
        "max_traces_per_sample": 10,
    }


async def _setup_monitor_item(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_monitor_create(ctx)
    created = await ctx.client.post(f"{_API}/evaluation/monitors", headers=ctx.headers, json=payload)
    body = await _expect_json(created, ok=(200, 201), label="monitor_create")
    return {"monitor_id": _str_field(body, "monitor_id")}


async def _setup_monitor_update(ctx: LiveCtx) -> JsonObject:
    item = await _setup_monitor_item(ctx)
    name = f"Live monitor upd {_token(ctx)}"
    ctx.marker = name
    return {
        **item,
        "branch_id": "default",
        "name": name,
        "description": name,
        "state": "paused",
        "sampling_rate": 1.0,
        "max_traces_per_sample": 10,
    }


async def _setup_monitor_sample(ctx: LiveCtx) -> JsonObject:
    item = await _setup_monitor_item(ctx)
    return {**item, "limit": 10}


async def _setup_monitor_cycle(ctx: LiveCtx) -> JsonObject:
    item = await _setup_monitor_item(ctx)
    return {
        **item,
        "limit": 10,
        "enqueue_gate_run": False,
        "trials": 1,
        "max_concurrency": 1,
    }


async def _setup_monitor_cycles_active(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_monitor_create(ctx)
    payload["filter"] = {"session_id": f"missing-monitor-{ctx.unique_id}"}
    created = await ctx.client.post(
        f"{_API}/evaluation/monitors",
        headers=ctx.headers,
        json=payload,
    )
    body = await _expect_json(created, ok=(200, 201), label="monitor_create")
    ctx.marker = _str_field(body, "monitor_id")
    return {
        "limit_per_monitor": 10,
        "enqueue_gate_runs": False,
        "trials": 1,
        "max_concurrency": 1,
    }


async def _setup_monitor_observation_case(ctx: LiveCtx) -> JsonObject:
    item = await _setup_monitor_item(ctx)
    return {
        **item,
        "trace_id": "missing-live-trace",
        "name": f"Live obs {_token(ctx)}",
        "description": "obs",
        "dialog": [{"role": "user", "content": "hello"}],
        "checks": [],
        "tags": ["live"],
        "sort_order": 0,
    }


async def _setup_pairwise(_ctx: LiveCtx) -> JsonObject:
    return {
        "mode": "human",
        "left_case_run_id": "missing-live-left",
        "right_case_run_id": "missing-live-right",
        "preferred": "left",
        "feedback": "live",
    }


async def _setup_rubric_create(ctx: LiveCtx) -> JsonObject:
    flow = await _create_flow(ctx)
    name = f"Live rubric {_token(ctx)}"
    ctx.marker = name
    return {
        "flow_id": _str_field(flow, "flow_id"),
        "name": name,
        "prompt": "Score strictly.",
        "pass_threshold": 7.0,
        "description": name,
        "tags": ["live"],
    }


async def _setup_rubric_item(ctx: LiveCtx) -> JsonObject:
    flow = await _create_flow(ctx)
    rubric = await _create_rubric(ctx, _str_field(flow, "flow_id"))
    return {"rubric_id": _str_field(rubric, "rubric_id")}


async def _setup_rubric_update(ctx: LiveCtx) -> JsonObject:
    item = await _setup_rubric_item(ctx)
    name = f"Live rubric upd {_token(ctx)}"
    ctx.marker = name
    return {**item, "name": name, "description": name, "tags": ["live"]}


async def _setup_rubric_version(ctx: LiveCtx) -> JsonObject:
    item = await _setup_rubric_item(ctx)
    return {**item, "prompt": "Score even stricter.", "pass_threshold": 8.0}


async def _setup_code_agent(ctx: LiveCtx) -> JsonObject:
    created = await _create_flow(ctx)
    return {
        "flow_id": _str_field(created, "flow_id"),
        "node_id": "echo",
        "branch_id": "default",
    }


async def _setup_code_agent_git(ctx: LiveCtx) -> JsonObject:
    ref = await _setup_code_agent(ctx)
    return {**ref, "git_url": "http://127.0.0.1:1/missing.git", "source_sha": "0" * 40}


async def _setup_code_agent_archive(ctx: LiveCtx) -> JsonObject:
    ref = await _setup_code_agent(ctx)
    return {**ref, "file_id": "missing-live-file"}


async def _setup_code_agent_copy(_ctx: LiveCtx) -> JsonObject:
    return {
        "flow_id": "missing-live-flow",
        "node_id": "missing-live-node",
        "from_catalog_id": "missing-live-catalog",
    }


async def _setup_code_agent_rebuild(ctx: LiveCtx) -> JsonObject:
    ref = await _setup_code_agent(ctx)
    return {
        **ref,
        "language": "python",
        "invoke_kind": "cli",
        "invoke_argv": ["python3", "main.py"],
    }


async def _setup_logs_trace(_ctx: LiveCtx) -> JsonObject:
    return {"trace_id": "0" * 32, "limit": 20}


async def _setup_logs_session(_ctx: LiveCtx) -> JsonObject:
    return {"session_id": "missing-flow:missing-live-session", "limit": 20}


async def _setup_logs_request(_ctx: LiveCtx) -> JsonObject:
    return {"request_id": "missing-live-request", "limit": 20}


async def _setup_logs_span(_ctx: LiveCtx) -> JsonObject:
    return {"span_id": "0" * 16, "limit": 20}


async def _setup_logs_user(ctx: LiveCtx) -> JsonObject:
    return {"user_id": ctx.system_user2_id, "limit": 20}


async def _setup_traces_search(ctx: LiveCtx) -> JsonObject:
    return {"flow_id": f"trace-search-{ctx.unique_id}", "limit": 10, "offset": 0}


async def _setup_traces_session(_ctx: LiveCtx) -> JsonObject:
    return {"session_id": "missing-flow:missing-live-session", "limit": 10}


async def _setup_traces_task(_ctx: LiveCtx) -> JsonObject:
    return {"task_id": "missing-live-task", "limit": 10}


async def _setup_traces_trace(_ctx: LiveCtx) -> JsonObject:
    return {"trace_id": "0" * 32, "limit": 10}


async def _setup_traces_handoff(_ctx: LiveCtx) -> JsonObject:
    return {"parent_session_id": "missing-flow:missing-live-session"}


async def _setup_hitl(_ctx: LiveCtx) -> JsonObject:
    return {"work_item_id": "missing-live-work-item"}


async def _setup_hitl_send(_ctx: LiveCtx) -> JsonObject:
    return {
        "work_item_id": "missing-live-work-item",
        "text": "hello",
        "idempotency_key": "missing-live-hitl",
    }


async def _setup_lara(_ctx: LiveCtx) -> JsonObject:
    return {
        "pending_action_id": "missing-live-action",
        "context_id": "missing-live-context",
    }


async def _setup_company_mismatch(_ctx: LiveCtx) -> JsonObject:
    return {
        "company_id": "missing-live-company",
        "company_name": "Missing",
        "subdomain": "missing",
    }


async def _setup_credentials_remove(_ctx: LiveCtx) -> JsonObject:
    return {"provider": "google", "service": "missing-live-service"}


async def _setup_workspace_put(_ctx: LiveCtx) -> JsonObject:
    return {"service_account_json": "{not-json"}


async def _setup_tool_runtime_call(ctx: LiveCtx) -> JsonObject:
    """Подписанный capability context: tool runtime поднимает контекст из него, не из сессии."""
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id=ctx.system_user2_id,
        flow_id=f"live-tool-runtime-{ctx.unique_id}",
        branch_id="main",
        session_id=f"live-tool-runtime-{ctx.unique_id}:ctx",
        task_id=f"task-{ctx.unique_id}",
        context_id=f"ctx-{ctx.unique_id}",
        channel="test",
        exp=execution_token_exp(120),
    )
    context = CapabilityExecutionContext(
        execution_token=issue_execution_token(claims),
        company_id=claims.company_id,
        user_id=claims.user_id,
        flow_id=claims.flow_id,
        branch_id=claims.branch_id,
        session_id=claims.session_id,
        task_id=claims.task_id,
        context_id=claims.context_id,
        channel=claims.channel,
    )
    return {
        "context": require_json_object(context.model_dump(mode="json"), "execution context"),
        "tool_id": "calculator",
        "arguments": {"expression": "2 + 2"},
        "state": {
            "task_id": claims.task_id,
            "context_id": claims.context_id,
            "user_id": ctx.system_user2_id,
            "session_id": claims.session_id,
            "flow_id": claims.flow_id,
        },
    }


def _browser_preview_ids(ctx: LiveCtx) -> tuple[str, str, str]:
    """Сессии Browser Runtime в тестовом стеке нет: token валиден, а сам вызов — ошибка peer."""
    session_id = f"live-bp-session-{ctx.unique_id}"
    task_id = f"live-bp-task-{ctx.unique_id}"
    return session_id, task_id, create_browser_preview_token(session_id=session_id, task_id=task_id)


async def _setup_browser_preview_session(ctx: LiveCtx) -> JsonObject:
    session_id, _task_id, token = _browser_preview_ids(ctx)
    return {"session_id": session_id, "token": token}


async def _setup_browser_preview_task(ctx: LiveCtx) -> JsonObject:
    _session_id, task_id, token = _browser_preview_ids(ctx)
    return {"task_id": task_id, "token": token}


async def _setup_browser_preview_click(ctx: LiveCtx) -> JsonObject:
    session_id, _task_id, token = _browser_preview_ids(ctx)
    return {
        "session_id": session_id,
        "token": token,
        "x": 10.0,
        "y": 20.0,
        "image_width": 800.0,
        "image_height": 600.0,
        "button": "left",
        "click_count": 1,
    }


async def _setup_browser_preview_key(ctx: LiveCtx) -> JsonObject:
    session_id, _task_id, token = _browser_preview_ids(ctx)
    return {"session_id": session_id, "token": token, "key": "Enter"}


async def _setup_browser_preview_text(ctx: LiveCtx) -> JsonObject:
    session_id, _task_id, token = _browser_preview_ids(ctx)
    return {"session_id": session_id, "token": token, "text": "hello"}


async def _setup_browser_preview_takeover(ctx: LiveCtx) -> JsonObject:
    session_id, _task_id, token = _browser_preview_ids(ctx)
    return {"session_id": session_id, "token": token, "owner": "human"}


def _op(
    method: str,
    url: str,
    strategy: PayloadStrategy,
    setup: SetupFn,
    *,
    same: bool,
    expect: ExpectMode = "succeeded",
    compare: CompareMode | None = None,
    query_keys: tuple[str, ...] = (),
    marker_field: str = "name",
    list_key: str = "items",
) -> OpCase:
    resolved: CompareMode
    if compare is not None:
        resolved = compare
    elif expect == "failed":
        resolved = "error_code"
    else:
        resolved = "normalized"
    return OpCase(
        rest=RestMirror(
            method=method,
            url=url,
            strategy=strategy,
            query_keys=query_keys,
        ),
        setup=setup,
        same_resource=same,
        compare=resolved,
        expect=expect,
        marker_field=marker_field,
        list_key=list_key,
    )


_CASES: dict[str, OpCase] = {
    "flows/flows/list_requested": _op(
        "GET", f"{_API}/flows/", "query", _setup_flows_list, same=True, compare="marker_row",
    ),
    "flows/flows/item_requested": _op("GET", f"{_API}/flows/{{flow_id}}", "none", _setup_flow_id, same=True),
    "flows/flows/create_requested": _op("POST", f"{_API}/flows/", "body", _setup_flow_create, same=False),
    "flows/flows/update_requested": _op(
        "PUT", f"{_API}/flows/{{flow_id}}", "body", _setup_flow_update, same=True,
    ),
    "flows/flows/remove_requested": _op(
        "DELETE", f"{_API}/flows/{{flow_id}}", "none", _setup_flow_id, same=False,
    ),
    "flows/flows/store_bundles_requested": _op(
        "GET", f"{_API}/flows/store/bundles", "none", _empty, same=True,
    ),
    "flows/flows/validate_requested": _op(
        "POST", f"{_API}/flows/validate", "body", _setup_flow_validate, same=True,
    ),
    "flows/flows/reload_from_bundle_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/reload-from-bundle",
        "none",
        _setup_reload_bundle,
        same=True,
        expect="failed",
    ),
    "flows/flows/versions_list_requested": _op(
        "GET", f"{_API}/flows/{{flow_id}}/versions", "none", _setup_flow_id, same=True,
    ),
    "flows/flows/version_item_requested": _op(
        "GET", f"{_API}/flows/{{flow_id}}/versions/{{version}}", "none", _setup_version, same=True,
    ),
    "flows/flows/version_rollback_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/versions/{{version}}/rollback",
        "none",
        _setup_version,
        same=True,
    ),
    "flows/flows/branch_create_requested": _op(
        "POST", f"{_API}/{{flow_id}}/branches", "body_minus_path", _setup_branch_create, same=False,
    ),
    "flows/flows/branch_update_requested": _op(
        "PUT",
        f"{_API}/{{flow_id}}/branches/{{branch_id}}",
        "body_minus_path",
        _setup_branch_update,
        same=True,
    ),
    "flows/flows/branch_remove_requested": _op(
        "DELETE", f"{_API}/{{flow_id}}/branches/{{branch_id}}", "none", _setup_branch_remove, same=False,
    ),
    "flows/flows/voice_session_query_requested": _op(
        "GET",
        f"{_API}/flows/{{flow_id}}/voice-session-query",
        "query",
        _setup_preview_share,
        same=True,
    ),
    "flows/flows/preview_share_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/preview-share",
        "body_minus_path",
        _setup_preview_share,
        same=True,
    ),
    "flows/flows/nodes_bulk_delete_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/nodes/bulk_delete",
        "body_minus_path",
        _setup_bulk_delete,
        same=False,
    ),
    "flows/flows/metadata_update_requested": _op(
        "PATCH",
        f"{_API}/flows/{{flow_id}}/metadata",
        "body_minus_path",
        _setup_metadata,
        same=True,
    ),
    "flows/flows/dataflow_inspect_requested": _op(
        "POST", f"{_API}/flows/dataflow/inspect", "body", _setup_dataflow, same=True,
    ),
    "flows/metadata/node_types_requested": _op(
        "GET", f"{_API}/metadata/node-types", "none", _empty, same=True,
    ),
    "flows/metadata/resource_types_requested": _op(
        "GET", f"{_API}/metadata/resource-types", "none", _empty, same=True,
    ),
    "flows/metadata/exception_absorb_allow_names_requested": _op(
        "GET", f"{_API}/metadata/exception-absorb-allow-names", "none", _empty, same=True,
    ),
    "flows/metadata/execution_limits_requested": _op(
        "GET", f"{_API}/metadata/execution-limits", "none", _empty, same=True,
    ),
    "flows/tools/list_requested": _op("GET", f"{_API}/tools/", "query", _limit, same=True),
    "flows/tools/item_requested": _op(
        "GET", f"{_API}/tools/{{tool_id}}", "none", _setup_tool_id, same=True,
    ),
    "flows/tools/create_requested": _op(
        "POST", f"{_API}/tools/", "body", _setup_tool_create, same=False,
    ),
    "flows/tools/remove_requested": _op(
        "DELETE", f"{_API}/tools/{{tool_id}}", "none", _setup_tool_remove, same=False,
    ),
    "flows/tools/list_all_requested": _op("GET", f"{_API}/tools/all", "query", _limit_tools_all, same=True),
    "flows/tools/tag_groups_requested": _op(
        "GET", f"{_API}/tools/tag-groups", "query", _limit, same=True,
    ),
    "flows/tools/preview_requested": _op(
        "POST", f"{_API}/tools/preview", "body", _setup_tool_preview, same=True,
    ),
    "flows/tools/contract_requested": _op(
        "GET", f"{_API}/tools/{{tool_id}}/contract", "none", _setup_tool_id, same=True,
    ),
    "flows/triggers/list_requested": _op(
        "GET", f"{_API}/flows/{{flow_id}}/triggers", "none", _setup_flow_id, same=True,
    ),
    "flows/triggers/item_requested": _op(
        "GET",
        f"{_API}/flows/{{flow_id}}/triggers/{{trigger_id}}",
        "none",
        _setup_trigger_item,
        same=True,
    ),
    "flows/triggers/create_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/triggers",
        "body_minus_path",
        _setup_trigger_create,
        same=False,
    ),
    "flows/triggers/update_requested": _op(
        "PUT",
        f"{_API}/flows/{{flow_id}}/triggers/{{trigger_id}}",
        "body_minus_path",
        _setup_trigger_update,
        same=True,
    ),
    "flows/triggers/remove_requested": _op(
        "DELETE",
        f"{_API}/flows/{{flow_id}}/triggers/{{trigger_id}}",
        "none",
        _setup_trigger_item,
        same=False,
    ),
    "flows/triggers/verify_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/triggers/verify",
        "body_minus_path",
        _setup_trigger_verify,
        same=True,
    ),
    "flows/triggers/reregister_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/triggers/{{trigger_id}}/reregister",
        "none",
        _setup_trigger_item,
        same=True,
    ),
    "flows/triggers/test_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/triggers/{{trigger_id}}/test",
        "body",
        _setup_trigger_test,
        same=True,
    ),
    "flows/platform_events/catalog_requested": _op(
        "GET", f"{_API}/platform-events/catalog", "none", _empty, same=True,
    ),
    "flows/code/documentation_requested": _op(
        "GET", f"{_API}/code/documentation", "query", _setup_code_docs, same=True,
    ),
    "flows/code/templates_requested": _op(
        "GET", f"{_API}/code/templates", "query", _setup_code_templates, same=True,
    ),
    "flows/code/editor_state_requested": _op(
        "GET", f"{_API}/code/editor-state", "query", _setup_code_editor, same=True,
    ),
    "flows/code/source_requested": _op(
        "GET", f"{_API}/code/source", "query", _setup_code_source, same=True,
    ),
    "flows/code/flow_functions_requested": _op(
        "GET", f"{_API}/code/flow-functions", "query", _setup_code_functions, same=True, expect="failed",
    ),
    "flows/code/tool_source_requested": _op(
        "GET", f"{_API}/code/tool-source", "query", _setup_code_tool_source, same=True, expect="failed",
    ),
    "flows/code/parse_signature_requested": _op(
        "POST", f"{_API}/code/parse-signature", "body", _setup_code_parse, same=True,
    ),
    "flows/code/validate_requested": _op(
        "POST", f"{_API}/code/validate", "body", _setup_code_validate, same=True,
    ),
    "flows/code/execute_requested": _op(
        "POST", f"{_API}/code/execute", "body", _setup_code_execute, same=True,
    ),
    "flows/datasources/list_requested": _op(
        "GET", f"{_API}/datasources", "query", _limit, same=True,
    ),
    "flows/datasources/item_requested": _op(
        "GET",
        f"{_API}/datasources/{{datasource_id}}",
        "none",
        _setup_datasource_missing,
        same=True,
        expect="failed",
    ),
    "flows/datasources/create_requested": _op(
        "POST",
        f"{_API}/datasources",
        "body",
        _setup_datasource_create,
        same=True,
        expect="failed",
    ),
    "flows/datasources/update_requested": _op(
        "PATCH",
        f"{_API}/datasources/{{datasource_id}}",
        "body_minus_path",
        _setup_datasource_patch,
        same=True,
        expect="failed",
    ),
    "flows/datasources/remove_requested": _op(
        "DELETE",
        f"{_API}/datasources/{{datasource_id}}",
        "none",
        _setup_datasource_missing,
        same=True,
        expect="failed",
    ),
    "flows/datasources/test_requested": _op(
        "POST",
        f"{_API}/datasources/{{datasource_id}}/test",
        "none",
        _setup_datasource_missing,
        same=True,
        expect="failed",
    ),
    "flows/datasources/introspect_requested": _op(
        "POST",
        f"{_API}/datasources/{{datasource_id}}/introspect",
        "none",
        _setup_datasource_missing,
        same=True,
        expect="failed",
    ),
    "flows/datasources/query_requested": _op(
        "POST",
        f"{_API}/datasources/{{datasource_id}}/query",
        "body_minus_path",
        _setup_datasource_sql,
        same=True,
        expect="failed",
    ),
    "flows/datasources/execute_requested": _op(
        "POST",
        f"{_API}/datasources/{{datasource_id}}/execute",
        "body_minus_path",
        _setup_datasource_sql,
        same=True,
        expect="failed",
    ),
    "flows/datasources/connectors_list_requested": _op(
        "GET", f"{_API}/datasources/connectors", "none", _empty, same=True,
    ),
    "flows/datasources/connectors_upsert_requested": _op(
        "PUT",
        f"{_API}/datasources/connectors",
        "body",
        _setup_connector_upsert,
        same=True,
        expect="failed",
    ),
    "flows/flow_ui/schema_requested": _op("GET", f"{_API}/flow-ui/schema", "none", _empty, same=True),
    "flows/flow_ui/templates_requested": _op(
        "GET", f"{_API}/flow-ui/templates", "query", _setup_flow_ui_templates, same=True,
    ),
    "flows/flow_ui/assist_requested": _op(
        "POST",
        f"{_API}/flow-ui/assist",
        "body",
        _setup_flow_ui_assist,
        same=True,
        expect="failed",
        compare="failed_only",
    ),
    "flows/flow_ui_shares/list_requested": _op(
        "GET", f"{_API}/flow-ui/shares", "query", _setup_share_list, same=True, expect="failed",
    ),
    "flows/flow_ui_shares/create_requested": _op(
        "POST",
        f"{_API}/flow-ui/shares",
        "body_minus_path",
        _setup_share_create,
        same=True,
        expect="failed",
        query_keys=("public_host",),
    ),
    "flows/flow_ui_shares/remove_requested": _op(
        "DELETE",
        f"{_API}/flow-ui/shares/{{grant_id}}",
        "none",
        _setup_share_remove,
        same=True,
        expect="failed",
    ),
    "flows/data_tables/create_requested": _op(
        "POST", f"{_API}/data-tables", "body", _setup_data_table, same=False,
    ),
    "flows/llm_context/resolve_parent_requested": _op(
        "POST", f"{_API}/llm-context/resolve-parent", "body", _setup_llm_context, same=True,
    ),
    "flows/prompts/render_requested": _op(
        "POST", f"{_API}/prompts/render", "body", _setup_prompt, same=True,
    ),
    "flows/registry/providers_list_requested": _op(
        "GET", f"{_API}/registry/providers/values", "query", _empty, same=True,
    ),
    "flows/registry/models_list_requested": _op(
        "GET", f"{_API}/registry/models/values", "query", _empty, same=True,
    ),
    "flows/resources/list_requested": _op("GET", f"{_API}/resources/", "query", _limit, same=True),
    "flows/resources/item_requested": _op(
        "GET", f"{_API}/resources/{{resource_id}}", "none", _setup_resource_item, same=True,
    ),
    "flows/resources/create_requested": _op(
        "POST", f"{_API}/resources/", "body", _setup_resource_create, same=False,
    ),
    "flows/resources/update_requested": _op(
        "PUT",
        f"{_API}/resources/{{resource_id}}",
        "body_minus_path",
        _setup_resource_update,
        same=True,
    ),
    "flows/resources/remove_requested": _op(
        "DELETE", f"{_API}/resources/{{resource_id}}", "none", _setup_resource_item, same=False,
    ),
    "flows/sessions/list_requested": _op(
        "GET", f"{_API}/sessions/", "query", _setup_sessions_list, same=True,
    ),
    "flows/sessions/remove_requested": _op(
        "DELETE",
        f"{_API}/sessions/{{session_id}}",
        "none",
        _setup_session_missing,
        same=True,
        expect="failed",
    ),
    "flows/sessions/state_requested": _op(
        "GET", f"{_API}/tasks/state", "query", _setup_session_state, same=True, expect="failed",
    ),
    "flows/sessions/state_update_requested": _op(
        "PUT",
        f"{_API}/tasks/state",
        "body",
        _setup_session_state_update,
        same=True,
        expect="failed",
    ),
    "flows/durable/history_requested": _op(
        "GET",
        f"{_API}/tasks/{{session_id}}/history",
        "query",
        _setup_durable_history,
        same=True,
    ),
    "flows/durable/branches_requested": _op(
        "GET",
        f"{_API}/tasks/{{session_id}}/branches",
        "none",
        _setup_session_missing,
        same=True,
    ),
    "flows/durable/state_at_requested": _op(
        "GET",
        f"{_API}/tasks/{{session_id}}/state-at/{{sequence}}",
        "query",
        _setup_durable_state_at,
        same=True,
        expect="failed",
    ),
    "flows/durable/fork_requested": _op(
        "POST",
        f"{_API}/tasks/{{session_id}}/fork",
        "body_minus_path",
        _setup_durable_fork,
        same=True,
        expect="failed",
    ),
    "flows/durable/rewind_requested": _op(
        "POST",
        f"{_API}/tasks/{{session_id}}/rewind",
        "body_minus_path",
        _setup_durable_rewind,
        same=True,
        expect="failed",
    ),
    "flows/durable/manual_patch_requested": _op(
        "POST",
        f"{_API}/tasks/{{session_id}}/manual-patch",
        "body_minus_path",
        _setup_durable_patch,
        same=True,
        expect="failed",
    ),
    "flows/durable/retry_from_failure_requested": _op(
        "POST",
        f"{_API}/tasks/{{session_id}}/retry-from-failure",
        "body_minus_path",
        _setup_durable_retry,
        same=True,
        expect="failed",
    ),
    "flows/agent_skills/list_requested": _op(
        "GET", f"{_API}/agent-skills", "query", _limit, same=True,
    ),
    "flows/agent_skills/item_requested": _op(
        "GET", f"{_API}/agent-skills/{{agent_skill_id}}", "none", _setup_skill_item, same=True,
    ),
    "flows/agent_skills/create_requested": _op(
        "POST", f"{_API}/agent-skills", "body", _setup_skill_create, same=False,
    ),
    "flows/agent_skills/update_requested": _op(
        "PUT",
        f"{_API}/agent-skills/{{agent_skill_id}}",
        "body_minus_path",
        _setup_skill_update,
        same=True,
    ),
    "flows/agent_skills/remove_requested": _op(
        "DELETE", f"{_API}/agent-skills/{{agent_skill_id}}", "none", _setup_skill_item, same=False,
    ),
    "flows/agent_skills/import_requested": _op(
        "POST", f"{_API}/agent-skills/import", "body", _setup_skill_import, same=False,
    ),
    "flows/agent_skills/ensure_seed_requested": _op(
        "POST", f"{_API}/agent-skills/ensure-seed", "none", _empty, same=True,
    ),
    # REST-маршрут анонимный (peer capability-gateway без сессии): без company tools,
    # WS идёт с контекстом компании — сравнивается только успех.
    "flows/tool_runtime/manifest_requested": _op(
        "GET", f"{_API}/tool-runtime/manifest", "none", _empty, same=True, compare="succeeded_only",
    ),
    "flows/tool_runtime/call_requested": _op(
        "POST", f"{_API}/tool-runtime/call", "body", _setup_tool_runtime_call, same=True,
    ),
    "flows/browser_preview/status_requested": _op(
        "GET",
        f"{_API}/browser-preview/sessions/{{session_id}}/status",
        "query",
        _setup_browser_preview_session,
        same=True,
        expect="failed",
    ),
    "flows/browser_preview/active_session_requested": _op(
        "GET",
        f"{_API}/browser-preview/tasks/{{task_id}}/active-session",
        "query",
        _setup_browser_preview_task,
        same=True,
    ),
    "flows/browser_preview/click_requested": _op(
        "POST",
        f"{_API}/browser-preview/sessions/{{session_id}}/click",
        "body_minus_path",
        _setup_browser_preview_click,
        same=True,
        expect="failed",
        query_keys=("token",),
    ),
    "flows/browser_preview/key_requested": _op(
        "POST",
        f"{_API}/browser-preview/sessions/{{session_id}}/key",
        "body_minus_path",
        _setup_browser_preview_key,
        same=True,
        expect="failed",
        query_keys=("token",),
    ),
    "flows/browser_preview/text_requested": _op(
        "POST",
        f"{_API}/browser-preview/sessions/{{session_id}}/text",
        "body_minus_path",
        _setup_browser_preview_text,
        same=True,
        expect="failed",
        query_keys=("token",),
    ),
    "flows/browser_preview/takeover_requested": _op(
        "POST",
        f"{_API}/browser-preview/sessions/{{session_id}}/takeover",
        "body_minus_path",
        _setup_browser_preview_takeover,
        same=True,
        expect="failed",
        query_keys=("token",),
    ),
    "flows/browser_preview/takeover_release_requested": _op(
        "POST",
        f"{_API}/browser-preview/sessions/{{session_id}}/takeover/release",
        "body_minus_path",
        _setup_browser_preview_session,
        same=True,
        expect="failed",
        query_keys=("token",),
    ),
    "flows/mcp_servers/list_requested": _op(
        "GET", f"{_API}/mcp/servers", "query", _setup_mcp_list, same=True,
    ),
    "flows/mcp_servers/item_requested": _op(
        "GET",
        f"{_API}/mcp/servers/{{server_id}}",
        "none",
        _setup_mcp_missing,
        same=True,
        expect="failed",
    ),
    "flows/mcp_servers/create_requested": _op(
        "POST", f"{_API}/mcp/servers", "body", _setup_mcp_create, same=False,
    ),
    "flows/mcp_servers/update_requested": _op(
        "PUT",
        f"{_API}/mcp/servers/{{server_id}}",
        "body_minus_path",
        _setup_mcp_update,
        same=True,
        expect="failed",
    ),
    "flows/mcp_servers/remove_requested": _op(
        "DELETE",
        f"{_API}/mcp/servers/{{server_id}}",
        "none",
        _setup_mcp_missing,
        same=True,
        expect="failed",
    ),
    "flows/mcp_servers/sync_requested": _op(
        "POST",
        f"{_API}/mcp/servers/{{server_id}}/sync",
        "none",
        _setup_mcp_missing,
        same=True,
        expect="failed",
    ),
    "flows/mcp_servers/test_requested": _op(
        "POST",
        f"{_API}/mcp/servers/{{server_id}}/test",
        "none",
        _setup_mcp_missing,
        same=True,
        expect="failed",
    ),
    "flows/mcp_servers/reset_catalog_defaults_requested": _op(
        "POST",
        f"{_API}/mcp/servers/{{server_id}}/reset_catalog_defaults",
        "none",
        _setup_mcp_missing,
        same=True,
        expect="failed",
    ),
    "flows/mcp_branding/list_requested": _op(
        "GET", f"{_API}/mcp/branding", "query", _setup_mcp_list, same=True,
    ),
    "flows/mcp_branding/slug_suggest_requested": _op(
        "GET", f"{_API}/mcp/branding/slug-suggest", "query", _setup_branding_suggest, same=True,
    ),
    "flows/mcp_branding/upsert_requested": _op(
        "PUT",
        f"{_API}/mcp/branding/{{server_id}}",
        "body_minus_path",
        _setup_branding_upsert,
        same=True,
        expect="failed",
    ),
    "flows/mcp_branding/remove_requested": _op(
        "DELETE",
        f"{_API}/mcp/branding/{{server_id}}",
        "none",
        _setup_mcp_missing,
        same=True,
        expect="failed",
    ),
    "flows/mcp_catalog/list_requested": _op(
        "GET", f"{_API}/mcp/catalog", "query", _setup_mcp_catalog, same=True,
    ),
    "flows/mcp_catalog/install_requested": _op(
        "POST",
        f"{_API}/mcp/catalog/{{catalog_id}}/install",
        "none",
        _setup_mcp_catalog_id,
        same=True,
        expect="failed",
    ),
    "flows/mcp_catalog/uninstall_requested": _op(
        "DELETE",
        f"{_API}/mcp/catalog/{{catalog_id}}/install",
        "none",
        _setup_mcp_catalog_id,
        same=True,
        expect="failed",
    ),
    "flows/nodes_catalog/list_requested": _op(
        "GET", f"{_API}/nodes/", "query", _setup_node_list, same=True,
    ),
    "flows/nodes_catalog/item_requested": _op(
        "GET", f"{_API}/nodes/{{node_id}}", "none", _setup_node_item, same=True, expect="failed",
    ),
    "flows/nodes_catalog/create_requested": _op(
        "POST", f"{_API}/nodes/", "body", _setup_node_create, same=False,
    ),
    "flows/nodes_catalog/update_requested": _op(
        "PUT",
        f"{_API}/nodes/{{node_id}}",
        "body",
        _setup_node_create,
        same=True,
        expect="failed",
    ),
    "flows/nodes_catalog/remove_requested": _op(
        "DELETE", f"{_API}/nodes/{{node_id}}", "none", _setup_node_item, same=True, expect="failed",
    ),
    "flows/evaluation/evaluator_catalog_requested": _op(
        "GET", f"{_API}/evaluation/evaluator-catalog", "none", _empty, same=True,
    ),
    "flows/evaluation/suites_list_requested": _op(
        "GET", f"{_API}/evaluation/suites", "query", _setup_eval_flow_id, same=True,
    ),
    "flows/evaluation/suite_create_requested": _op(
        "POST", f"{_API}/evaluation/suites", "body", _setup_suite_create, same=False,
    ),
    "flows/evaluation/suite_item_requested": _op(
        "GET", f"{_API}/evaluation/suites/{{suite_id}}", "none", _setup_suite_item, same=True,
    ),
    "flows/evaluation/suite_update_requested": _op(
        "PUT",
        f"{_API}/evaluation/suites/{{suite_id}}",
        "body_minus_path",
        _setup_suite_update,
        same=True,
    ),
    "flows/evaluation/suite_archive_requested": _op(
        "POST",
        f"{_API}/evaluation/suites/{{suite_id}}/archive",
        "none",
        _setup_suite_item,
        same=True,
    ),
    "flows/evaluation/cases_list_requested": _op(
        "GET",
        f"{_API}/evaluation/suites/{{suite_id}}/cases",
        "none",
        _setup_suite_item,
        same=True,
    ),
    "flows/evaluation/case_create_requested": _op(
        "POST",
        f"{_API}/evaluation/suites/{{suite_id}}/cases",
        "body_minus_path",
        _setup_case_create,
        same=False,
    ),
    "flows/evaluation/case_item_requested": _op(
        "GET",
        f"{_API}/evaluation/suites/{{suite_id}}/cases/{{case_id}}",
        "none",
        _setup_case_item,
        same=True,
    ),
    "flows/evaluation/case_update_requested": _op(
        "PUT",
        f"{_API}/evaluation/suites/{{suite_id}}/cases/{{case_id}}",
        "body_minus_path",
        _setup_case_update,
        same=True,
    ),
    "flows/evaluation/case_delete_requested": _op(
        "DELETE",
        f"{_API}/evaluation/suites/{{suite_id}}/cases/{{case_id}}",
        "none",
        _setup_case_item,
        same=False,
    ),
    "flows/evaluation/case_import_requested": _op(
        "POST",
        f"{_API}/evaluation/suites/{{suite_id}}/cases/import",
        "body_minus_path",
        _setup_case_import,
        same=False,
    ),
    "flows/evaluation/case_from_dialog_requested": _op(
        "POST",
        f"{_API}/evaluation/suites/{{suite_id}}/cases/from-dialog",
        "body_minus_path",
        _setup_case_from_dialog,
        same=False,
    ),
    "flows/evaluation/case_from_case_run_requested": _op(
        "POST",
        f"{_API}/evaluation/suites/{{suite_id}}/cases/from-case-run",
        "body_minus_path",
        _setup_case_from_case_run,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/case_from_trace_requested": _op(
        "POST",
        f"{_API}/evaluation/suites/{{suite_id}}/cases/from-trace",
        "body_minus_path",
        _setup_case_from_trace,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/runs_list_requested": _op(
        "GET",
        f"{_API}/evaluation/suites/{{suite_id}}/runs",
        "query",
        _setup_suite_item,
        same=True,
    ),
    "flows/evaluation/run_create_requested": _op(
        "POST", f"{_API}/evaluation/runs", "body", _setup_run_create, same=False,
    ),
    "flows/evaluation/run_get_requested": _op(
        "GET",
        f"{_API}/evaluation/runs/{{run_id}}",
        "none",
        _setup_run_id,
        same=True,
        compare="succeeded_only",
    ),
    "flows/evaluation/run_cancel_requested": _op(
        "POST",
        f"{_API}/evaluation/runs/{{run_id}}/cancel",
        "none",
        _setup_run_id,
        same=True,
        compare="succeeded_only",
    ),
    "flows/evaluation/run_cases_requested": _op(
        "GET",
        f"{_API}/evaluation/runs/{{run_id}}/cases",
        "none",
        _setup_run_id,
        same=True,
        compare="succeeded_only",
    ),
    "flows/evaluation/run_events_requested": _op(
        "GET",
        f"{_API}/evaluation/runs/{{run_id}}/events",
        "none",
        _setup_run_id,
        same=True,
        compare="succeeded_only",
    ),
    "flows/evaluation/run_events_page_requested": _op(
        "GET",
        f"{_API}/evaluation/runs/{{run_id}}/events-page",
        "query",
        _setup_run_events_page,
        same=True,
        compare="succeeded_only",
    ),
    "flows/evaluation/run_jobs_enqueue_pending_requested": _op(
        "POST",
        f"{_API}/evaluation/run-jobs/enqueue-pending",
        "query",
        _setup_jobs,
        same=True,
    ),
    "flows/evaluation/matrix_get_requested": _op(
        "GET",
        f"{_API}/evaluation/suites/{{suite_id}}/matrix",
        "query",
        _setup_matrix,
        same=True,
    ),
    "flows/evaluation/compare_runs_requested": _op(
        "GET",
        f"{_API}/evaluation/runs/compare",
        "query",
        _setup_compare_runs,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/case_run_trace_requested": _op(
        "GET",
        f"{_API}/evaluation/case-runs/{{case_run_id}}/trace",
        "none",
        _setup_case_run_trace,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/annotations_list_requested": _op(
        "GET",
        f"{_API}/evaluation/runs/{{run_id}}/annotations",
        "none",
        _setup_run_id,
        same=True,
    ),
    "flows/evaluation/annotation_create_requested": _op(
        "POST",
        f"{_API}/evaluation/runs/{{run_id}}/annotations",
        "body_minus_path",
        _setup_annotation_create,
        same=False,
    ),
    "flows/evaluation/annotation_update_requested": _op(
        "PUT",
        f"{_API}/evaluation/annotations/{{annotation_id}}",
        "body_minus_path",
        _setup_annotation_item,
        same=True,
    ),
    "flows/evaluation/annotation_delete_requested": _op(
        "DELETE",
        f"{_API}/evaluation/annotations/{{annotation_id}}",
        "none",
        _setup_annotation_id,
        same=False,
    ),
    "flows/evaluation/baselines_list_requested": _op(
        "GET",
        f"{_API}/evaluation/suites/{{suite_id}}/baselines",
        "none",
        _setup_suite_item,
        same=True,
    ),
    "flows/evaluation/baseline_set_requested": _op(
        "PUT",
        f"{_API}/evaluation/suites/{{suite_id}}/baselines/{{branch_id}}",
        "body_minus_path",
        _setup_baseline_set,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/baseline_item_requested": _op(
        "GET",
        f"{_API}/evaluation/suites/{{suite_id}}/baselines/{{branch_id}}",
        "none",
        _setup_baseline_item,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/baseline_compare_requested": _op(
        "GET",
        f"{_API}/evaluation/suites/{{suite_id}}/baseline-compare",
        "query",
        _setup_baseline_compare,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/gate_policies_list_requested": _op(
        "GET",
        f"{_API}/evaluation/suites/{{suite_id}}/gate-policies",
        "none",
        _setup_suite_item,
        same=True,
    ),
    "flows/evaluation/gate_policy_create_requested": _op(
        "POST",
        f"{_API}/evaluation/suites/{{suite_id}}/gate-policies",
        "body_minus_path",
        _setup_gate_create,
        same=False,
    ),
    "flows/evaluation/gate_policy_item_requested": _op(
        "GET",
        f"{_API}/evaluation/gate-policies/{{gate_policy_id}}",
        "none",
        _setup_gate_item,
        same=True,
    ),
    "flows/evaluation/gate_policy_update_requested": _op(
        "PUT",
        f"{_API}/evaluation/gate-policies/{{gate_policy_id}}",
        "body_minus_path",
        _setup_gate_update,
        same=True,
    ),
    "flows/evaluation/gate_policy_archive_requested": _op(
        "POST",
        f"{_API}/evaluation/gate-policies/{{gate_policy_id}}/archive",
        "none",
        _setup_gate_item,
        same=True,
    ),
    "flows/evaluation/gate_policy_run_requested": _op(
        "POST",
        f"{_API}/evaluation/gate-policies/{{gate_policy_id}}/run",
        "body_minus_path",
        _setup_gate_run,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/gate_result_requested": _op(
        "GET",
        f"{_API}/evaluation/runs/{{run_id}}/gate-result",
        "none",
        _setup_run_id,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/monitors_list_requested": _op(
        "GET",
        f"{_API}/evaluation/suites/{{suite_id}}/monitors",
        "none",
        _setup_suite_item,
        same=True,
    ),
    "flows/evaluation/monitor_create_requested": _op(
        "POST", f"{_API}/evaluation/monitors", "body", _setup_monitor_create, same=False,
    ),
    "flows/evaluation/monitor_item_requested": _op(
        "GET",
        f"{_API}/evaluation/monitors/{{monitor_id}}",
        "none",
        _setup_monitor_item,
        same=True,
    ),
    "flows/evaluation/monitor_update_requested": _op(
        "PUT",
        f"{_API}/evaluation/monitors/{{monitor_id}}",
        "body_minus_path",
        _setup_monitor_update,
        same=True,
    ),
    "flows/evaluation/monitor_archive_requested": _op(
        "POST",
        f"{_API}/evaluation/monitors/{{monitor_id}}/archive",
        "none",
        _setup_monitor_item,
        same=True,
    ),
    "flows/evaluation/monitor_sample_requested": _op(
        "POST",
        f"{_API}/evaluation/monitors/{{monitor_id}}/sample",
        "body_minus_path",
        _setup_monitor_sample,
        same=True,
    ),
    "flows/evaluation/monitor_run_cycle_requested": _op(
        "POST",
        f"{_API}/evaluation/monitors/{{monitor_id}}/run-cycle",
        "body_minus_path",
        _setup_monitor_cycle,
        same=True,
    ),
    "flows/evaluation/monitor_cycles_run_active_requested": _op(
        "POST",
        f"{_API}/evaluation/monitor-cycles/run-active",
        "body",
        _setup_monitor_cycles_active,
        same=True,
        compare="marker_row",
        marker_field="monitor.monitor_id",
        list_key="cycles",
    ),
    "flows/evaluation/monitor_observations_requested": _op(
        "GET",
        f"{_API}/evaluation/monitors/{{monitor_id}}/observations",
        "query",
        _setup_monitor_sample,
        same=True,
    ),
    "flows/evaluation/monitor_observation_case_create_requested": _op(
        "POST",
        f"{_API}/evaluation/monitors/{{monitor_id}}/observations/{{trace_id}}/case",
        "body_minus_path",
        _setup_monitor_observation_case,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/pairwise_judgment_create_requested": _op(
        "POST",
        f"{_API}/evaluation/pairwise-judgments",
        "body",
        _setup_pairwise,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/pairwise_judgments_list_requested": _op(
        "GET",
        f"{_API}/evaluation/case-runs/{{case_run_id}}/pairwise-judgments",
        "none",
        _setup_case_run_trace,
        same=True,
        expect="failed",
    ),
    "flows/evaluation/rubrics_list_requested": _op(
        "GET", f"{_API}/evaluation/rubrics", "query", _setup_eval_flow_id, same=True,
    ),
    "flows/evaluation/rubric_create_requested": _op(
        "POST", f"{_API}/evaluation/rubrics", "body", _setup_rubric_create, same=False,
    ),
    "flows/evaluation/rubric_item_requested": _op(
        "GET", f"{_API}/evaluation/rubrics/{{rubric_id}}", "none", _setup_rubric_item, same=True,
    ),
    "flows/evaluation/rubric_update_requested": _op(
        "PUT",
        f"{_API}/evaluation/rubrics/{{rubric_id}}",
        "body_minus_path",
        _setup_rubric_update,
        same=True,
    ),
    "flows/evaluation/rubric_archive_requested": _op(
        "POST",
        f"{_API}/evaluation/rubrics/{{rubric_id}}/archive",
        "none",
        _setup_rubric_item,
        same=True,
    ),
    "flows/evaluation/rubric_versions_list_requested": _op(
        "GET",
        f"{_API}/evaluation/rubrics/{{rubric_id}}/versions",
        "none",
        _setup_rubric_item,
        same=True,
    ),
    "flows/evaluation/rubric_version_create_requested": _op(
        "POST",
        f"{_API}/evaluation/rubrics/{{rubric_id}}/versions",
        "body_minus_path",
        _setup_rubric_version,
        same=False,
    ),
    "flows/code_agent/ensure_source_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/nodes/{{node_id}}/code-agent/ensure-source",
        "query",
        _setup_code_agent,
        same=True,
    ),
    "flows/code_agent/import_git_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/nodes/{{node_id}}/code-agent/import-git",
        "body_minus_path",
        _setup_code_agent_git,
        same=True,
        expect="failed",
    ),
    "flows/code_agent/import_archive_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/nodes/{{node_id}}/code-agent/import-archive",
        "body_minus_path",
        _setup_code_agent_archive,
        same=True,
        expect="failed",
    ),
    "flows/code_agent/copy_tree_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/nodes/{{node_id}}/code-agent/copy-tree",
        "body_minus_path",
        _setup_code_agent_copy,
        same=True,
        expect="failed",
    ),
    "flows/code_agent/rebuild_requested": _op(
        "POST",
        f"{_API}/flows/{{flow_id}}/nodes/{{node_id}}/code-agent/rebuild",
        "body_minus_path",
        _setup_code_agent_rebuild,
        same=True,
    ),
    "flows/code_agent/status_requested": _op(
        "GET",
        f"{_API}/flows/{{flow_id}}/nodes/{{node_id}}/code-agent",
        "query",
        _setup_code_agent,
        same=True,
    ),
    "flows/code_agent/logs_requested": _op(
        "GET",
        f"{_API}/flows/{{flow_id}}/nodes/{{node_id}}/code-agent/logs",
        "query",
        _setup_code_agent,
        same=True,
    ),
    "flows/code_agent/delete_requested": _op(
        "DELETE",
        f"{_API}/flows/{{flow_id}}/nodes/{{node_id}}/code-agent",
        "query",
        _setup_code_agent,
        same=True,
    ),
    "flows/logs/by_trace_requested": _op(
        "GET",
        f"{_API}/observability/logs/by-trace/{{trace_id}}",
        "query",
        _setup_logs_trace,
        same=True,
        expect="failed",
    ),
    "flows/logs/by_session_requested": _op(
        "GET",
        f"{_API}/observability/logs/by-session/{{session_id}}",
        "query",
        _setup_logs_session,
        same=True,
        expect="failed",
    ),
    "flows/logs/by_request_requested": _op(
        "GET",
        f"{_API}/observability/logs/by-request/{{request_id}}",
        "query",
        _setup_logs_request,
        same=True,
        expect="failed",
    ),
    "flows/logs/by_span_requested": _op(
        "GET",
        f"{_API}/observability/logs/by-span/{{span_id}}",
        "query",
        _setup_logs_span,
        same=True,
        expect="failed",
    ),
    "flows/logs/by_user_requested": _op(
        "GET",
        f"{_API}/observability/logs/by-user/{{user_id}}",
        "query",
        _setup_logs_user,
        same=True,
        expect="failed",
    ),
    "flows/traces/search_requested": _op(
        "GET", f"{_API}/traces/search", "query", _setup_traces_search, same=True,
    ),
    "flows/traces/by_session_requested": _op(
        "GET",
        f"{_API}/traces/session/{{session_id}}",
        "query",
        _setup_traces_session,
        same=True,
        expect="failed",
    ),
    "flows/traces/by_task_requested": _op(
        "GET",
        f"{_API}/traces/task/{{task_id}}",
        "query",
        _setup_traces_task,
        same=True,
        expect="failed",
    ),
    "flows/traces/by_trace_requested": _op(
        "GET",
        f"{_API}/traces/trace/{{trace_id}}",
        "query",
        _setup_traces_trace,
        same=True,
        expect="failed",
    ),
    "flows/traces/handoff_chain_requested": _op(
        "GET",
        f"{_API}/traces/handoff-chain/{{parent_session_id}}",
        "none",
        _setup_traces_handoff,
        same=True,
        expect="failed",
    ),
    "flows/voice_providers/catalog_requested": _op(
        "GET", f"{_API}/voice-providers/catalog", "none", _empty, same=True,
    ),
    "flows/hitl/conversation_get_requested": _op(
        "GET",
        f"{_API}/hitl/{{work_item_id}}/conversation",
        "none",
        _setup_hitl,
        same=True,
        expect="failed",
    ),
    "flows/hitl/conversation_send_requested": _op(
        "POST",
        f"{_API}/hitl/{{work_item_id}}/conversation/messages",
        "body_minus_path",
        _setup_hitl_send,
        same=True,
        expect="failed",
    ),
    "flows/lara/pending_actions_apply_requested": _op(
        "POST",
        f"{_API}/lara/pending-actions/apply",
        "body",
        _setup_lara,
        same=True,
        expect="failed",
    ),
    "flows/company/init_requested": _op(
        "POST",
        f"{_API}/company/init",
        "body",
        _setup_company_mismatch,
        same=True,
        expect="failed",
    ),
    "flows/integrations/credentials_list_requested": _op(
        "GET", f"{_API}/integrations/credentials", "none", _empty, same=True,
    ),
    "flows/integrations/credentials_remove_requested": _op(
        "DELETE",
        f"{_API}/integrations/credentials/{{provider}}/{{service}}",
        "none",
        _setup_credentials_remove,
        same=True,
        expect="failed",
    ),
    "flows/integrations/workspace_company_get_requested": _op(
        "GET",
        f"{_API}/integrations/credentials/google/workspace/company",
        "none",
        _empty,
        same=True,
    ),
    "flows/integrations/workspace_company_put_requested": _op(
        "PUT",
        f"{_API}/integrations/credentials/google/workspace/company",
        "body",
        _setup_workspace_put,
        same=True,
        expect="failed",
    ),
    "flows/integrations/workspace_company_delete_requested": _op(
        "DELETE",
        f"{_API}/integrations/credentials/google/workspace/company",
        "none",
        _empty,
        same=True,
        expect="failed",
    ),
}


def _error_code(payload: JsonObject) -> str:
    code = payload.get("error_code")
    if isinstance(code, str) and code:
        return code
    raise AssertionError(f"error_code required, got {payload!r}")


async def _ws_command(
    *,
    auth_token: str,
    realtime_session_client: AsyncClient,
    canonical_type: str,
    payload: JsonObject,
    timeout_sec: float = 25.0,
) -> JsonObject:
    token_data = get_token_service().validate_token(auth_token)
    event_id = str(uuid.uuid4())
    succeeded = canonical_type.removesuffix("_requested") + "_succeeded"
    failed = canonical_type.removesuffix("_requested") + "_failed"
    async with connect_centrifugo(auth_token) as ws:
        accepted = await rpc_platform_event(
            ws,
            event_type=canonical_type,
            payload=payload,
            company_id=token_data.company_id,
            event_id=event_id,
        )
        assert accepted.get("accepted") is True
        assert accepted.get("event_id") == event_id
        deadline = asyncio.get_running_loop().time() + timeout_sec
        terminal_ws: JsonObject | None = None
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            event = await ws.recv_platform_event(timeout=remaining)
            event_type = event.get("type")
            if event_type not in (succeeded, failed):
                continue
            meta = event.get("meta")
            if not isinstance(meta, dict) or meta.get("causation_id") != event_id:
                continue
            terminal_ws = event
            break
    if terminal_ws is None:
        raise AssertionError(f"WS reply для {canonical_type!r} event_id={event_id} не получен")
    stored = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}")
    assert stored.status_code == 200, stored.text
    assert stored.json()["type"] == canonical_type
    terminal_http = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}/terminal")
    assert terminal_http.status_code == 200, terminal_http.text
    terminal = require_json_object(terminal_http.json(), "terminal")
    assert terminal["type"] == terminal_ws["type"]
    assert terminal["meta"]["causation_id"] == event_id
    return terminal_ws


def _query_params(payload: JsonObject, path_params: dict[str, str]) -> dict[str, JsonValue]:
    query: dict[str, JsonValue] = {}
    for key, value in payload.items():
        if key in path_params or value is None:
            continue
        query[key] = value
    return query


async def _rest_command(
    *,
    client: AsyncClient,
    headers: dict[str, str],
    rest: RestMirror,
    payload: JsonObject,
    expect: ExpectMode,
) -> JsonObject:
    path_params: dict[str, str] = {}
    for key in _PATH_PLACEHOLDER.findall(rest.url):
        raw = payload.get(key)
        if isinstance(raw, int) and key == "sequence":
            path_params[key] = str(raw)
            continue
        path_params[key] = _str_field(payload, key)
    url = rest.url.format(**path_params)
    json_body: JsonObject | None = None
    query: dict[str, JsonValue] | None = None
    query_keys = set(rest.query_keys)
    if rest.strategy == "body":
        json_body = dict(payload)
    elif rest.strategy == "body_minus_path":
        body = {
            k: v
            for k, v in payload.items()
            if k not in path_params and k not in query_keys and v is not None
        }
        json_body = body
        if query_keys:
            query = {k: v for k, v in payload.items() if k in query_keys and v is not None}
    elif rest.strategy == "query":
        query = _query_params(payload, path_params)
    elif rest.strategy == "none":
        pass
    else:
        raise AssertionError(f"unknown REST strategy {rest.strategy!r}")
    request_headers = dict(headers)
    if rest.url.startswith(f"{_API}/flow-ui/shares") and rest.method == "POST":
        request_headers["Host"] = "localhost:9001"
    response = await client.request(
        rest.method,
        url,
        headers=request_headers,
        json=json_body,
        params=query,
    )
    if expect == "failed":
        return await _expect_json(
            response,
            ok=(400, 403, 404, 409, 422, 500, 502, 503),
            label=f"REST {rest.method} {url}",
        )
    return await _expect_json(
        response,
        ok=(200, 201, 202, 204),
        label=f"REST {rest.method} {url}",
    )


def _marker_value(row: JsonObject, field: str) -> JsonValue | None:
    current: JsonValue | None = row
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _row_by_marker(
    payload: JsonObject,
    field: str,
    marker: str,
    *,
    list_key: str,
) -> JsonObject:
    items = payload.get(list_key)
    if not isinstance(items, list):
        raise AssertionError(f"list payload must have {list_key}[]")
    matched: list[JsonObject] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if _marker_value(require_json_object(item, "list.row"), field) == marker:
            matched.append(require_json_object(item, "list.row"))
    if len(matched) != 1:
        raise AssertionError(f"expected one row {field}={marker!r}, got {len(matched)}")
    return matched[0]


def test_every_flows_operation_has_live_case() -> None:
    missing = sorted(set(FLOWS_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(FLOWS_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(90)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_flows_op_ws_rest_identical(
    canonical_type: str,
    flows_service: None,
    realtime_service: None,
    frontend_service: None,
    flows_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user2_id: str,
    unique_id: str,
) -> None:
    _ = flows_service, realtime_service, frontend_service
    headers = {**auth_headers_system}
    case = _CASES[canonical_type]
    ws_ctx = LiveCtx(
        client=flows_client_http,
        headers=headers,
        unique_id=unique_id,
        suffix="ws",
        system_user2_id=system_user2_id,
    )
    ws_payload = await case.setup(ws_ctx)
    ws_marker = ws_ctx.marker
    ws_event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type=canonical_type,
        payload=ws_payload,
    )
    if case.expect == "succeeded":
        assert str(ws_event["type"]).endswith("_succeeded"), (
            f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
        )
    else:
        assert str(ws_event["type"]).endswith("_failed"), (
            f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
        )
    ws_result = _event_payload(ws_event)
    if case.same_resource:
        rest_payload = ws_payload
        rest_marker = ws_ctx.marker
    else:
        rest_ctx = LiveCtx(
            client=flows_client_http,
            headers=headers,
            unique_id=unique_id,
            suffix="rest",
            system_user2_id=system_user2_id,
        )
        rest_payload = await case.setup(rest_ctx)
        rest_marker = rest_ctx.marker
    rest_result = await _rest_command(
        client=flows_client_http,
        headers=headers,
        rest=case.rest,
        payload=rest_payload,
        expect=case.expect,
    )
    if case.compare == "marker_row":
        if ws_marker is None or rest_marker is None:
            raise AssertionError("marker_row compare requires marker")
        assert _normalize(
            _row_by_marker(ws_result, case.marker_field, ws_marker, list_key=case.list_key)
        ) == _normalize(
            _row_by_marker(rest_result, case.marker_field, rest_marker, list_key=case.list_key)
        ), f"WS != REST row для {canonical_type}"
        return
    if case.compare == "error_code":
        assert _error_code(ws_result) == _error_code(rest_result), (
            f"WS != REST error_code для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
        )
        return
    if case.compare == "succeeded_only":
        return
    if case.compare == "failed_only":
        return
    assert _normalize(ws_result) == _normalize(rest_result), (
        f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    )
