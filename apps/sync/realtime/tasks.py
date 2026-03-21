"""TaskIQ задачи realtime слоя Sync."""

from __future__ import annotations

from typing import Any

from apps.sync.realtime.broker import broker
from apps.sync.realtime.command_dispatch import dispatch_sync_command
from apps.sync.realtime.commands import CommandEnvelope
from core.logging import get_logger

logger = get_logger(__name__)


@broker.task
async def handle_command(cmd: dict[str, Any]) -> dict[str, Any]:
    """Обработка realtime команды в sync-worker."""
    command = CommandEnvelope.model_validate(cmd)
    logger.info(
        "task handle_command started: id=%s type=%s actor=%s company=%s",
        command.id, command.type, command.actor_user_id, command.company_id,
    )
    return await dispatch_sync_command(command)
