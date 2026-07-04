"""Push-уведомление desktop-агентам об обновлении каталога toolkits."""

from __future__ import annotations

import json

from core.clients.redis_client import RedisClient
from core.logging import get_logger

logger = get_logger(__name__)

TUNNEL_TOOLKITS_UPDATED_CHANNEL = "platform:agent_tunnel_toolkits_updated"


async def notify_agent_toolkits_updated(redis_client: RedisClient, company_id: str) -> None:
    payload = {"company_id": company_id}
    _ = await redis_client.publish(TUNNEL_TOOLKITS_UPDATED_CHANNEL, json.dumps(payload))
    logger.info("agent.toolkits_updated.broadcast", company_id=company_id)
