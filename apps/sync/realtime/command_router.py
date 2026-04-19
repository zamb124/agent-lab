"""Регистрация WS command-handler'ов Sync в платформенном `core.websocket`.

Каждая команда Sync имеет каноничное имя `sync/<entity>/<verb>_requested`
и REST-зеркало с тем же payload в `apps/sync/api/**`. Бизнес-логика — одна
для обоих транспортов: `apps.sync.realtime.handlers.execute_command`.

Транспортный слой:
  - Frontend dispatch'ит `sync/<entity>/<verb>_requested` через
    `transport: 'ws'` фабрики (см. `architecture.mdc`).
  - Core WS-роутер ловит фрейм, вызывает зарегистрированный здесь handler.
  - Handler собирает `CommandEnvelope` и зовёт ту же `execute_command`,
    что и REST. Возвращает `result.model_dump(mode='json')` (станет
    payload-ом `*_succeeded`-фрейма).

Маппинг каноничных WS-имён в внутренние короткие типы CommandEnvelope.type
(`spaces.create`, `messages.send` и т.д.) — единственное место, где живёт
эта таблица. handlers.py продолжает использовать короткие имена.

При `WsCommandError` верх ловит её и формирует `*_failed` reply
(`error_code`, `error_detail`).
"""

from __future__ import annotations

from typing import Any

from apps.sync.container import get_sync_container
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.handlers import execute_command
from apps.sync.realtime.publish_events import publish_realtime_events
from core.context import get_context
from core.logging import get_logger
from core.models.identity_models import User
from core.websocket import WsCommandError, register_ws_command_handler

logger = get_logger(__name__)


# canonical WS event name -> internal CommandEnvelope.type (короткое имя из commands.py).
SYNC_COMMAND_TYPE_MAP: dict[str, str] = {
    "sync/spaces/create_requested": "spaces.create",
    "sync/spaces/update_requested": "spaces.update",
    "sync/channels/create_requested": "channels.create",
    "sync/channels/update_requested": "channels.update",
    "sync/channels/mark_read_requested": "channels.mark_read",
    "sync/channels/typing_requested": "channels.typing",
    "sync/threads/create_requested": "threads.create",
    "sync/messages/send_requested": "messages.send",
    "sync/messages/mark_read_requested": "messages.mark_read",
    "sync/messages/edit_requested": "messages.edit",
    "sync/messages/delete_requested": "messages.delete",
    "sync/messages/forward_requested": "messages.forward",
    "sync/messages/react_requested": "messages.react",
    "sync/messages/pin_requested": "messages.pin",
    "sync/messages/transcribe_audio_requested": "messages.transcribe_audio",
    "sync/messages/transcribe_video_requested": "messages.transcribe_video",
    "sync/messages/transcribe_call_requested": "messages.transcribe_call",
    "sync/git_resources/upsert_requested": "git.resources.upsert",
    "sync/calls/invite_requested": "call.invite",
    "sync/calls/accept_requested": "call.accept",
    "sync/calls/decline_requested": "call.decline",
    "sync/calls/hangup_requested": "call.hangup",
    "sync/calls/recording_start_requested": "call.recording.start",
    "sync/calls/recording_stop_requested": "call.recording.stop",
    "sync/calls/admin_transfer_requested": "call.admin.transfer",
}


# `sync/calls/signal_requested` обрабатывается отдельно: исторически быстрый
# WS-путь без TaskIQ (in-process publish_realtime_events). Подробности —
# в обработчике ниже.
SIGNAL_COMMAND_TYPE = "sync/calls/signal_requested"


async def _handle_generic(internal_type: str, payload: dict[str, Any], user: User) -> dict[str, Any] | None:
    context = get_context()
    company_id = (
        context.active_company.id
        if context and context.active_company
        else user.active_company_id
    )
    if not company_id:
        raise WsCommandError("ws_no_company", "Нет active_company_id для команды Sync.")

    cmd_id = payload.pop("_request_id", None) if isinstance(payload, dict) else None

    container = get_sync_container()
    envelope = CommandEnvelope(
        id=cmd_id or "ws",
        actor_user_id=user.user_id,
        company_id=company_id,
        type=internal_type,
        payload=payload if isinstance(payload, dict) else {},
    )
    exec_res = await execute_command(
        envelope,
        spaces=container.space_repository,
        channels=container.channel_repository,
        threads=container.thread_repository,
        messages=container.message_repository,
        git_refs=container.git_resource_ref_repository,
        calls=container.call_repository,
        call_recordings=container.call_recording_repository,
        user_repository=container.user_repository,
    )
    await publish_realtime_events(exec_res.events)

    if not exec_res.ok:
        raise WsCommandError("sync_command_failed", "Команда Sync не выполнена.")
    if exec_res.result is None:
        return None
    if hasattr(exec_res.result, "model_dump"):
        return exec_res.result.model_dump(mode="json")
    if isinstance(exec_res.result, dict):
        return exec_res.result
    raise WsCommandError(
        "sync_command_invalid_result",
        f"Sync command result must be Pydantic model | dict | None, got {type(exec_res.result).__name__}",
    )


def _make_handler(internal_type: str):
    async def handler(payload: dict[str, Any], user: User) -> dict[str, Any] | None:
        return await _handle_generic(internal_type, payload, user)
    return handler


async def _handle_call_signal(payload: dict[str, Any], user: User) -> dict[str, Any] | None:
    """Быстрый путь для `call.signal`: без TaskIQ, прямая публикация события."""
    from apps.sync.realtime.commands import CallSignalPayload
    from apps.sync.realtime.events import event_call_signal

    context = get_context()
    company_id = (
        context.active_company.id
        if context and context.active_company
        else user.active_company_id
    )
    if not company_id:
        raise WsCommandError("ws_no_company", "Нет active_company_id для call.signal.")
    signal_payload = CallSignalPayload.model_validate(payload)
    event = event_call_signal(
        signal_payload.call_id,
        signal_payload.signal_type,
        signal_payload.data,
        company_id=company_id,
        recipient_user_ids=[signal_payload.target_user_id],
    )
    event.payload["target_user_id"] = signal_payload.target_user_id
    event.payload["sender_user_id"] = user.user_id
    await publish_realtime_events([event])
    return None


def register_sync_ws_commands() -> None:
    """Зарегистрировать все sync command-handler'ы. Вызывать на on_startup."""
    for canonical_type, internal_type in SYNC_COMMAND_TYPE_MAP.items():
        register_ws_command_handler(canonical_type, _make_handler(internal_type))
    register_ws_command_handler(SIGNAL_COMMAND_TYPE, _handle_call_signal)
    logger.info("Sync WS command-handlers зарегистрированы (%d команд)", len(SYNC_COMMAND_TYPE_MAP) + 1)
