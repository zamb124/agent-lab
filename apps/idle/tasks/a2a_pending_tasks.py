"""Sweeper `a2a_pending_calls`/`a2a_pending_joins` — добивка потерянных вызовов.

Просроченный pending-ряд: сначала каноничный ``GetTask`` — если remote уже в
терминале (webhook потерян при доставке), continuation уходит с реальным
``a2a_state``; иначе — ``deadline_exceeded`` и best-effort ``CancelTask`` на
работающем remote. Webhook, опоздавший после expire, consume не пройдёт —
дедлайн есть дедлайн.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.idle.tasks.task_names import (
    TASK_A2A_CALL_FINISHED,
    TASK_A2A_PENDING_SWEEP_TICK,
)
from core.a2a.pending_call import (
    A2A_STATE_DEADLINE_EXCEEDED,
    CONSUMED_RETENTION_SECONDS,
    PlatformA2APendingCall,
)
from core.a2a.pending_join import PlatformA2APendingJoin
from core.a2a.submit import a2a_fetch_terminal_result, a2a_task_outcome
from core.a2a.task_states import A2A_OPEN_TASK_STATES
from core.clients.a2a_client import A2AClient, A2AClientError
from core.logging import get_logger
from core.tasks import enqueue_dynamic, platform_task
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)

_OPEN_STATES = A2A_OPEN_TASK_STATES


async def _resolve_sweep_outcome(
    row: PlatformA2APendingCall, a2a_client: A2AClient
) -> tuple[str, JsonObject]:
    """(a2a_state, payload): реальный терминал если remote уже ответил, иначе deadline."""
    try:
        result = await a2a_fetch_terminal_result(
            a2a_client=a2a_client,
            base_url=row.base_url,
            a2a_task_id=row.a2a_task_id,
            company_id=row.company_id,
            user_id=row.user_id,
        )
    except A2AClientError as exc:
        logger.warning(
            "a2a.sweep.get_task_failed",
            a2a_task_id=row.a2a_task_id,
            error=str(exc),
        )
        return A2A_STATE_DEADLINE_EXCEEDED, {}
    if result.status in _OPEN_STATES:
        try:
            _ = await a2a_client.cancel_task(
                row.base_url,
                row.a2a_task_id,
                timeout=10.0,
            )
        except A2AClientError as exc:
            logger.warning(
                "a2a.sweep.cancel_failed",
                a2a_task_id=row.a2a_task_id,
                error=str(exc),
            )
        return A2A_STATE_DEADLINE_EXCEEDED, {}
    return result.status, {"task": result.task}


async def _sweep_pending_calls(now: datetime, a2a_client: A2AClient) -> JsonObject:
    fired = skipped = failed = 0
    for row in await PlatformA2APendingCall.due_for_sweep(now):
        expired = await PlatformA2APendingCall.mark_expired(row.a2a_task_id)
        if expired is None:
            skipped += 1
            continue
        a2a_state, a2a_payload = await _resolve_sweep_outcome(expired, a2a_client)
        try:
            _ = await enqueue_dynamic(
                expired.continuation_task,
                {
                    "a2a_task_id": expired.a2a_task_id,
                    "a2a_state": a2a_state,
                    "a2a_payload": a2a_payload,
                    "a2a_base_url": expired.base_url,
                    **expired.continuation_kwargs,
                },
            )
        except Exception as exc:
            _ = await PlatformA2APendingCall.restore_pending(expired.a2a_task_id)
            logger.error(
                "a2a.sweep.enqueue_failed",
                a2a_task_id=expired.a2a_task_id,
                error=str(exc),
            )
            failed += 1
            continue
        fired += 1
    return {"fired": fired, "skipped": skipped, "failed": failed}


async def _sweep_pending_joins(now: datetime) -> JsonObject:
    fired = skipped = failed = 0
    for join in await PlatformA2APendingJoin.due_for_sweep(now):
        expired = await PlatformA2APendingJoin.mark_expired(join.join_group)
        if expired is None:
            skipped += 1
            continue
        try:
            _ = await enqueue_dynamic(
                expired.join_task,
                {
                    "join_group": expired.join_group,
                    "a2a_state": A2A_STATE_DEADLINE_EXCEEDED,
                    **expired.join_kwargs,
                },
            )
        except Exception as exc:
            _ = await PlatformA2APendingJoin.restore_pending(expired.join_group)
            logger.error(
                "a2a.sweep.join_enqueue_failed",
                join_group=expired.join_group,
                error=str(exc),
            )
            failed += 1
            continue
        fired += 1
    return {"fired": fired, "skipped": skipped, "failed": failed}


@platform_task(TASK_A2A_PENDING_SWEEP_TICK)
async def a2a_pending_sweep_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> JsonObject:
    _ = schedule_task_id, company_id
    now = datetime.now(timezone.utc)
    a2a_client = A2AClient()

    calls = await _sweep_pending_calls(now, a2a_client)
    joins = await _sweep_pending_joins(now)
    purged_calls = await PlatformA2APendingCall.purge_consumed_before(
        now - timedelta(seconds=CONSUMED_RETENTION_SECONDS)
    )
    purged_joins = await PlatformA2APendingJoin.purge_finished_before(
        now - timedelta(seconds=CONSUMED_RETENTION_SECONDS)
    )

    logger.info(
        "a2a.sweep.tick",
        calls_fired=calls["fired"],
        joins_fired=joins["fired"],
        purged_calls=purged_calls,
        purged_joins=purged_joins,
    )
    return {
        "calls": calls,
        "joins": joins,
        "purged_calls": purged_calls,
        "purged_joins": purged_joins,
    }


@platform_task(TASK_A2A_CALL_FINISHED)
async def a2a_call_finished(
    a2a_task_id: str,
    a2a_state: str,
    a2a_payload: JsonObject,
    a2a_base_url: str,
    resume_task: str | None = None,
    resume_kwargs: JsonObject | None = None,
) -> JsonObject:
    """Generic continuation для resume-паттерна ``submit_a2a_call`` + dedup_key.

    Записывает результат в pending-ряд (``store_result``) и re-enqueue'ит
    вызывающую задачу (``resume_task``/``resume_kwargs`` из resume-контекста
    субмиттера). Повторная доставка — идемпотентна: ``store_result`` уже
    applied → пропуск записи, resume ставится ещё раз (re-run отдаст тот же
    payload через ``take_result``).
    """
    row = await PlatformA2APendingCall.pending_by_id(a2a_task_id)
    if row is None:
        logger.error("a2a.call_finished.no_row", a2a_task_id=a2a_task_id)
        return {"stored": False, "resumed": False, "reason": "row_missing"}

    if a2a_state == A2A_STATE_DEADLINE_EXCEEDED:
        result_payload: JsonObject = {
            "status": "failed",
            "response": "",
            "artifacts": [],
            "error": f"A2A task {a2a_task_id} exceeded its deadline",
        }
    else:
        task_payload = a2a_payload.get("task")
        if isinstance(task_payload, dict):
            # Push доставил полный Task — GetTask не нужен.
            result_payload = a2a_task_outcome(
                require_json_object(task_payload, "a2a.payload.task"), a2a_state
            )
        else:
            try:
                result = await a2a_fetch_terminal_result(
                    a2a_client=A2AClient(),
                    base_url=a2a_base_url,
                    a2a_task_id=a2a_task_id,
                    company_id=row.company_id,
                    user_id=row.user_id,
                )
                if result.status in A2A_OPEN_TASK_STATES:
                    result_payload = {
                        "status": "failed",
                        "response": "",
                        "artifacts": [],
                        "error": f"remote still {result.status} at continuation",
                    }
                else:
                    result_payload = {
                        "status": result.status,
                        "response": result.response,
                        "artifacts": result.artifacts,
                        "task": result.task,
                        "error": None,
                    }
            except A2AClientError as exc:
                result_payload = {
                    "status": a2a_state,
                    "response": "",
                    "artifacts": [],
                    "error": str(exc),
                }

    return await _finish_call(row, a2a_task_id, result_payload, resume_task, resume_kwargs)


async def _finish_call(
    row: PlatformA2APendingCall,
    a2a_task_id: str,
    result_payload: JsonObject,
    resume_task: str | None,
    resume_kwargs: JsonObject | None,
) -> JsonObject:
    """store_result + re-enqueue вызывающей задачи (общий хвост continuation)."""
    stored = await PlatformA2APendingCall.store_result(
        a2a_task_id, result_payload
    )
    if stored is None and row.result_payload is None:
        logger.error(
            "a2a.call_finished.store_failed", a2a_task_id=a2a_task_id
        )
        return {"stored": False, "resumed": False}

    if resume_task is None or resume_kwargs is None:
        logger.warning(
            "a2a.call_finished.no_resume",
            a2a_task_id=a2a_task_id,
            service=row.service,
        )
        return {"stored": True, "resumed": False, "reason": "resume_missing"}

    _ = await enqueue_dynamic(resume_task, resume_kwargs)
    logger.info(
        "a2a.call_finished.resumed",
        a2a_task_id=a2a_task_id,
        resume_task=resume_task,
        status=result_payload.get("status"),
    )
    return {
        "stored": True,
        "resumed": True,
        "status": result_payload.get("status"),
    }
