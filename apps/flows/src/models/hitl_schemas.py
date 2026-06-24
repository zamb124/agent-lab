"""
HITL-схемы flows: снимок прерывания и idempotency-команда хэндоффа.

HITL реализован поверх платформенного ядра задач WorkItem (см. `worktracker.mdc`):
снимок хранится в `WorkItemHook.binding`, а durable-команда обеспечивает
идемпотентность регистрации задачи оператора. Имена нейтральны (без `Operator`),
т.к. задача оператора — частный случай WorkItem.
"""

from __future__ import annotations

import uuid
from typing import ClassVar
from uuid import UUID

from pydantic import ConfigDict, Field

from core.models import StrictBaseModel
from core.state import ExecutionState
from core.state.interrupt import HandoffMode

HANDOFF_COMMAND_NAMESPACE = UUID("7f74c4a1-6b92-45a4-942a-7e4f983ddc58")


class HitlInterruptSnapshot(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    question: str = Field(..., min_length=1)
    task_title: str = Field(..., min_length=1)
    assignee_queue: str = Field(..., min_length=1)
    work_queue_id: str = Field(..., min_length=1)
    handoff_mode: HandoffMode = HandoffMode.SINGLE_REPLY
    handoff_command_id: str = Field(..., min_length=1)
    execution_branch_id: str = Field(..., min_length=1)
    node_schedule_sequence: int = Field(..., ge=1)
    node_id: str = Field(..., min_length=1)
    tool_call_id: str | None = Field(default=None, min_length=1)


class HitlHandoffCommand(StrictBaseModel):
    correlation_id: UUID
    idempotency_key: str = Field(..., min_length=1)
    execution_branch_id: str = Field(..., min_length=1)
    node_schedule_sequence: int = Field(..., ge=1)
    node_id: str = Field(..., min_length=1)
    tool_call_id: str | None = Field(default=None, min_length=1)


def build_hitl_handoff_command(
    *,
    state: ExecutionState,
    node_id: str,
    tool_call_id: str | None = None,
) -> HitlHandoffCommand:
    execution_branch_id = state.durable_execution_branch_id
    if execution_branch_id is None:
        raise RuntimeError("HITL handoff requires durable execution_branch_id")
    node_schedule_sequence = state.durable_node_schedule_sequence
    if node_schedule_sequence is None:
        raise RuntimeError("HITL handoff requires durable NodeScheduled.sequence")
    key_parts = [
        "hitl",
        f"session:{state.session_id}",
        f"branch:{execution_branch_id}",
        f"schedule:{node_schedule_sequence}",
        f"node:{node_id}",
    ]
    if tool_call_id is not None:
        key_parts.append(f"tool_call:{tool_call_id}")
    idempotency_key = ":".join(key_parts)
    return HitlHandoffCommand(
        correlation_id=uuid.uuid5(HANDOFF_COMMAND_NAMESPACE, idempotency_key),
        idempotency_key=idempotency_key,
        execution_branch_id=execution_branch_id,
        node_schedule_sequence=node_schedule_sequence,
        node_id=node_id,
        tool_call_id=tool_call_id,
    )


__all__ = [
    "HitlInterruptSnapshot",
    "HitlHandoffCommand",
    "build_hitl_handoff_command",
]
