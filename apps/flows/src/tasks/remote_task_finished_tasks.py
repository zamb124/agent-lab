"""Continuation для припаркованных remote A2A-вызовов (RemoteFlowNode, CodeAgentNode).

Webhook ``/internal/a2a/push`` consume'ит pending-ряд и ставит эту задачу.
Она добирает финальный результат через каноничный ``GetTask``, записывает
``record_activity_completed`` по ``activity_id`` припаркованной durable
activity и ставит ``process_flow_task(is_resume=True)`` — run loop реиграет
ноду с persisted result.

Идемпотентность: повторная доставка webhook или дубль sweeper'а находят
activity уже completed → ``record_activity_completed`` возвращает ``False``
→ resume не ставится второй раз.
"""

from __future__ import annotations

from apps.flows.di import Di
from apps.flows.src.tasks.task_names import (
    TASK_FLOWS_REMOTE_TASK_FINISHED,
    TASK_PROCESS_FLOW,
)
from core.a2a.submit import a2a_fetch_terminal_result
from core.a2a.task_json import extract_text_from_parts_json, extract_text_from_task_json
from core.a2a.task_states import A2A_OPEN_TASK_STATES
from core.clients.a2a_client import A2AClient, A2AClientError
from core.context import set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.tasks import enqueue, platform_task
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)


def _outcome_from_task_payload(task_obj: JsonObject, a2a_state: str) -> JsonObject:
    """Outcome из полного Task, доставленного push webhook'ом (без GetTask)."""
    artifacts_value = task_obj.get("artifacts")
    artifacts = (
        [
            require_json_object(item, "a2a.payload.task.artifacts[]")
            for item in artifacts_value
        ]
        if isinstance(artifacts_value, list)
        else []
    )
    try:
        response_text = extract_text_from_task_json(task_obj)
    except ValueError:
        response_text = ""
    if a2a_state != "completed":
        status_obj = task_obj.get("status")
        error_text = a2a_state
        if isinstance(status_obj, dict):
            message_obj = status_obj.get("message")
            if isinstance(message_obj, dict):
                detail = extract_text_from_parts_json(message_obj.get("parts"))
                if detail:
                    error_text = detail
        return {
            "response": "",
            "status": a2a_state,
            "artifacts": artifacts,
            "error": error_text,
        }
    return {
        "response": response_text,
        "status": a2a_state,
        "artifacts": artifacts,
        "error": None,
    }


async def _resolve_remote_outcome(
    *,
    a2a_client: A2AClient,
    a2a_task_id: str,
    a2a_state: str,
    a2a_payload: JsonObject,
    a2a_base_url: str,
    company_id: str,
    user_id: str,
) -> JsonObject:
    """Финальный outcome remote-задачи для записи в durable activity.

    Push, доставивший полный ``task``, отдаёт outcome напрямую; push с
    голым ``statusUpdate`` добирает артефакты каноничным ``GetTask``.
    ``GetTask`` бросает ``A2AClientError`` при ``status=failed`` — текст
    status.message изымается из сообщения исключения.
    """
    task_payload = a2a_payload.get("task")
    if isinstance(task_payload, dict):
        return _outcome_from_task_payload(
            require_json_object(task_payload, "a2a.payload.task"), a2a_state
        )
    try:
        result = await a2a_fetch_terminal_result(
            a2a_client=a2a_client,
            base_url=a2a_base_url,
            a2a_task_id=a2a_task_id,
            company_id=company_id,
            user_id=user_id,
        )
    except A2AClientError as exc:
        if a2a_state in ("failed", "canceled", "rejected", "auth-required"):
            return {
                "response": "",
                "status": a2a_state,
                "artifacts": [],
                "error": str(exc),
            }
        raise
    if result.status in A2A_OPEN_TASK_STATES:
        return {
            "response": "",
            "status": a2a_state,
            "artifacts": [],
            "error": (
                f"Remote task still {result.status} at continuation"
                f" (delivered state {a2a_state!r})"
            ),
        }
    return {
        "response": result.response,
        "status": result.status,
        "artifacts": result.artifacts,
        "error": None,
    }


@platform_task(TASK_FLOWS_REMOTE_TASK_FINISHED)
async def flows_remote_task_finished(
    a2a_task_id: str,
    a2a_state: str,
    a2a_payload: JsonObject,
    a2a_base_url: str,
    session_id: str,
    flow_id: str,
    branch_id: str,
    task_id: str,
    context_id: str,
    node_id: str,
    activity_id: str,
    user_id: str,
    context_data: JsonObject,
    *,
    di: Di,
) -> JsonObject:
    """Завершить припаркованный remote A2A-вызов и возобновить flow."""
    if context_data is None:
        raise ValueError("Context is required for remote task continuation")
    context = Context.from_dict(context_data)
    context.session_id = session_id
    _ = set_context(context)
    if context.active_company is None:
        raise ValueError("Remote task continuation requires active_company")
    company_id = context.active_company.company_id

    if a2a_state == "deadline_exceeded":
        outcome = {
            "response": "",
            "status": "failed",
            "artifacts": [],
            "error": f"Remote A2A task {a2a_task_id} exceeded its deadline",
        }
    else:
        outcome = await _resolve_remote_outcome(
            a2a_client=A2AClient(),
            a2a_task_id=a2a_task_id,
            a2a_state=a2a_state,
            a2a_base_url=a2a_base_url,
            company_id=company_id,
            user_id=user_id,
        )

    completed = await di.workflow_runtime.record_activity_completed(
        activity_id=activity_id,
        result_json={"result": outcome},
    )
    if not completed:
        logger.info(
            "flows.remote_task_finished.duplicate",
            a2a_task_id=a2a_task_id,
            activity_id=activity_id,
        )
        return {"resumed": False, "reason": "activity_already_completed"}

    _ = await enqueue(
        TASK_PROCESS_FLOW,
        flow_id=flow_id,
        session_id=session_id,
        user_id=user_id,
        content="",
        branch_id=branch_id,
        channel="a2a",
        task_id=task_id,
        context_id=context_id,
        metadata={},
        is_resume=True,
        files=[],
        context_data=context_data,
        trace_context=None,
        background_kind="a2a_remote_resume",
    )
    logger.info(
        "flows.remote_task_finished.resumed",
        a2a_task_id=a2a_task_id,
        activity_id=activity_id,
        session_id=session_id,
        node_id=node_id,
        status=outcome.get("status"),
    )
    return {
        "resumed": True,
        "a2a_task_id": a2a_task_id,
        "status": outcome.get("status"),
    }
