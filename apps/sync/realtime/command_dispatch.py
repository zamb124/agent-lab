"""Выполнение sync-команд с публикацией событий (общая реализация для API и TaskIQ)."""

from __future__ import annotations

from typing import Any

from apps.sync.container import get_sync_container
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.handlers import execute_command
from apps.sync.realtime.publish_events import publish_realtime_events
from core.logging import get_logger

logger = get_logger(__name__)


async def dispatch_sync_command(command: CommandEnvelope) -> dict[str, Any]:
    logger.info(
        "dispatch_sync_command: id=%s type=%s actor=%s company=%s",
        command.id,
        command.type,
        command.actor_user_id,
        command.company_id,
    )

    container = get_sync_container()

    exec_res = await execute_command(
        command,
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

    if exec_res.ok:
        if exec_res.result is None:
            result_payload = None
        elif hasattr(exec_res.result, "model_dump"):
            result_payload = exec_res.result.model_dump(mode="json")
        else:
            result_payload = exec_res.result
        logger.info("dispatch_sync_command ok: id=%s type=%s", command.id, command.type)
        return {
            "id": command.id,
            "ok": True,
            "result": result_payload,
            "error_code": None,
            "error_detail": None,
        }

    logger.error("dispatch_sync_command failed: id=%s type=%s", command.id, command.type)
    return {
        "id": command.id,
        "ok": False,
        "result": None,
        "error_code": "command_failed",
        "error_detail": "Command failed.",
    }
