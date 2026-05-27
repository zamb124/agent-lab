"""
Единый фасад Lara для mutating/read операций из eval-инструментов.
"""

from __future__ import annotations

from typing import ClassVar, Protocol
from urllib.parse import quote

from apps.crm.models.api import EntityCreate, EntityResponse
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.services.lara_action_engine import LaraActionEngine, LaraPendingAction
from core.clients.service_client import ServiceClient
from core.context import get_context
from core.types import JsonObject, require_json_object


class LaraToolState(Protocol):
    context_id: str


class _MinimalLaraToolState:
    """Минимальный state для LaraFacade при HTTP/embed apply (нужен только context_id)."""

    __slots__: ClassVar[tuple[str]] = ("context_id",)

    context_id: str

    def __init__(self, context_id: str) -> None:
        cid = str(context_id).strip()
        if not cid:
            raise ValueError("context_id must be non-empty")
        self.context_id = cid


_FLOW_CONFIG_RESPONSE_KEYS = frozenset(
    {
        "flow_id",
        "version",
        "name",
        "description",
        "type",
        "entry",
        "nodes",
        "edges",
        "variables",
        "tags",
        "branches",
        "hidden",
        "url",
        "headers",
        "status",
        "last_health_check",
        "agent_card",
        "triggers",
        "resources",
        "metadata",
        "store_card_image_url",
        "source",
        "speech",
    }
)
_BRANCH_CONFIG_RESPONSE_KEYS = frozenset(
    {
        "name",
        "description",
        "tags",
        "permission",
        "entry",
        "nodes",
        "edges",
        "variables",
        "nodes_mode",
        "edges_mode",
        "variables_mode",
        "resources",
        "resources_mode",
        "speech",
    }
)


def _known_non_null_fields(source: JsonObject, keys: frozenset[str]) -> JsonObject:
    payload: JsonObject = {}
    for key in keys:
        if key in source and source[key] is not None:
            payload[key] = source[key]
    return payload


def flow_config_from_flow_api_response(response: JsonObject) -> FlowConfig:
    """Преобразует FlowResponse REST API в строгий FlowConfig без UI-only полей ответа."""
    payload = _known_non_null_fields(response, _FLOW_CONFIG_RESPONSE_KEYS)
    branches_raw = response.get("branches")
    if branches_raw is not None:
        branches = require_json_object(branches_raw, "flows.response.branches")
        payload["branches"] = {
            branch_id: _known_non_null_fields(
                require_json_object(branch_payload, f"flows.response.branches.{branch_id}"),
                _BRANCH_CONFIG_RESPONSE_KEYS,
            )
            for branch_id, branch_payload in branches.items()
        }
    return FlowConfig.model_validate(payload)


