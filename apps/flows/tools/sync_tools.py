"""Платформенные тулы Sync-чата для flow-сотрудника.

Сотрудник действует от собственного имени (Context.user = employee, SESSION JWT),
поэтому ServiceClient проходит обычный auth и ACL канала штатно — без спецпутей.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from apps.flows.src.tools.decorator import tool
from core.clients.service_client import ServiceClient
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState


class SyncSendMessageArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="ID канала sync для отправки.")
    text: str = Field(..., min_length=1, description="Текст сообщения (Markdown).")
    thread_id: str | None = Field(default=None, description="ID треда (опционально).")


class SyncListMessagesArgs(StrictBaseModel):
    channel_id: str = Field(..., min_length=1, description="ID канала sync.")
    limit: int = Field(default=20, ge=1, le=200, description="Сколько последних сообщений вернуть.")


@tool(
    name="sync_send_message",
    description="Отправляет сообщение в канал Sync от имени сотрудника-агента.",
    tags=["misc", "sync"],
    parameters_model=SyncSendMessageArgs,
)
async def sync_send_message(
    channel_id: str,
    text: str,
    thread_id: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    client = ServiceClient()
    payload: JsonObject = {
        "contents": [{"type": "text/plain", "order": 0, "data": {"body": text}}],
    }
    if thread_id:
        payload["thread_id"] = thread_id
    response = await client.post(
        "sync",
        f"/sync/api/v1/channels/{channel_id}/messages",
        json=payload,
    )
    result = require_json_object(response, "sync_send_message.response")
    message_id = result.get("message_id")
    return {"message_id": message_id, "channel_id": channel_id}


@tool(
    name="sync_list_messages",
    description="Возвращает последние сообщения канала Sync (лента) для сотрудника-агента.",
    tags=["misc", "sync"],
    parameters_model=SyncListMessagesArgs,
)
async def sync_list_messages(
    channel_id: str,
    limit: int = 20,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    client = ServiceClient()
    response = await client.get(
        "sync",
        f"/sync/api/v1/channels/{channel_id}/messages",
        params={"limit": str(limit)},
    )
    result = require_json_object(response, "sync_list_messages.response")
    raw_items = result.get("items")
    items: list[JsonValue] = raw_items if isinstance(raw_items, list) else []
    return {"channel_id": channel_id, "count": len(items), "items": items}
