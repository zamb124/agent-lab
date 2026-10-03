"""FlowsClient — REST load of FlowConfig + Lara propose/apply for editor tools.

LLM `mode=propose|apply` is a workflow switch, not authorization. Apply still requires a
server-validated `pending_action_id` from a prior propose (LaraActionEngine).

ToolApprovalStore is written alongside Lara pending actions (approval_id in propose response).
LaraActionEngine remains the apply path until Phase 4 migration.
"""

from __future__ import annotations

from urllib.parse import quote

from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.services.flow_ui_cards import show_action_preview, show_action_result
from apps.flows.src.services.lara_facade import LaraFacade, flow_config_from_flow_api_response
from apps.flows.src.services.tool_approval import ToolApprovalStore
from core.clients.service_client import ServiceClient
from core.context import get_context
from core.state import ExecutionState
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_object,
    require_json_array,
    require_json_object,
)


def normalize_flows_branch_id(raw_branch_id: str | None) -> str:
    if raw_branch_id is None:
        return "base"
    cleaned = raw_branch_id.strip()
    if not cleaned or cleaned == "default":
        return "base"
    return cleaned


def resolve_flow_node_scope(
    flow_data: FlowConfig, resolved_branch: str
) -> dict[str, JsonObject]:
    if resolved_branch == "base":
        nodes = flow_data.nodes
        if nodes is None:
            raise ValueError("Flow base nodes are invalid")
        return nodes
    branch_payload = flow_data.branches.get(resolved_branch)
    if branch_payload is None:
        raise ValueError(f"Branch '{resolved_branch}' not found in flow '{flow_data.flow_id}'")
    nodes = branch_payload.nodes
    if nodes is None:
        raise ValueError(f"Branch '{resolved_branch}' has no nodes object")
    return nodes


def require_flow_node(
    flow_data: FlowConfig, resolved_branch: str, required_node_id: str
) -> JsonObject:
    nodes = resolve_flow_node_scope(flow_data, resolved_branch)
    node = nodes.get(required_node_id)
    if node is None:
        raise ValueError(f"Node '{required_node_id}' not found in branch '{resolved_branch}'")
    return node


def flow_branch_entry(flow_data: FlowConfig, resolved_branch: str) -> str | None:
    if resolved_branch == "base":
        return flow_data.entry
    branch_payload = flow_data.branches.get(resolved_branch)
    if branch_payload is None:
        raise ValueError(f"Branch '{resolved_branch}' not found in flow '{flow_data.flow_id}'")
    return branch_payload.entry


def nodes_index_entries(nodes: dict[str, JsonObject]) -> list[JsonObject]:
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


def flow_summary_payload(flow_data: FlowConfig) -> JsonObject:
    return {
        "name": flow_data.name,
        "description": flow_data.description,
        "tags": list(flow_data.tags) if flow_data.tags else [],
        "entry": flow_data.entry,
        "variables_keys": sorted(str(key) for key in flow_data.variables.keys()),
        "branch_ids": sorted(flow_data.branches.keys()),
    }