class LaraFacade:
    """Безопасный фасад для тулов: preview/apply через LaraActionEngine."""

    def __init__(self, action_engine: LaraActionEngine):
        self._action_engine: LaraActionEngine = action_engine
        self._client: ServiceClient = ServiceClient()

    @staticmethod
    def _encode_flow_id(flow_id: str) -> str:
        return quote(flow_id, safe="")

    @staticmethod
    def _require_runtime_ids(state: LaraToolState) -> tuple[str, str, str]:
        ctx = get_context()
        if ctx is None:
            raise RuntimeError("Context is not set")
        if ctx.active_company is None:
            raise RuntimeError("Active company is required")
        context_id = state.context_id
        if not context_id:
            raise ValueError("state.context_id is required")
        return ctx.active_company.company_id, ctx.user.user_id, context_id

    @staticmethod
    def _resolve_graph_nodes(
        flow_config: FlowConfig,
        *,
        flow_id: str,
        branch_id: str,
    ) -> dict[str, JsonObject]:
        if branch_id == "base":
            if flow_config.nodes is None:
                raise ValueError(f"Flow '{flow_id}' has no base nodes")
            return flow_config.nodes

        branch_cfg = flow_config.branches.get(branch_id)
        if branch_cfg is None:
            raise ValueError(f"Branch '{branch_id}' not found in flow '{flow_id}'")
        if branch_cfg.nodes is None:
            raise ValueError(f"Branch '{branch_id}' has no nodes")
        return branch_cfg.nodes

    async def preview_crm_create_note(
        self,
        *,
        name: str,
        description: str,
        note_date: str | None,
        namespace: str,
        state: LaraToolState,
        idempotency_key: str | None,
    ) -> LaraPendingAction:
        company_id, user_id, context_id = self._require_runtime_ids(state)
        payload: JsonObject = {
            "name": name,
            "description": description,
            "namespace": namespace,
        }
        if note_date is not None:
            payload["note_date"] = note_date
        preview: JsonObject = {
            "summary": "Создать заметку в CRM",
            "fields": payload,
        }
        action = await self._action_engine.preview_action(
            company_id=company_id,
            user_id=user_id,
            context_id=context_id,
            capability="crm.note",
            operation="create",
            target={"service": "crm", "resource": "entity", "entity_subtype": "note"},
            payload=payload,
            preview=preview,
            risk="low",
            requires_confirmation=True,
            idempotency_key=idempotency_key,
        )
        return action

    async def apply_crm_create_note(
        self,
        *,
        pending_action_id: str,
        state: LaraToolState,
        idempotency_key: str | None,
    ) -> LaraPendingAction:
        company_id, user_id, context_id = self._require_runtime_ids(state)

        async def _apply(action: LaraPendingAction) -> JsonObject:
            entity_create = EntityCreate.model_validate(
                {
                    "entity_type": "note",
                    **action.payload,
                }
            )
            body = require_json_object(
                entity_create.model_dump(mode="json", exclude_none=True),
                "crm.note.create.body",
            )
            response = await self._client.post("crm", "/crm/api/v1/entities", json=body)
            entity = EntityResponse.model_validate(response)
            entity_payload = require_json_object(
                entity.model_dump(mode="json"),
                "crm.note.create.response",
            )
            return {
                "entity": entity_payload,
                "message": "Заметка создана",
            }

        return await self._action_engine.apply_action(
            company_id=company_id,
            user_id=user_id,
            context_id=context_id,
            pending_action_id=pending_action_id,
            idempotency_key=idempotency_key,
            apply_fn=_apply,
        )

    async def preview_node_patch(
        self,
        *,
        flow_id: str,
        node_id: str,
        patch: JsonObject,
        branch_id: str | None,
        state: LaraToolState,
        idempotency_key: str | None,
    ) -> LaraPendingAction:
        company_id, user_id, context_id = self._require_runtime_ids(state)
        encoded_flow_id = self._encode_flow_id(flow_id)
        flow_config = flow_config_from_flow_api_response(
            require_json_object(
                await self._client.get("flows", f"/flows/api/v1/flows/{encoded_flow_id}"),
                "flows.node.preview.response",
            )
        )
        resolved_branch_id = branch_id or "base"
        graph_nodes = self._resolve_graph_nodes(
            flow_config,
            flow_id=flow_id,
            branch_id=resolved_branch_id,
        )
        node_before = graph_nodes.get(node_id)
        if node_before is None:
            raise ValueError(f"Node '{node_id}' not found in branch '{resolved_branch_id}'")
        node_after: JsonObject = {**node_before, **patch}
        action = await self._action_engine.preview_action(
            company_id=company_id,
            user_id=user_id,
            context_id=context_id,
            capability="flows.node",
            operation="patch",
            target={"flow_id": flow_id, "branch_id": resolved_branch_id, "node_id": node_id},
            payload={"patch": patch},
            preview={
                "summary": "Изменение ноды flow",
                "node_before": node_before,
                "node_after": node_after,
            },
            risk="medium",
            requires_confirmation=True,
            idempotency_key=idempotency_key,
        )
        return action

    async def apply_node_patch(
        self,
        *,
        pending_action_id: str,
        state: LaraToolState,
        idempotency_key: str | None,
    ) -> LaraPendingAction:
        company_id, user_id, context_id = self._require_runtime_ids(state)

        async def _apply(action: LaraPendingAction) -> JsonObject:
            flow_id_raw = action.target.get("flow_id")
            node_id_raw = action.target.get("node_id")
            branch_id_raw = action.target.get("branch_id")
            patch_raw = action.payload.get("patch")
            if not isinstance(flow_id_raw, str) or not flow_id_raw.strip():
                raise ValueError("Pending action target.flow_id is missing")
            if not isinstance(node_id_raw, str) or not node_id_raw.strip():
                raise ValueError("Pending action target.node_id is missing")
            if branch_id_raw is not None and not isinstance(branch_id_raw, str):
                raise ValueError("Pending action target.branch_id must be a string")
            if not isinstance(patch_raw, dict):
                raise ValueError("Pending action payload.patch is missing")
            flow_id = flow_id_raw.strip()
            node_id = node_id_raw.strip()
            branch_id = branch_id_raw.strip() if isinstance(branch_id_raw, str) and branch_id_raw.strip() else "base"
            patch = require_json_object(patch_raw, "pending_action.payload.patch")
            encoded_flow_id = self._encode_flow_id(flow_id)
            flow_config = flow_config_from_flow_api_response(
                require_json_object(
                    await self._client.get("flows", f"/flows/api/v1/flows/{encoded_flow_id}"),
                    "flows.node.apply.response",
                )
            )
            graph_nodes = self._resolve_graph_nodes(
                flow_config,
                flow_id=flow_id,
                branch_id=branch_id,
            )
            node_before = graph_nodes.get(node_id)
            if node_before is None:
                raise ValueError(f"Node '{node_id}' not found in branch '{branch_id}'")
            graph_nodes[node_id] = {**node_before, **patch}
            _ = await self._client.put(
                "flows",
                f"/flows/api/v1/flows/{encoded_flow_id}",
                json=require_json_object(
                    flow_config.model_dump(mode="json"),
                    "flows.node.patch.flow_config",
                ),
            )
            return {"flow_id": flow_id, "node_id": node_id, "patch": patch}

        return await self._action_engine.apply_action(
            company_id=company_id,
            user_id=user_id,
            context_id=context_id,
            pending_action_id=pending_action_id,
            idempotency_key=idempotency_key,
            apply_fn=_apply,
        )

    async def preview_flow_patch(
        self,
        *,
        flow_id: str,
        patch: JsonObject,
        state: LaraToolState,
        idempotency_key: str | None,
    ) -> LaraPendingAction:
        company_id, user_id, context_id = self._require_runtime_ids(state)
        encoded_flow_id = self._encode_flow_id(flow_id)
        flow_before = flow_config_from_flow_api_response(
            require_json_object(
                await self._client.get("flows", f"/flows/api/v1/flows/{encoded_flow_id}"),
                "flows.flow.preview.response",
            )
        )
        flow_before_payload = require_json_object(
            flow_before.model_dump(mode="json"),
            "flows.flow.patch.before",
        )
        flow_after = FlowConfig.model_validate({**flow_before_payload, **patch})
        flow_after_payload = require_json_object(
            flow_after.model_dump(mode="json"),
            "flows.flow.patch.after",
        )
        action = await self._action_engine.preview_action(
            company_id=company_id,
            user_id=user_id,
            context_id=context_id,
            capability="flows.flow",
            operation="patch",
            target={"flow_id": flow_id},
            payload={"patch": patch},
            preview={
                "summary": "Изменение метаданных flow",
                "flow_before": flow_before_payload,
                "flow_after": flow_after_payload,
            },
            risk="medium",
            requires_confirmation=True,
            idempotency_key=idempotency_key,
        )
        return action

    async def apply_flow_patch(
        self,
        *,
        pending_action_id: str,
        state: LaraToolState,
        idempotency_key: str | None,
    ) -> LaraPendingAction:
        company_id, user_id, context_id = self._require_runtime_ids(state)

        async def _apply(action: LaraPendingAction) -> JsonObject:
            flow_id_raw = action.target.get("flow_id")
            patch_raw = action.payload.get("patch")
            if not isinstance(flow_id_raw, str) or not flow_id_raw.strip():
                raise ValueError("Pending action target.flow_id is missing")
            if not isinstance(patch_raw, dict):
                raise ValueError("Pending action payload.patch is missing")
            flow_id = flow_id_raw.strip()
            patch = require_json_object(patch_raw, "pending_action.payload.patch")
            encoded_flow_id = self._encode_flow_id(flow_id)
            flow_before = flow_config_from_flow_api_response(
                require_json_object(
                    await self._client.get("flows", f"/flows/api/v1/flows/{encoded_flow_id}"),
                    "flows.flow.apply.response",
                )
            )
            flow_before_payload = require_json_object(
                flow_before.model_dump(mode="json"),
                "flows.flow.patch.before",
            )
            flow_after = FlowConfig.model_validate({**flow_before_payload, **patch})
            _ = await self._client.put(
                "flows",
                f"/flows/api/v1/flows/{encoded_flow_id}",
                json=require_json_object(
                    flow_after.model_dump(mode="json"),
                    "flows.flow.patch.after",
                ),
            )
            return {"flow_id": flow_id, "patch": patch}

        return await self._action_engine.apply_action(
            company_id=company_id,
            user_id=user_id,
            context_id=context_id,
            pending_action_id=pending_action_id,
            idempotency_key=idempotency_key,
            apply_fn=_apply,
        )

    async def apply_pending_action_from_http(
        self,
        *,
        pending_action_id: str,
        context_id: str,
        idempotency_key: str | None,
    ) -> LaraPendingAction:
        pid = pending_action_id.strip()
        if not pid:
            raise ValueError("pending_action_id is required")
        state = _MinimalLaraToolState(context_id)
        company_id, _, _ = self._require_runtime_ids(state)
        peek = await self._action_engine.get_action(company_id=company_id, pending_action_id=pid)
        capability = peek.capability
        operation = peek.operation
        if capability == "crm.note" and operation == "create":
            return await self.apply_crm_create_note(
                pending_action_id=pid,
                state=state,
                idempotency_key=idempotency_key,
            )
        if capability == "flows.node" and operation == "patch":
            return await self.apply_node_patch(
                pending_action_id=pid,
                state=state,
                idempotency_key=idempotency_key,
            )
        if capability == "flows.flow" and operation == "patch":
            return await self.apply_flow_patch(
                pending_action_id=pid,
                state=state,
                idempotency_key=idempotency_key,
            )
        raise ValueError(f"Unsupported pending action capability={capability} operation={operation}")
