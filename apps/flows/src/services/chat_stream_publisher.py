"""Маппинг A2A SSE-фреймов в push-события `flows/chat/*` для UI.

Источник правды по структуре кадров — `apps.flows.src.channels.a2a.A2AChannel.on_message_stream`,
который выдаёт `Message`/`Task`/`TaskStatusUpdateEvent`/`TaskArtifactUpdateEvent` (a2a-sdk).

UI получает эти push-события через единый WebSocket `/flows/api/ws/notifications`
(подписан на канал `platform:ui_events`) и применяет в reducer фабрики
`flows/chat`. REST-зеркало команды отправки — `POST /flows/api/v1/{flow_id}`
(JSON-RPC `message/stream`); REST остаётся работоспособным для SDK/CLI/embed.

Имена push-событий **не** конфликтуют с командой
`flows/chat/send_requested` — у них нет суффиксов
`_requested`/`_succeeded`/`_failed`.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from a2a.types import (
    Message,
    MessageSendParams,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)

from apps.flows.src.channels.a2a import A2AChannel
from core.logging import get_logger
from core.ui_events import publish_ui_event_to_user

logger = get_logger(__name__)


CHAT_EVENT_PREFIX = "flows/chat"

CHAT_EVENT_CONTENT_CHUNK = f"{CHAT_EVENT_PREFIX}/content_chunk"
CHAT_EVENT_REASONING_CHUNK = f"{CHAT_EVENT_PREFIX}/reasoning_chunk"
CHAT_EVENT_OPERATOR_REPLY = f"{CHAT_EVENT_PREFIX}/operator_reply"
CHAT_EVENT_OPERATOR_FILES = f"{CHAT_EVENT_PREFIX}/operator_files"
CHAT_EVENT_TOOL_CALLS = f"{CHAT_EVENT_PREFIX}/tool_calls"
CHAT_EVENT_TOOL_RESULT = f"{CHAT_EVENT_PREFIX}/tool_result"
CHAT_EVENT_COMPLETED = f"{CHAT_EVENT_PREFIX}/completed"
CHAT_EVENT_FAILED = f"{CHAT_EVENT_PREFIX}/failed"
CHAT_EVENT_BREAKPOINT = f"{CHAT_EVENT_PREFIX}/breakpoint"
CHAT_EVENT_INPUT_REQUIRED = f"{CHAT_EVENT_PREFIX}/input_required"
CHAT_EVENT_TASK_STARTED = f"{CHAT_EVENT_PREFIX}/task_started"


def _extract_text_parts(parts: Optional[list[Any]]) -> str:
    if not parts:
        return ""
    chunks: list[str] = []
    for part in parts:
        kind = getattr(part, "kind", None)
        text = getattr(part, "text", None)
        if (kind == "text" or text) and isinstance(text, str) and text:
            chunks.append(text)
    return "".join(chunks)


def _message_metadata(message: Optional[Message]) -> dict[str, Any]:
    if message is None:
        return {}
    metadata = getattr(message, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    return {}


def _artifact_state(event: TaskArtifactUpdateEvent) -> Optional[str]:
    artifact = getattr(event, "artifact", None)
    if artifact is None:
        return None
    state = getattr(artifact, "state", None)
    if isinstance(state, str):
        return state
    return None


def _resolve_task_id(event: Any, fallback_task_id: str) -> str:
    raw = getattr(event, "task_id", None) or getattr(event, "taskId", None)
    if isinstance(raw, str) and raw:
        return raw
    metadata = getattr(event, "metadata", None)
    if isinstance(metadata, dict):
        meta_task_id = metadata.get("task_id") or metadata.get("taskId")
        if isinstance(meta_task_id, str) and meta_task_id:
            return meta_task_id
    return fallback_task_id


async def _publish(
    user_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    correlation_id: Optional[str],
) -> None:
    await publish_ui_event_to_user(
        user_id=user_id,
        type=event_type,
        payload=payload,
        correlation_id=correlation_id,
    )


def _normalize_message(message: Optional[Message]) -> Optional[dict[str, Any]]:
    if message is None:
        return None
    return message.model_dump(by_alias=True, exclude_none=True)


async def _emit_artifact_update(
    user_id: str,
    event: TaskArtifactUpdateEvent,
    *,
    task_id: str,
    correlation_id: Optional[str],
) -> None:
    artifact = getattr(event, "artifact", None)
    name = getattr(artifact, "name", None) if artifact is not None else None
    text = _extract_text_parts(getattr(artifact, "parts", None) if artifact else None)
    base_payload: dict[str, Any] = {"task_id": task_id, "artifact_name": name}

    if name == "operator_files":
        data_part = next(
            (
                p
                for p in (getattr(artifact, "parts", None) or [])
                if isinstance(getattr(p, "data", None), dict)
                and (getattr(p, "data") or {}).get("file_ids")
            ),
            None,
        )
        if data_part is not None:
            await _publish(
                user_id,
                CHAT_EVENT_OPERATOR_FILES,
                {**base_payload, "file_ids": list(data_part.data.get("file_ids", []))},
                correlation_id=correlation_id,
            )
        return

    if not text:
        return

    if name == "reasoning":
        await _publish(
            user_id,
            CHAT_EVENT_REASONING_CHUNK,
            {**base_payload, "text": text},
            correlation_id=correlation_id,
        )
        return

    if name == "operator_reply":
        await _publish(
            user_id,
            CHAT_EVENT_OPERATOR_REPLY,
            {**base_payload, "text": text},
            correlation_id=correlation_id,
        )
        return

    await _publish(
        user_id,
        CHAT_EVENT_CONTENT_CHUNK,
        {**base_payload, "text": text},
        correlation_id=correlation_id,
    )


async def _emit_status_update(
    user_id: str,
    event: TaskStatusUpdateEvent,
    *,
    task_id: str,
    correlation_id: Optional[str],
) -> None:
    status = getattr(event, "status", None)
    if status is None:
        return
    state = getattr(status, "state", None)
    state_str = state.value if hasattr(state, "value") else str(state) if state is not None else ""
    message = getattr(status, "message", None)
    msg_meta = _message_metadata(message)
    final_flag = bool(getattr(event, "final", False))
    base_payload: dict[str, Any] = {
        "task_id": task_id,
        "state": state_str,
        "final": final_flag,
        "message": _normalize_message(message),
    }

    tool_calls = msg_meta.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        await _publish(
            user_id,
            CHAT_EVENT_TOOL_CALLS,
            {**base_payload, "tool_calls": tool_calls},
            correlation_id=correlation_id,
        )

    tool_result = msg_meta.get("tool_result")
    if isinstance(tool_result, dict):
        await _publish(
            user_id,
            CHAT_EVENT_TOOL_RESULT,
            {**base_payload, "tool_result": tool_result},
            correlation_id=correlation_id,
        )

    if state_str in ("completed", "finished"):
        await _publish(
            user_id,
            CHAT_EVENT_COMPLETED,
            {**base_payload, "content": _extract_text_parts(getattr(message, "parts", None))},
            correlation_id=correlation_id,
        )
        return

    if state_str in ("failed", "error"):
        await _publish(
            user_id,
            CHAT_EVENT_FAILED,
            {**base_payload, "error": _extract_text_parts(getattr(message, "parts", None))},
            correlation_id=correlation_id,
        )
        return

    if state_str in ("input-required", "input_required"):
        result_meta = getattr(event, "metadata", None) if isinstance(getattr(event, "metadata", None), dict) else {}
        breakpoint_data = (result_meta or {}).get("breakpoint") or msg_meta.get("breakpoint")
        if isinstance(breakpoint_data, dict):
            await _publish(
                user_id,
                CHAT_EVENT_BREAKPOINT,
                {**base_payload, "breakpoint": breakpoint_data},
                correlation_id=correlation_id,
            )
            return
        await _publish(
            user_id,
            CHAT_EVENT_INPUT_REQUIRED,
            {
                **base_payload,
                "result_metadata": result_meta or {},
                "message_metadata": msg_meta,
            },
            correlation_id=correlation_id,
        )


async def stream_to_user(
    *,
    user_id: str,
    channel: A2AChannel,
    params: MessageSendParams,
    channel_context: Optional[dict[str, Any]],
    correlation_id: Optional[str],
) -> None:
    """Прокачивает A2A-стрим и публикует push-события для UI.

    Используется WS-командой `flows/chat/send_requested`. Запускается фоновой
    таской — сама команда возвращается ack-ом сразу после старта стриминга.
    """
    fallback_task_id = ""
    try:
        async for event in channel.on_message_stream(params, context=channel_context):
            task_id = _resolve_task_id(event, fallback_task_id)
            if not fallback_task_id and task_id:
                fallback_task_id = task_id
                await _publish(
                    user_id,
                    CHAT_EVENT_TASK_STARTED,
                    {"task_id": task_id},
                    correlation_id=correlation_id,
                )

            if isinstance(event, TaskArtifactUpdateEvent):
                await _emit_artifact_update(
                    user_id, event, task_id=task_id, correlation_id=correlation_id
                )
            elif isinstance(event, TaskStatusUpdateEvent):
                await _emit_status_update(
                    user_id, event, task_id=task_id, correlation_id=correlation_id
                )
            elif isinstance(event, Task):
                if not fallback_task_id:
                    fallback_task_id = event.id or fallback_task_id
                    await _publish(
                        user_id,
                        CHAT_EVENT_TASK_STARTED,
                        {"task_id": fallback_task_id},
                        correlation_id=correlation_id,
                    )
            elif isinstance(event, Message):
                text = _extract_text_parts(getattr(event, "parts", None))
                if text:
                    await _publish(
                        user_id,
                        CHAT_EVENT_CONTENT_CHUNK,
                        {"task_id": fallback_task_id, "text": text, "artifact_name": None},
                        correlation_id=correlation_id,
                    )
    except asyncio.CancelledError:
        await _publish(
            user_id,
            CHAT_EVENT_FAILED,
            {
                "task_id": fallback_task_id,
                "state": "cancelled",
                "final": True,
                "error": "cancelled",
                "message": None,
            },
            correlation_id=correlation_id,
        )
        raise
    except Exception as exc:
        logger.exception("flows/chat stream failed for user=%s: %s", user_id, exc)
        await _publish(
            user_id,
            CHAT_EVENT_FAILED,
            {
                "task_id": fallback_task_id,
                "state": "failed",
                "final": True,
                "error": str(exc),
                "message": None,
            },
            correlation_id=correlation_id,
        )
