"""``submit_a2a_call`` — единственный способ асинхронного A2A-вызова.

Регистрирует ``PlatformA2APendingCall`` (PK — клиентский ``a2a_task_id``), шлёт
``SendMessage(returnImmediately=true)`` с ``taskPushNotificationConfig`` на
``/{service}/api/v1/internal/a2a/push`` и возвращает строку. Завершение приходит
webhook'ом → ``/internal/a2a/push`` consume'ит ряд и ставит continuation
TaskIQ-задачу. Ожидания и опроса нет — результат приходит webhook'ом.

Контракт continuation-задачи — kwargs ``a2a_task_id``, ``a2a_state``
(платформенный state или ``"deadline_exceeded"`` от sweeper'а),
``a2a_payload`` (StreamResponse ProtoJSON финального события) — плюс
``continuation_kwargs`` вызывающего. Continuation обязан быть идемпотентным
по ``a2a_task_id``: webhook и sweeper могут поставить его дважды.
"""

from __future__ import annotations

import contextvars
import secrets
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from core.a2a.pending_call import PlatformA2APendingCall
from core.a2a.push_callback import a2a_push_callback_url, mint_callback_token
from core.a2a.task_json import extract_text_from_parts_json, extract_text_from_task_json
from core.clients.a2a_client import A2AClient, A2AClientError
from core.internal_context_headers import build_internal_context_headers
from core.logging import get_logger
from core.tasks.registry import TaskSpec
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)

# Разброс дедлайна поверх базового бюджета — защита от стада одинаковых таймаутов.
_DEADLINE_JITTER_RATIO = 0.1

# Resume-контекст вызывающей TaskIQ-задачи: задача ставит через
# ``set_a2a_resume_context``, ``submit_a2a_call`` сшивает в continuation_kwargs.
# Generic continuation (``a2a_call_finished``) читает их и re-enqueue'ит
# ``resume_task`` с ``resume_kwargs`` после записи результата в pending-ряд.
_RESUME_TASK: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "a2a_resume_task", default=None
)
_RESUME_KWARGS: contextvars.ContextVar[JsonObject | None] = contextvars.ContextVar(
    "a2a_resume_kwargs", default=None
)
# Nonce прогона задачи (обычно её task_id): часть dedup_key — повторный запуск
# операции = новые submit'ы, re-run той же задачи = те же ключи.
_RESUME_NONCE: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "a2a_resume_nonce", default=None
)


class A2ACallPending(Exception):
    """A2A-вызов субмитнут; результат придёт push webhook'ом.

    Вызывающая граница (TaskIQ-задача или ``op_*``) ловит его и завершает
    ход: generic continuation ``a2a_call_finished`` кладёт результат в
    pending-ряд и re-enqueue'ит ``resume_task`` — повторный прогон забирает
    payload по ``dedup_key``. Ожидания/опроса нет никогда.
    """

    def __init__(self, a2a_task_id: str) -> None:
        self.a2a_task_id: str = a2a_task_id
        super().__init__(f"A2A call parked: {a2a_task_id}")


def a2a_resume_context_active() -> bool:
    """Контекст уже поставлен внешней командой (вложенные вызовы не перебивают)."""
    return _RESUME_TASK.get() is not None


def set_a2a_resume_context(
    resume_task: str,
    resume_kwargs: JsonObject,
    *,
    run_nonce: str | None = None,
) -> contextvars.Token[JsonObject | None]:
    """Пометить: вызовы ``submit_a2a_call`` в этой корутине резюмят данную задачу."""
    _ = _RESUME_TASK.set(resume_task)
    _ = _RESUME_NONCE.set(run_nonce)
    return _RESUME_KWARGS.set(dict(resume_kwargs))


def a2a_resume_nonce() -> str | None:
    """Nonce прогона для dedup_key вызывающего кода."""
    return _RESUME_NONCE.get()


def clear_a2a_resume_context(
    token: contextvars.Token[JsonObject | None],
) -> None:
    _ = _RESUME_TASK.set(None)
    _ = _RESUME_NONCE.set(None)
    _ = _RESUME_KWARGS.reset(token)


