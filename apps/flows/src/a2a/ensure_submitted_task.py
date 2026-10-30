"""Ensure durable A2A Task projection exists before stream event append."""

from __future__ import annotations

from a2a.types import Message, Part, Role, Task, TaskState, TaskStatus

from apps.flows.src.models.a2a_projection import A2ATaskProjection
from apps.flows.src.state import ExecutionState
from core.a2a import set_task_status_state


async def ensure_submitted_a2a_task(
    *,
    company_id: str,
    state: ExecutionState,
    input_message: Message | None = None,
    content: str | None = None,
) -> None:
    """Create SUBMITTED Task snapshot once for the current execution identity.

    Channel ingress and direct ``Flow.run`` / ``LlmNodeRunner`` paths both emit
    durable stream events. Append requires the Task row; prefer
    ``Emitter.create_ensured`` so ensure and emitter construction stay one contract.
    """
    owner_user_id = state.initiator_user_id or state.user_id
    if await A2ATaskProjection.any_task_id_matches_scope(
        company_id=company_id,
        task_id=state.task_id,
        session_id=state.session_id,
        flow_id=state.session_flow_id,
        context_id=state.context_id,
        owner_user_id=owner_user_id,
    ):
        return

    if input_message is None:
        text = content if content is not None else state.content
        resolved = Message(
            message_id=f"input:{state.task_id}",
            role=Role.ROLE_USER,
            parts=[Part(text=text)],
        )
    else:
        resolved = Message()
        resolved.CopyFrom(input_message)
        if resolved.message_id.strip() == "":
            resolved.message_id = f"input:{state.task_id}"
    resolved.task_id = state.task_id
    resolved.context_id = state.context_id

    history: list[Message] = []
    history_ids: set[str] = set()
    for message in state.messages:
        if message.message_id in history_ids:
            continue
        history.append(message)
        history_ids.add(message.message_id)
    if resolved.message_id not in history_ids:
        history.append(resolved)

    submitted_status = TaskStatus(
        message=Message(
            message_id=f"status:{state.task_id}:submitted",
            role=Role.ROLE_AGENT,
            parts=[Part(text="Task submitted")],
        )
    )
    set_task_status_state(submitted_status, TaskState.TASK_STATE_SUBMITTED)
    task = Task(
        id=state.task_id,
        context_id=state.context_id,
        status=submitted_status,
        history=history,
    )
    _ = await A2ATaskProjection.ensure_task(
        company_id=company_id,
        session_id=state.session_id,
        flow_id=state.session_flow_id,
        owner_user_id=owner_user_id,
        task=task,
        execution_branch_id=state.durable_execution_branch_id,
        flow_config_version=state.flow_config_version,
        input_message_id=resolved.message_id,
    )


__all__ = ["ensure_submitted_a2a_task"]
