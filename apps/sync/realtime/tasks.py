"""TaskIQ задачи realtime слоя Sync."""

from __future__ import annotations

import json

import redis.asyncio as redis

from apps.sync.config import get_sync_settings
from apps.sync.db.base import SyncDatabase
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from apps.sync.realtime.broker import broker
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.handlers import execute_command
from core.logging import get_logger

logger = get_logger(__name__)


@broker.task
async def handle_command(cmd: dict) -> dict:
    """Обработка realtime команды в sync-worker."""
    command = CommandEnvelope.model_validate(cmd)
    logger.info(
        "task handle_command started: id=%s type=%s actor=%s company=%s",
        command.id, command.type, command.actor_user_id, command.company_id,
    )

    settings = get_sync_settings()
    sync_db_url = settings.database.sync_url or settings.database.url
    db = SyncDatabase(sync_db_url)

    spaces = SpaceRepository(db)
    channels = ChannelRepository(db)
    threads = ThreadRepository(db)
    messages = MessageRepository(db)
    git_refs = GitResourceRefRepository(db)

    exec_res = await execute_command(
        command,
        spaces=spaces,
        channels=channels,
        threads=threads,
        messages=messages,
        git_refs=git_refs,
    )

    r = redis.from_url(settings.database.redis_url)
    try:
        for event in exec_res.events:
            await r.publish(
                "sync.realtime.events",
                json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
            )
    finally:
        await r.aclose()

    if exec_res.ok:
        result_payload = exec_res.result.model_dump(mode="json") if exec_res.result is not None else None
        logger.info("task handle_command ok: id=%s type=%s", command.id, command.type)
        return {"id": command.id, "ok": True, "result": result_payload, "error_code": None, "error_detail": None}

    logger.error("task handle_command failed: id=%s type=%s", command.id, command.type)
    return {
        "id": command.id,
        "ok": False,
        "result": None,
        "error_code": "command_failed",
        "error_detail": "Command failed.",
    }