async def submit_a2a_call(
    *,
    a2a_client: A2AClient,
    service: str,
    company_id: str,
    user_id: str,
    base_url: str,
    content: str,
    continuation: TaskSpec,
    continuation_kwargs: JsonObject,
    deadline_seconds: float,
    context_id: str | None = None,
    branch_id: str = "default",
    a2a_task_id: str | None = None,
    parts: Sequence[JsonObject] | None = None,
    metadata: JsonObject | None = None,
    headers: dict[str, str] | None = None,
    parent_task_id: str | None = None,
    join_group: str | None = None,
    dedup_key: str | None = None,
) -> PlatformA2APendingCall:
    """Поставить A2A-вызов без ожидания: pending-ряд + SendMessage + push config.

    ``service`` — владелец callback endpoint'а (имя сервиса, на чей
    ``get_service_url`` строится URL). ``continuation`` — TaskSpec задачи
    завершения; в её kwargs добавляются ``a2a_task_id``/``a2a_state``/
    ``a2a_payload``/``a2a_base_url``.
    """
    if deadline_seconds <= 0:
        raise ValueError("deadline_seconds must be > 0")
    resolved_task_id = a2a_task_id or str(uuid.uuid4())
    token, token_hash = mint_callback_token()
    jitter = 1.0 + secrets.randbelow(100) / 100.0 * _DEADLINE_JITTER_RATIO
    deadline_at = datetime.now(timezone.utc) + timedelta(
        seconds=deadline_seconds * jitter
    )
    resolved_kwargs = dict(continuation_kwargs)
    resume_task = _RESUME_TASK.get()
    resume_kwargs = _RESUME_KWARGS.get()
    if resume_task is not None and resume_kwargs is not None:
        resolved_kwargs["resume_task"] = resume_task
        resolved_kwargs["resume_kwargs"] = dict(resume_kwargs)
    row = await PlatformA2APendingCall.register(
        a2a_task_id=resolved_task_id,
        service=service,
        company_id=company_id,
        user_id=user_id,
        base_url=base_url,
        continuation_task=continuation.name,
        continuation_kwargs=resolved_kwargs,
        callback_token_hash=token_hash,
        deadline_at=deadline_at,
        join_group=join_group,
        parent_task_id=parent_task_id,
        dedup_key=dedup_key,
    )
    submitted = await a2a_client.submit_task(
        base_url,
        content,
        session_id=context_id,
        branch_id=branch_id,
        task_id=resolved_task_id,
        parts=parts,
        metadata=metadata,
        headers=headers,
        push_config={
            "url": a2a_push_callback_url(service),
            "token": token,
        },
    )
    remote_task_id = submitted.task.get("id")
    if not isinstance(remote_task_id, str) or not remote_task_id.strip():
        raise A2AClientError("A2A submit returned Task without id")
    if remote_task_id != resolved_task_id:
        logger.info(
            "a2a.pending.relink",
            a2a_task_id=resolved_task_id,
            remote_task_id=remote_task_id,
        )
        row = await PlatformA2APendingCall.relink_task_id(
            resolved_task_id, remote_task_id
        )
    return row


def a2a_task_outcome(task_obj: JsonObject, a2a_state: str) -> JsonObject:
    """Нормализованный outcome терминальной A2A-задачи из полного Task JSON.

    Один формат для всех continuation-задач: ``{status, response, artifacts,
    task, error}``. ``task`` — исходный Task ProtoJSON (сохраняется целиком,
    вызывающий код достаёт структурированные артефакты из него).
    """
    artifacts_value = task_obj.get("artifacts")
    artifacts = (
        [
            require_json_object(item, "a2a.task.artifacts[]")
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
        error_text = a2a_state
        status_obj = task_obj.get("status")
        if isinstance(status_obj, dict):
            message_obj = status_obj.get("message")
            if isinstance(message_obj, dict):
                detail = extract_text_from_parts_json(message_obj.get("parts"))
                if detail:
                    error_text = detail
        return {
            "status": a2a_state,
            "response": "",
            "artifacts": artifacts,
            "task": task_obj,
            "error": error_text,
        }
    return {
        "status": a2a_state,
        "response": response_text,
        "artifacts": artifacts,
        "task": task_obj,
        "error": None,
    }


async def a2a_fetch_terminal_result(
    *,
    a2a_client: A2AClient,
    base_url: str,
    a2a_task_id: str,
    company_id: str,
    user_id: str,
    headers: dict[str, str] | None = None,
):
    """GetTask финального результата для continuation-задачи.

    Webhook несёт только statusUpdate; артефакты/история добираются каноничным
    ``GetTask`` под свежей подписью internal-контекста владельца вызова.
    """
    request_headers = dict(headers or {})
    request_headers.update(
        build_internal_context_headers(company_id=company_id, user_id=user_id)
    )
    return await a2a_client.get_task(
        base_url,
        a2a_task_id,
        headers=request_headers,
        timeout=30.0,
    )


__all__ = [
    "A2ACallPending",
    "a2a_fetch_terminal_result",
    "a2a_task_outcome",
    "a2a_resume_context_active",
    "a2a_resume_nonce",
    "clear_a2a_resume_context",
    "set_a2a_resume_context",
    "submit_a2a_call",
]
