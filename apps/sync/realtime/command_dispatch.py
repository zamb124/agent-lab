"""Выполнение sync-команд с публикацией событий (общая реализация для API и TaskIQ)."""

from __future__ import annotations

from typing import Any

from apps.sync.config import get_sync_settings
from apps.sync.container import get_sync_container
from apps.sync.db.base import SyncDatabase
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
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

    settings = get_sync_settings()
    if not settings.database.sync_url:
        raise ValueError("database.sync_url не задан")
    sync_db_url = settings.database.sync_url
    db = SyncDatabase(sync_db_url)

    spaces = SpaceRepository(db)
    channels = ChannelRepository(db)
    threads = ThreadRepository(db)
    messages = MessageRepository(db)
    git_refs = GitResourceRefRepository(db)

    container = get_sync_container()
    user_repository = container.user_repository

    exec_res = await execute_command(
        command,
        spaces=spaces,
        channels=channels,
        threads=threads,
        messages=messages,
        git_refs=git_refs,
        user_repository=user_repository,
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
