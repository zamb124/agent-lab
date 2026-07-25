"""Flows editor tools for flow employees / Lara (node/flow patch + embed UI blocks).

Require authenticated user context in the worker.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.runtime_helpers.state_utils import push_ui_event
from apps.flows.src.services.lara_facade import flow_config_from_flow_api_response
from apps.flows.src.services.platform_facades import get_lara_facade
from apps.flows.src.tools.decorator import tool
from core.clients.service_client import ServiceClient
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_array,
    parse_json_object,
    require_json_array,
    require_json_object,
)

if TYPE_CHECKING:
    from core.state import ExecutionState


def _normalize_flows_branch_id(raw_branch_id: str | None) -> str:
    if raw_branch_id is None:
        return "base"
    cleaned = raw_branch_id.strip()
    if not cleaned or cleaned == "default":
        return "base"
    return cleaned


def _resolve_flow_node_scope(flow_data: FlowConfig, resolved_branch: str) -> dict[str, JsonObject]:
    if resolved_branch == "base":
        nodes = flow_data.nodes
        if nodes is None:
            raise ValueError("Flow base nodes are invalid")
        return nodes
    branch_payload = flow_data.branches.get(resolved_branch)
    if branch_payload is None:
        raise ValueError(f"Ветка '{resolved_branch}' не найдена во flow '{flow_data.flow_id}'")
    nodes = branch_payload.nodes
    if nodes is None:
        raise ValueError(f"У ветки '{resolved_branch}' нет объекта nodes")
    return nodes


def _require_flow_node(
    flow_data: FlowConfig, resolved_branch: str, required_node_id: str
) -> JsonObject:
    nodes = _resolve_flow_node_scope(flow_data, resolved_branch)
    node = nodes.get(required_node_id)
    if node is None:
        raise ValueError(f"Node '{required_node_id}' not found in branch '{resolved_branch}'")
    return node


def _flow_branch_entry(flow_data: FlowConfig, resolved_branch: str) -> str | None:
    if resolved_branch == "base":
        return flow_data.entry
    branch_payload = flow_data.branches.get(resolved_branch)
    if branch_payload is None:
        raise ValueError(f"Ветка '{resolved_branch}' не найдена во flow '{flow_data.flow_id}'")
    return branch_payload.entry


def _nodes_index_entries(nodes: dict[str, JsonObject]) -> list[JsonObject]:
    entries: list[JsonObject] = []
    for node_id, node in nodes.items():
        tools_raw = node.get("tools")
        tools_list: list[JsonValue] = []
        if isinstance(tools_raw, list):
            for tool_item in tools_raw:
                if isinstance(tool_item, str):
                    tools_list.append(tool_item)
                elif isinstance(tool_item, dict):
                    tool_id = tool_item.get("tool_id") or tool_item.get("name")
                    if isinstance(tool_id, str) and tool_id:
                        tools_list.append(tool_id)
        name = node.get("name")
        node_type = node.get("type")
        description = node.get("description")
        entries.append(
            {
                "node_id": node_id,
                "name": name if isinstance(name, str) else None,
                "type": node_type if isinstance(node_type, str) else None,
                "description": description if isinstance(description, str) else None,
                "tools": tools_list,
            }
        )
    return entries


def _flow_summary_payload(flow_data: FlowConfig) -> JsonObject:
    return {
        "name": flow_data.name,
        "description": flow_data.description,
        "tags": list(flow_data.tags) if flow_data.tags else [],
        "entry": flow_data.entry,
        "variables_keys": sorted(str(key) for key in flow_data.variables.keys()),
        "branch_ids": sorted(flow_data.branches.keys()),
    }


async def _load_flow_config(flow_id: str) -> FlowConfig:
    client = ServiceClient()
    return flow_config_from_flow_api_response(
        require_json_object(
            await client.get("flows", f"/flows/api/v1/flows/{quote(flow_id, safe='')}"),
            "flows.load_flow_config.response",
        )
    )


class PushEmbedBlocksArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    blocks_json: str = Field(
        ...,
        min_length=2,
        description=(
            "Одна JSON-строка: массив объектов блоков UI. У каждого объекта поле type: "
            "card | table | actions | file_card | text и поля по схеме блока."
        ),
    )


class FlowsReadContextArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    flow_id: str = Field(..., min_length=1, description="ID flow в сервисе flows.")
    branch_id: str | None = Field(
        None,
        description="ID ветки (branch). Для базового графа передай base или оставь пустым.",
    )
    node_id: str | None = Field(
        None,
        description=(
            "ID ноды: если передан, в ответе будет полное тело этой ноды. "
            "Полный graph не возвращается — для одной ноды предпочитай flows_get_node."
        ),
    )


class FlowsGetNodeArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    flow_id: str = Field(..., min_length=1, description="ID flow в сервисе flows.")
    node_id: str = Field(..., min_length=1, description="ID ноды в выбранной ветке.")
    branch_id: str | None = Field(
        None,
        description="ID ветки (branch). Для базового графа передай base или оставь пустым.",
    )


class FlowsListNodesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    flow_id: str = Field(..., min_length=1, description="ID flow в сервисе flows.")
    branch_id: str | None = Field(
        None,
        description="ID ветки (branch). Для базового графа передай base или оставь пустым.",
    )


class FlowsPatchNodeArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    flow_id: str | None = Field(None, description="ID flow (обязателен при mode=propose).")
    node_id: str | None = Field(None, description="ID ноды (обязателен при mode=propose).")
    patch_json: str | None = Field(
        None,
        description="JSON-объект изменений ноды при mode=propose.",
    )
    branch_id: str | None = Field(
        None,
        description="ID ветки (branch). Для base можно не передавать.",
    )
    mode: Literal["propose", "apply"] = Field(
        "propose",
        description="propose — подготовить действие и ждать подтверждения; apply — применить по pending_action_id.",
    )
    pending_action_id: str | None = Field(
        None,
        description="ID действия из propose. Обязателен для mode=apply.",
    )
    idempotency_key: str | None = Field(
        None,
        description="Идемпотентный ключ выполнения. Если не передан, используется pending_action_id.",
    )

    @field_validator("pending_action_id", mode="before")
    @classmethod
    def _strip_pending_patch_node(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @model_validator(mode="after")
    def _flows_patch_node_mode(self) -> "FlowsPatchNodeArgs":
        if self.mode == "apply":
            if self.pending_action_id is None:
                raise ValueError("pending_action_id is required when mode='apply'")
            return self
        fid = self.flow_id
        nid = self.node_id
        pj = self.patch_json
        if not fid or not str(fid).strip():
            raise ValueError("flow_id is required when mode='propose'")
        if not nid or not str(nid).strip():
            raise ValueError("node_id is required when mode='propose'")
        if pj is None or not str(pj).strip():
            raise ValueError("patch_json is required when mode='propose'")
        return self


class FlowsPatchFlowArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    flow_id: str | None = Field(None, description="ID flow (обязателен при mode=propose).")
    patch_json: str | None = Field(
        None,
        description=(
            "JSON-объект изменений flow при mode=propose. Разрешённые поля: name, description, tags, variables."
        ),
    )
    mode: Literal["propose", "apply"] = Field(
        "propose",
        description="propose — подготовить действие и ждать подтверждения; apply — применить по pending_action_id.",
    )
    pending_action_id: str | None = Field(
        None,
        description="ID действия из propose. Обязателен для mode=apply.",
    )
    idempotency_key: str | None = Field(
        None,
        description="Идемпотентный ключ выполнения. Если не передан, используется pending_action_id.",
    )

    @field_validator("pending_action_id", mode="before")
    @classmethod
    def _strip_pending_patch_flow(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @model_validator(mode="after")
    def _flows_patch_flow_mode(self) -> "FlowsPatchFlowArgs":
        if self.mode == "apply":
            if self.pending_action_id is None:
                raise ValueError("pending_action_id is required when mode='apply'")
            return self
        if self.flow_id is None or not str(self.flow_id).strip():
            raise ValueError("flow_id is required when mode='propose'")
        if self.patch_json is None or not str(self.patch_json).strip():
            raise ValueError("patch_json is required when mode='propose'")
        return self


@tool(
    name="push_embed_blocks",
    description=(
        "Отображает блоки UI в чате. Передай blocks_json — JSON-массив объектов "
        "с полем type: card | table | actions | file_card | text и полями схемы."
    ),
    tags=["flows"],
    parameters_model=PushEmbedBlocksArgs,
)
async def push_embed_blocks(blocks_json: str, *, state: "ExecutionState") -> str:
    _ = state
    parsed = parse_json_array(blocks_json, "blocks_json")
    return json.dumps({"blocks": parsed}, ensure_ascii=False)


@tool(
    name="flows_get_node",
    description=(
        "Точечно возвращает одну ноду flow по flow_id + branch_id + node_id "
        "(полный config ноды, включая prompt/code). Не отдаёт весь graph."
    ),
    tags=["flows"],
    parameters_model=FlowsGetNodeArgs,
)
async def flows_get_node(
    flow_id: str,
    node_id: str,
    branch_id: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    flow_config = await _load_flow_config(flow_id)
    resolved_branch_id = _normalize_flows_branch_id(branch_id)
    selected_node = _require_flow_node(flow_config, resolved_branch_id, node_id)
    payload: JsonObject = {
        "success": True,
        "flow_id": flow_id,
        "branch_id": resolved_branch_id,
        "node_id": node_id,
        "node": selected_node,
    }
    return json.dumps(payload, ensure_ascii=False)


@tool(
    name="flows_list_nodes",
    description=(
        "Индекс нод ветки flow: node_id, name, type, description, tools[]. "
        "Без prompt/code тел нод. Для полного тела одной ноды — flows_get_node."
    ),
    tags=["flows"],
    parameters_model=FlowsListNodesArgs,
)
async def flows_list_nodes(
    flow_id: str,
    branch_id: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    flow_config = await _load_flow_config(flow_id)
    resolved_branch_id = _normalize_flows_branch_id(branch_id)
    nodes = _resolve_flow_node_scope(flow_config, resolved_branch_id)
    payload: JsonObject = {
        "success": True,
        "flow_id": flow_id,
        "branch_id": resolved_branch_id,
        "entry": _flow_branch_entry(flow_config, resolved_branch_id),
        "nodes": _nodes_index_entries(nodes),
    }
    return json.dumps(payload, ensure_ascii=False)


@tool(
    name="flows_read_context",
    description=(
        "Лёгкий обзор flow: метаданные + индекс нод выбранной ветки. "
        "Опционально — полное тело одной ноды (node_id). "
        "Не возвращает полный FlowConfig; для одной ноды предпочитай flows_get_node."
    ),
    tags=["flows"],
    parameters_model=FlowsReadContextArgs,
)
async def flows_read_context(
    flow_id: str,
    branch_id: str | None = None,
    node_id: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    flow_config = await _load_flow_config(flow_id)
    resolved_branch_id = _normalize_flows_branch_id(branch_id)
    nodes = _resolve_flow_node_scope(flow_config, resolved_branch_id)
    selected_node: JsonObject | None = None
    if node_id:
        selected_node = _require_flow_node(flow_config, resolved_branch_id, node_id)

    payload: JsonObject = {
        "success": True,
        "flow_id": flow_id,
        "branch_id": resolved_branch_id,
        "node_id": node_id or None,
        "flow": _flow_summary_payload(flow_config),
        "nodes_index": _nodes_index_entries(nodes),
        "node": selected_node,
        "blocks": [
            {
                "type": "card",
                "title": flow_config.name or flow_id,
                "subtitle": f"Flow: {flow_id} | Branch: {resolved_branch_id}",
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


@tool(
    name="flows_patch_node",
    description=(
        "Готовит patch ноды flow для применения во внешнем UI. "
        "Возвращает node_before/node_after и ui_events; сам tool не сохраняет flow."
    ),
    tags=["flows"],
    parameters_model=FlowsPatchNodeArgs,
)
async def flows_patch_node(
    flow_id: str | None = None,
    node_id: str | None = None,
    patch_json: str | None = None,
    branch_id: str | None = None,
    mode: Literal["propose", "apply"] = "propose",
    pending_action_id: str | None = None,
    idempotency_key: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    def normalize_branch_id(raw_branch_id: str | None) -> str:
        if raw_branch_id is None:
            return "base"
        cleaned = raw_branch_id.strip()
        if not cleaned or cleaned == "default":
            return "base"
        return cleaned

    facade = get_lara_facade()

    if mode == "propose":
        if flow_id is None or node_id is None or patch_json is None:
            raise ValueError("flow_id, node_id and patch_json are required for mode=propose")
        patch = parse_json_object(patch_json, "flows_patch_node.patch_json")

        resolved_branch_id = normalize_branch_id(branch_id)
        action = await facade.preview_node_patch(
            flow_id=flow_id,
            node_id=node_id,
            patch=patch,
            branch_id=resolved_branch_id,
            state=state,
            idempotency_key=idempotency_key,
        )
        action_payload = require_json_object(
            action.model_dump(mode="json"),
            "flows.node.preview.action",
        )
        preview_data = action.preview
        node_before = preview_data.get("node_before")
        node_after = preview_data.get("node_after")
        preview_payload: JsonObject = {
            "action": action_payload,
            "patch_kind": "node",
            "flow_id": flow_id,
            "branch_id": resolved_branch_id,
            "node_id": node_id,
            "changes": patch,
            "open_editor": True,
        }
        apply_button = require_json_object(
            {
                "action_id": "flows.node.patch.apply",
                "action_kind": "apply",
                "label": "Применить изменение",
                "pending_action_id": action.pending_action_id,
                "arguments": {
                    "pending_action_id": action.pending_action_id,
                    "flow_id": flow_id,
                    "branch_id": resolved_branch_id,
                    "node_id": node_id,
                },
                "context": {
                    "flow_id": flow_id,
                    "branch_id": resolved_branch_id,
                    "node_id": node_id,
                    "patch_kind": "node",
                },
            },
            "flows.node.preview.apply_button",
        )
        preview_blocks = require_json_array(
            [
                {"type": "text", "text": f"Черновик готов. Подтвердите применение для ноды {node_id}."},
                {"type": "actions", "buttons": [apply_button]},
            ],
            "flows.node.preview.blocks",
        )
        preview_payload["blocks"] = preview_blocks
        _ = push_ui_event(
            state,
            event_type="action_previewed",
            payload=preview_payload,
            event_id=f"flows-node-preview-{action.pending_action_id}",
            version="1.0.0",
        )
        return json.dumps(
            {
                "success": True,
                "mode": mode,
                "flow_id": flow_id,
                "branch_id": resolved_branch_id,
                "node_id": node_id,
                "pending_action_id": action.pending_action_id,
                "action": action_payload,
                "node_before": node_before,
                "node_after": node_after,
                "blocks": preview_blocks,
            },
            ensure_ascii=False,
        )

    if not pending_action_id:
        raise ValueError("pending_action_id is required for mode=apply")
    action = await facade.apply_node_patch(
        pending_action_id=pending_action_id,
        state=state,
        idempotency_key=idempotency_key,
    )
    action_payload = require_json_object(
        action.model_dump(mode="json"),
        "flows.node.apply.action",
    )
    target = action.target
    flow_resolved = target.get("flow_id")
    node_resolved = target.get("node_id")
    if not isinstance(flow_resolved, str) or not flow_resolved.strip():
        raise ValueError("Pending action target.flow_id is missing")
    if not isinstance(node_resolved, str) or not node_resolved.strip():
        raise ValueError("Pending action target.node_id is missing")
    branch_resolved = target.get("branch_id")
    if branch_resolved is not None and not isinstance(branch_resolved, str):
        raise ValueError("Pending action target.branch_id must be a string")
    resolved_branch_id = normalize_branch_id(branch_resolved)

    preview_data = action.preview
    node_before = preview_data.get("node_before")
    node_after = preview_data.get("node_after")
    patch_raw = action.payload.get("patch")
    if not isinstance(patch_raw, dict):
        raise ValueError("Pending action payload.patch is missing")
    patch_restored = require_json_object(patch_raw, "flows.node.apply.patch")
    event_payload: JsonObject = {
        "action": action_payload,
        "patch_kind": "node",
        "flow_id": flow_resolved,
        "branch_id": resolved_branch_id,
        "node_id": node_resolved,
        "changes": patch_restored,
        "open_editor": True,
    }
    _ = push_ui_event(
        state,
        event_type="action_applied",
        payload=event_payload,
        event_id=f"flows-node-apply-{pending_action_id}",
        version="1.0.0",
    )
    result = {
        "success": True,
        "mode": mode,
        "flow_id": flow_resolved,
        "branch_id": resolved_branch_id,
        "node_id": node_resolved,
        "pending_action_id": pending_action_id,
        "node_before": node_before,
        "node_after": node_after,
        "blocks": [{"type": "text", "text": f"Изменение для ноды {node_resolved} применено."}],
    }
    return json.dumps(result, ensure_ascii=False)


@tool(
    name="flows_patch_flow",
    description=(
        "Готовит patch к самому flow (name/description/tags/variables) для применения во внешнем UI. "
        "Возвращает flow_before/flow_after и ui_events; сам tool не сохраняет flow."
    ),
    tags=["flows"],
    parameters_model=FlowsPatchFlowArgs,
)
async def flows_patch_flow(
    flow_id: str | None = None,
    patch_json: str | None = None,
    mode: Literal["propose", "apply"] = "propose",
    pending_action_id: str | None = None,
    idempotency_key: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    facade = get_lara_facade()

    if mode == "propose":
        if flow_id is None or patch_json is None:
            raise ValueError("flow_id and patch_json are required for mode=propose")
        patch = parse_json_object(patch_json, "flows_patch_flow.patch_json")

        allowed_fields = {"name", "description", "tags", "variables"}
        unsupported = sorted(set(patch.keys()) - allowed_fields)
        if unsupported:
            allowed = "Allowed: name, description, tags, variables."
            raise ValueError(f"Unsupported flow patch fields: {', '.join(unsupported)}. {allowed}")

        action = await facade.preview_flow_patch(
            flow_id=flow_id,
            patch=patch,
            state=state,
            idempotency_key=idempotency_key,
        )
        action_payload = require_json_object(
            action.model_dump(mode="json"),
            "flows.flow.preview.action",
        )
        preview_data = action.preview
        flow_before = preview_data.get("flow_before")
        flow_after = preview_data.get("flow_after")
        preview_payload: JsonObject = {
            "action": action_payload,
            "patch_kind": "flow",
            "flow_id": flow_id,
            "flow_changes": patch,
            "open_editor": True,
        }
        apply_button = require_json_object(
            {
                "action_id": "flows.flow.patch.apply",
                "action_kind": "apply",
                "label": "Применить изменение",
                "pending_action_id": action.pending_action_id,
                "arguments": {"pending_action_id": action.pending_action_id, "flow_id": flow_id},
                "context": {"flow_id": flow_id, "patch_kind": "flow"},
            },
            "flows.flow.preview.apply_button",
        )
        preview_blocks = require_json_array(
            [
                {"type": "text", "text": f"Черновик готов. Подтвердите применение для flow {flow_id}."},
                {"type": "actions", "buttons": [apply_button]},
            ],
            "flows.flow.preview.blocks",
        )
        preview_payload["blocks"] = preview_blocks
        _ = push_ui_event(
            state,
            event_type="action_previewed",
            payload=preview_payload,
            event_id=f"flows-flow-preview-{action.pending_action_id}",
            version="1.0.0",
        )
        return json.dumps(
            {
                "success": True,
                "mode": mode,
                "flow_id": flow_id,
                "pending_action_id": action.pending_action_id,
                "action": action_payload,
                "flow_before": flow_before,
                "flow_after": flow_after,
                "blocks": preview_blocks,
            },
            ensure_ascii=False,
        )

    if not pending_action_id:
        raise ValueError("pending_action_id is required for mode=apply")
    action = await facade.apply_flow_patch(
        pending_action_id=pending_action_id,
        state=state,
        idempotency_key=idempotency_key,
    )
    action_payload = require_json_object(
        action.model_dump(mode="json"),
        "flows.flow.apply.action",
    )
    target = action.target
    flow_resolved = target.get("flow_id")
    if not isinstance(flow_resolved, str) or not flow_resolved.strip():
        raise ValueError("Pending action target.flow_id is missing")

    preview_data = action.preview
    flow_before = preview_data.get("flow_before")
    flow_after = preview_data.get("flow_after")

    patch_raw = action.payload.get("patch")
    if not isinstance(patch_raw, dict):
        raise ValueError("Pending action payload.patch is missing")
    patch_restored = require_json_object(patch_raw, "flows.flow.apply.patch")

    apply_payload: JsonObject = {
        "action": action_payload,
        "patch_kind": "flow",
        "flow_id": flow_resolved,
        "flow_changes": patch_restored,
        "open_editor": True,
    }
    _ = push_ui_event(
        state,
        event_type="action_applied",
        payload=apply_payload,
        event_id=f"flows-flow-apply-{pending_action_id}",
        version="1.0.0",
    )
    result = {
        "success": True,
        "mode": mode,
        "flow_id": flow_resolved,
        "pending_action_id": pending_action_id,
        "flow_before": flow_before,
        "flow_after": flow_after,
        "blocks": [{"type": "text", "text": f"Изменение для flow {flow_resolved} применено."}],
    }
    return json.dumps(result, ensure_ascii=False)


