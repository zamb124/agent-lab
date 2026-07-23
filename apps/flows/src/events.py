"""Каталог UI/domain событий сервиса flows на шине `platform:events`."""

from __future__ import annotations

from pydantic import BaseModel

from apps.flows.src.models.evaluation_lab import EvaluationRunEvent
from apps.flows.src.models.hitl_conversation import ConversationTurnAppendedEvent
from core.events import register_platform_event

FLOWS_FLOW_UPDATED = "flows/flow/updated"
FLOWS_FLOW_DELETED = "flows/flow/deleted"
FLOWS_BRANCH_CREATED = "flows/branch/created"
FLOWS_BRANCH_UPDATED = "flows/branch/updated"
FLOWS_BRANCH_DELETED = "flows/branch/deleted"
FLOWS_HITL_TURN_APPENDED = "flows/hitl_conversation/turn_appended"
FLOWS_EVALUATION_EVENT = "flows/evaluation/event"


class FlowsFlowUpdatedEventPayload(BaseModel):
    flow_id: str
    version: str = ""


class FlowsFlowDeletedEventPayload(BaseModel):
    flow_id: str


class FlowsBranchEventPayload(BaseModel):
    flow_id: str
    branch_id: str


register_platform_event(
    FLOWS_FLOW_UPDATED,
    FlowsFlowUpdatedEventPayload,
    description="Конфиг flow обновлён (редактор / reload-from-bundle).",
)
register_platform_event(
    FLOWS_FLOW_DELETED,
    FlowsFlowDeletedEventPayload,
    description="Flow удалён.",
)
register_platform_event(
    FLOWS_BRANCH_CREATED,
    FlowsBranchEventPayload,
    description="Создана ветка flow.",
)
register_platform_event(
    FLOWS_BRANCH_UPDATED,
    FlowsBranchEventPayload,
    description="Обновлена ветка flow.",
)
register_platform_event(
    FLOWS_BRANCH_DELETED,
    FlowsBranchEventPayload,
    description="Удалена ветка flow.",
)
register_platform_event(
    FLOWS_HITL_TURN_APPENDED,
    ConversationTurnAppendedEvent,
    description="В HITL-диалог WorkItem добавлен turn.",
)
register_platform_event(
    FLOWS_EVALUATION_EVENT,
    EvaluationRunEvent,
    description="Запись события evaluation lab run.",
)

# Re-export для call-sites (единый модуль сервиса).
__all__ = [
    "FLOWS_BRANCH_CREATED",
    "FLOWS_BRANCH_DELETED",
    "FLOWS_BRANCH_UPDATED",
    "FLOWS_EVALUATION_EVENT",
    "FLOWS_FLOW_DELETED",
    "FLOWS_FLOW_UPDATED",
    "FLOWS_HITL_TURN_APPENDED",
    "FlowsBranchEventPayload",
    "FlowsFlowDeletedEventPayload",
    "FlowsFlowUpdatedEventPayload",
]
