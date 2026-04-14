"""
Единый фасад Lara для mutating/read операций из eval-инструментов.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import quote

from core.clients.service_client import ServiceClient
from core.context import get_context

from apps.flows.src.services.lara_action_engine import LaraActionEngine


class LaraFacade:
    """Безопасный фасад для тулов: preview/apply через LaraActionEngine."""

    def __init__(self, action_engine: LaraActionEngine):
        self._action_engine = action_engine
        self._client = ServiceClient()

    @staticmethod
    def _encode_flow_id(flow_id: str) -> str:
        return quote(flow_id, safe="")

    @staticmethod
    def _require_runtime_ids(state: Any) -> tuple[str, str, str]:
        ctx = get_context()
        if ctx is None:
            raise RuntimeError("Context is not set")
        if ctx.active_company is None:
            raise RuntimeError("Active company is required")
        if ctx.user is None:
            raise RuntimeError("User is required")
        if state is None:
            raise ValueError("state is required")
        context_id = getattr(state, "context_id", None)
        if not isinstance(context_id, str) or not context_id:
            raise ValueError("state.context_id is required")
        return ctx.active_company.company_id, ctx.user.user_id, context_id

    async def preview_crm_create_note(
        self,
        *,
        name: str,
        description: str,
        note_date: str | None,
        namespace: str,
        state: Any,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        company_id, user_id, context_id = self._require_runtime_ids(state)
        payload = {
            "name": name,
            "description": description,
            "namespace": namespace,
        }
        if note_date is not None:
            payload["note_date"] = note_date
        preview = {
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
        state: Any,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        company_id, user_id, context_id = self._require_runtime_ids(state)

        async def _apply(action: dict[str, Any]) -> dict[str, Any]:
            payload = action["payload"]
            body: dict[str, Any] = {
                "name": payload["name"],
                "entity_type": "note",
                "description": payload["description"],
                "namespace": payload["namespace"],
            }
            if "note_date" in payload:
                body["note_date"] = payload["note_date"]
            response = await self._client.post("crm", "/crm/api/v1/entities", json=body)
            return {
                "entity": response,
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
        patch: dict[str, Any],
        skill_id: str | None,
        state: Any,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        company_id, user_id, context_id = self._require_runtime_ids(state)
        encoded_flow_id = self._encode_flow_id(flow_id)
        flow_config = await self._client.get("flows", f"/flows/api/v1/flows/{encoded_flow_id}")
        if not isinstance(flow_config, dict):
            raise ValueError("Flow config is missing in response")
        resolved_skill_id = skill_id or "base"
        if resolved_skill_id == "base":
            graph_nodes = flow_config.get("nodes")
            if not isinstance(graph_nodes, dict) or node_id not in graph_nodes:
                raise ValueError(f"Node '{node_id}' not found in flow '{flow_id}'")
            node_before = graph_nodes[node_id]
        else:
            skills = flow_config.get("skills")
            if not isinstance(skills, dict) or resolved_skill_id not in skills:
                raise ValueError(f"Skill '{resolved_skill_id}' not found in flow '{flow_id}'")
            skill_config = skills[resolved_skill_id]
            if not isinstance(skill_config, dict):
                raise ValueError(f"Skill '{resolved_skill_id}' payload is invalid")
            graph_nodes = skill_config.get("nodes")
            if not isinstance(graph_nodes, dict) or node_id not in graph_nodes:
                raise ValueError(f"Node '{node_id}' not found in skill '{resolved_skill_id}'")
            node_before = graph_nodes[node_id]
        node_after = deepcopy(node_before)
        node_after.update(patch)
        action = await self._action_engine.preview_action(
            company_id=company_id,
            user_id=user_id,
            context_id=context_id,
            capability="flows.node",
            operation="patch",
            target={"flow_id": flow_id, "skill_id": resolved_skill_id, "node_id": node_id},
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
        state: Any,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        company_id, user_id, context_id = self._require_runtime_ids(state)

        async def _apply(action: dict[str, Any]) -> dict[str, Any]:
            target = action["target"]
            payload = action["payload"]
            flow_id = target["flow_id"]
            node_id = target["node_id"]
            skill_id = target.get("skill_id") or "base"
            encoded_flow_id = self._encode_flow_id(flow_id)
            flow_config = await self._client.get("flows", f"/flows/api/v1/flows/{encoded_flow_id}")
            if not isinstance(flow_config, dict):
                raise ValueError("Flow config is missing in response")
            if skill_id == "base":
                graph_nodes = flow_config.get("nodes")
                if not isinstance(graph_nodes, dict) or node_id not in graph_nodes:
                    raise ValueError(f"Node '{node_id}' not found in flow '{flow_id}'")
                graph_nodes[node_id].update(payload["patch"])
            else:
                skills = flow_config.get("skills")
                if not isinstance(skills, dict) or skill_id not in skills:
                    raise ValueError(f"Skill '{skill_id}' not found in flow '{flow_id}'")
                skill_config = skills[skill_id]
                if not isinstance(skill_config, dict):
                    raise ValueError(f"Skill '{skill_id}' payload is invalid")
                graph_nodes = skill_config.get("nodes")
                if not isinstance(graph_nodes, dict) or node_id not in graph_nodes:
                    raise ValueError(f"Node '{node_id}' not found in skill '{skill_id}'")
                graph_nodes[node_id].update(payload["patch"])
            await self._client.put(
                "flows",
                f"/flows/api/v1/flows/{encoded_flow_id}",
                json=flow_config,
            )
            return {"flow_id": flow_id, "node_id": node_id, "patch": payload["patch"]}

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
        patch: dict[str, Any],
        state: Any,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        company_id, user_id, context_id = self._require_runtime_ids(state)
        encoded_flow_id = self._encode_flow_id(flow_id)
        flow_before = await self._client.get("flows", f"/flows/api/v1/flows/{encoded_flow_id}")
        if not isinstance(flow_before, dict):
            raise ValueError("Flow payload is missing in response")
        flow_after = deepcopy(flow_before)
        flow_after.update(patch)
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
                "flow_before": flow_before,
                "flow_after": flow_after,
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
        state: Any,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        company_id, user_id, context_id = self._require_runtime_ids(state)

        async def _apply(action: dict[str, Any]) -> dict[str, Any]:
            flow_id = action["target"]["flow_id"]
            patch = action["payload"]["patch"]
            encoded_flow_id = self._encode_flow_id(flow_id)
            flow_before = await self._client.get("flows", f"/flows/api/v1/flows/{encoded_flow_id}")
            if not isinstance(flow_before, dict):
                raise ValueError("Flow payload is missing in response")
            flow_after = deepcopy(flow_before)
            flow_after.update(patch)
            await self._client.put(
                "flows",
                f"/flows/api/v1/flows/{encoded_flow_id}",
                json=flow_after,
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