class FlowsClient:
    """REST load of FlowConfig plus LaraActionEngine propose/apply for patches."""

    _lara_facade: LaraFacade
    _tool_approval_store: ToolApprovalStore

    def __init__(
        self,
        *,
        lara_facade: LaraFacade,
        tool_approval_store: ToolApprovalStore,
        service_client: ServiceClient | None = None,
    ) -> None:
        self._lara_facade = lara_facade
        self._tool_approval_store = tool_approval_store
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    async def load_flow_config(self, flow_id: str) -> FlowConfig:
        return flow_config_from_flow_api_response(
            require_json_object(
                await self._http.get(
                    "flows", f"/flows/api/v1/flows/{quote(flow_id, safe='')}"
                ),
                "flows.load_flow_config.response",
            )
        )

    async def get_node(
        self,
        flow_id: str,
        node_id: str,
        branch_id: str | None = None,
    ) -> JsonObject:
        flow_config = await self.load_flow_config(flow_id)
        resolved_branch_id = normalize_flows_branch_id(branch_id)
        selected_node = require_flow_node(flow_config, resolved_branch_id, node_id)
        return {
            "success": True,
            "flow_id": flow_id,
            "branch_id": resolved_branch_id,
            "node_id": node_id,
            "node": selected_node,
        }

    async def list_nodes(
        self,
        flow_id: str,
        branch_id: str | None = None,
    ) -> JsonObject:
        flow_config = await self.load_flow_config(flow_id)
        resolved_branch_id = normalize_flows_branch_id(branch_id)
        nodes = resolve_flow_node_scope(flow_config, resolved_branch_id)
        return {
            "success": True,
            "flow_id": flow_id,
            "branch_id": resolved_branch_id,
            "entry": flow_branch_entry(flow_config, resolved_branch_id),
            "nodes": nodes_index_entries(nodes),
        }

    async def read_context(
        self,
        flow_id: str,
        branch_id: str | None = None,
        node_id: str | None = None,
    ) -> JsonObject:
        flow_config = await self.load_flow_config(flow_id)
        resolved_branch_id = normalize_flows_branch_id(branch_id)
        nodes = resolve_flow_node_scope(flow_config, resolved_branch_id)
        selected_node: JsonObject | None = None
        if node_id:
            selected_node = require_flow_node(flow_config, resolved_branch_id, node_id)
        return {
            "success": True,
            "flow_id": flow_id,
            "branch_id": resolved_branch_id,
            "node_id": node_id or None,
            "flow": flow_summary_payload(flow_config),
            "nodes_index": nodes_index_entries(nodes),
            "node": selected_node,
            "blocks": [
                {
                    "type": "card",
                    "title": flow_config.name or flow_id,
                    "subtitle": f"Flow: {flow_id} | Branch: {resolved_branch_id}",
                }
            ],
        }

    async def propose_node_patch(
        self,
        *,
        flow_id: str,
        node_id: str,
        patch_json: str,
        state: ExecutionState,
        branch_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> JsonObject:
        patch = parse_json_object(patch_json, "flows_patch_node.patch_json")
        resolved_branch_id = normalize_flows_branch_id(branch_id)
        action = await self._lara_facade.preview_node_patch(
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
                {
                    "type": "text",
                    "text": f"Черновик готов. Подтвердите применение для ноды {node_id}.",
                },
                {"type": "actions", "buttons": [apply_button]},
            ],
            "flows.node.preview.blocks",
        )
        preview_payload["blocks"] = preview_blocks
        _ = show_action_preview(
            state,
            card_id=f"flows-node-preview-{action.pending_action_id}",
            title=f"Изменение ноды {node_id}",
            summary="Черновик готов. Подтвердите применение.",
            parameters=preview_payload,
            apply_action="apply_pending_action",
            apply_payload={
                "pending_action_id": action.pending_action_id,
                "flow_id": flow_id,
                "branch_id": resolved_branch_id,
                "node_id": node_id,
            },
            apply_label="Применить изменение",
        )
        ctx = get_context()
        if ctx is None:
            raise RuntimeError("Context is not set")
        if ctx.active_company is None:
            raise RuntimeError("Active company is required")
        approval_args: JsonObject = {
            "flow_id": flow_id,
            "branch_id": resolved_branch_id,
            "node_id": node_id,
            "patch": patch,
        }
        approval = await self._tool_approval_store.create_pending(
            actor_user_id=ctx.user.user_id,
            company_id=ctx.active_company.company_id,
            tool_id="flows_patch_node",
            definition_version="1",
            args=approval_args,
        )
        return {
            "success": True,
            "mode": "propose",
            "flow_id": flow_id,
            "branch_id": resolved_branch_id,
            "node_id": node_id,
            "pending_action_id": action.pending_action_id,
            "approval_id": approval.approval_id,
            "action": action_payload,
            "node_before": node_before,
            "node_after": node_after,
            "blocks": preview_blocks,
        }

    async def apply_node_patch(
        self,
        *,
        pending_action_id: str,
        state: ExecutionState,
        idempotency_key: str | None = None,
    ) -> JsonObject:
        action = await self._lara_facade.apply_node_patch(
            pending_action_id=pending_action_id,
            state=state,
            idempotency_key=idempotency_key,
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
        resolved_branch_id = normalize_flows_branch_id(branch_resolved)

        preview_data = action.preview
        node_before = preview_data.get("node_before")
        node_after = preview_data.get("node_after")
        _ = show_action_result(
            state,
            card_id=f"flows-node-apply-{pending_action_id}",
            title=f"Нода {node_resolved} обновлена",
            status="success",
            summary=f"Изменение применено во flow {flow_resolved}.",
        )
        return {
            "success": True,
            "mode": "apply",
            "flow_id": flow_resolved,
            "branch_id": resolved_branch_id,
            "node_id": node_resolved,
            "pending_action_id": pending_action_id,
            "node_before": node_before,
            "node_after": node_after,
            "blocks": [
                {"type": "text", "text": f"Изменение для ноды {node_resolved} применено."}
            ],
        }

    async def propose_flow_patch(
        self,
        *,
        flow_id: str,
        patch_json: str,
        state: ExecutionState,
        idempotency_key: str | None = None,
    ) -> JsonObject:
        patch = parse_json_object(patch_json, "flows_patch_flow.patch_json")
        allowed_fields = {"name", "description", "tags", "variables"}
        unsupported = sorted(set(patch.keys()) - allowed_fields)
        if unsupported:
            allowed = "Allowed: name, description, tags, variables."
            raise ValueError(
                f"Unsupported flow patch fields: {', '.join(unsupported)}. {allowed}"
            )

        action = await self._lara_facade.preview_flow_patch(
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
                "arguments": {
                    "pending_action_id": action.pending_action_id,
                    "flow_id": flow_id,
                },
                "context": {"flow_id": flow_id, "patch_kind": "flow"},
            },
            "flows.flow.preview.apply_button",
        )
        preview_blocks = require_json_array(
            [
                {
                    "type": "text",
                    "text": f"Черновик готов. Подтвердите применение для flow {flow_id}.",
                },
                {"type": "actions", "buttons": [apply_button]},
            ],
            "flows.flow.preview.blocks",
        )
        preview_payload["blocks"] = preview_blocks
        _ = show_action_preview(
            state,
            card_id=f"flows-flow-preview-{action.pending_action_id}",
            title=f"Изменение flow {flow_id}",
            summary="Черновик готов. Подтвердите применение.",
            parameters=preview_payload,
            apply_action="apply_pending_action",
            apply_payload={"pending_action_id": action.pending_action_id, "flow_id": flow_id},
            apply_label="Применить изменение",
        )
        return {
            "success": True,
            "mode": "propose",
            "flow_id": flow_id,
            "pending_action_id": action.pending_action_id,
            "action": action_payload,
            "flow_before": flow_before,
            "flow_after": flow_after,
            "blocks": preview_blocks,
        }

    async def apply_flow_patch(
        self,
        *,
        pending_action_id: str,
        state: ExecutionState,
        idempotency_key: str | None = None,
    ) -> JsonObject:
        action = await self._lara_facade.apply_flow_patch(
            pending_action_id=pending_action_id,
            state=state,
            idempotency_key=idempotency_key,
        )
        target = action.target
        flow_resolved = target.get("flow_id")
        if not isinstance(flow_resolved, str) or not flow_resolved.strip():
            raise ValueError("Pending action target.flow_id is missing")

        preview_data = action.preview
        flow_before = preview_data.get("flow_before")
        flow_after = preview_data.get("flow_after")

        _ = show_action_result(
            state,
            card_id=f"flows-flow-apply-{pending_action_id}",
            title=f"Flow {flow_resolved} обновлён",
            status="success",
            summary="Изменение применено.",
        )
        return {
            "success": True,
            "mode": "apply",
            "flow_id": flow_resolved,
            "pending_action_id": pending_action_id,
            "flow_before": flow_before,
            "flow_after": flow_after,
            "blocks": [
                {
                    "type": "text",
                    "text": f"Изменение для flow {flow_resolved} применено.",
                }
            ],
        }
