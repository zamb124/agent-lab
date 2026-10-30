"""Flows editor tools — thin wrappers over FlowsClient.

LLM `mode=propose|apply` is a workflow switch, not authorization: apply requires a prior
propose and a server-validated pending_action_id (LaraActionEngine). Phase 3 will move
approval to server-owned effects.
"""

from __future__ import annotations

import json
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.flows.src.services.flows_client import FlowsClient
from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from core.types import JsonValue


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
        description=(
            "propose — подготовить действие и ждать подтверждения; "
            "apply — применить по pending_action_id из prior propose. "
            "mode is not authorization: server validates pending_action_id."
        ),
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
        description=(
            "propose — подготовить действие и ждать подтверждения; "
            "apply — применить по pending_action_id из prior propose. "
            "mode is not authorization: server validates pending_action_id."
        ),
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
    state: ExecutionState,
    flows_client: FlowsClient,
) -> str:
    _ = state
    payload = await flows_client.get_node(flow_id, node_id, branch_id=branch_id)
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
    state: ExecutionState,
    flows_client: FlowsClient,
) -> str:
    _ = state
    payload = await flows_client.list_nodes(flow_id, branch_id=branch_id)
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
    state: ExecutionState,
    flows_client: FlowsClient,
) -> str:
    _ = state
    payload = await flows_client.read_context(
        flow_id, branch_id=branch_id, node_id=node_id
    )
    return json.dumps(payload, ensure_ascii=False)


@tool(
    name="flows_patch_node",
    description=(
        "Готовит patch ноды flow для применения во внешнем UI (mode=propose), "
        "или применяет ранее предложенный patch (mode=apply + pending_action_id). "
        "apply requires a prior propose; mode is not authorization — server validates "
        "pending_action_id. Returns node_before/node_after and ui_events; "
        "сам tool не сохраняет flow на propose."
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
    state: ExecutionState,
    flows_client: FlowsClient,
) -> str:
    client = flows_client
    if mode == "propose":
        if flow_id is None or node_id is None or patch_json is None:
            raise ValueError("flow_id, node_id and patch_json are required for mode=propose")
        payload = await client.propose_node_patch(
            flow_id=flow_id,
            node_id=node_id,
            patch_json=patch_json,
            state=state,
            branch_id=branch_id,
            idempotency_key=idempotency_key,
        )
        return json.dumps(payload, ensure_ascii=False)
    if not pending_action_id:
        raise ValueError("pending_action_id is required for mode=apply")
    payload = await client.apply_node_patch(
        pending_action_id=pending_action_id,
        state=state,
        idempotency_key=idempotency_key,
    )
    return json.dumps(payload, ensure_ascii=False)


@tool(
    name="flows_patch_flow",
    description=(
        "Готовит patch к самому flow (name/description/tags/variables) для применения "
        "во внешнем UI (mode=propose), или применяет ранее предложенный patch "
        "(mode=apply + pending_action_id). apply requires a prior propose; mode is not "
        "authorization — server validates pending_action_id. "
        "Returns flow_before/flow_after and ui_events; сам tool не сохраняет flow на propose."
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
    state: ExecutionState,
    flows_client: FlowsClient,
) -> str:
    client = flows_client
    if mode == "propose":
        if flow_id is None or patch_json is None:
            raise ValueError("flow_id and patch_json are required for mode=propose")
        payload = await client.propose_flow_patch(
            flow_id=flow_id,
            patch_json=patch_json,
            state=state,
            idempotency_key=idempotency_key,
        )
        return json.dumps(payload, ensure_ascii=False)
    if not pending_action_id:
        raise ValueError("pending_action_id is required for mode=apply")
    payload = await client.apply_flow_patch(
        pending_action_id=pending_action_id,
        state=state,
        idempotency_key=idempotency_key,
    )
    return json.dumps(payload, ensure_ascii=False)
