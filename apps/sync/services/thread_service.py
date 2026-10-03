"""Сценарии команд тредов Sync."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from apps.sync.events import event_thread_created
from apps.sync.models.common import UserBrief
from apps.sync.models.message import SyncMessage
from apps.sync.models.threads import SyncThread, ThreadCreate, ThreadRead, ThreadRow
from apps.sync.realtime.handlers import channel_recipient_user_ids
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from core.events import publish_events
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.websocket import WsCommandError


async def _user_brief(user_id: str, *, resolve_user: bool) -> UserBrief:
    display_name = user_id
    avatar_url = None
    if resolve_user:
        user = await User.get(user_id)
        if user is not None:
            display_name = user.name
            avatar_url = user.avatar_url
    return UserBrief(user_id=user_id, display_name=display_name, avatar_url=avatar_url)


class SyncThreadService:
    """Список, чтение и создание треда."""

    def __init__(self, channel_access: SyncChannelAccessService) -> None:
        self._channel_access: SyncChannelAccessService = channel_access

    async def list_threads(
        self,
        *,
        company_id: str,
        channel_id: str,
        limit: int,
        offset: int,
    ) -> OffsetPage[ThreadRow]:
        threads = await SyncThread.list_threads_in_channel(
            company_id,
            channel_id,
            limit=limit,
            offset=offset,
        )
        items = [ThreadRow.model_validate(thread.model_dump()) for thread in threads]
        return OffsetPage[ThreadRow](
            items=items, total=len(items), limit=limit, offset=offset
        )

    async def get_thread(self, thread_id: str) -> ThreadRow:
        thread = await SyncThread.get(thread_id)
        if thread is None:
            raise WsCommandError(
                "not_found",
                f"Thread {thread_id!r} not found.",
                error_code="not_found",
            )
        return ThreadRow.model_validate(thread.model_dump())

    async def create_thread(
        self,
        body: ThreadCreate,
        *,
        actor_user_id: str,
        company_id: str,
    ) -> ThreadRead:
        root = await SyncMessage.get(body.root_message_id)
        if root is None:
            raise ValueError("root_message_id not found.")
        thread_id = uuid4().hex
        entity = SyncThread(
            thread_id=thread_id,
            company_id=company_id,
            channel_id=root.channel_id,
            root_message_id=body.root_message_id,
            title=body.title,
            created_at=datetime.now(tz=UTC),
            created_by_user_id=actor_user_id,
        )
        _ = await SyncThread.create_thread(entity)
        created_by = await _user_brief(actor_user_id, resolve_user=True)
        thread = ThreadRead(
            thread_id=thread_id,
            channel_id=root.channel_id,
            root_message_id=body.root_message_id,
            title=body.title,
            created_at=entity.created_at,
            created_by=created_by,
        )
        recipients = await channel_recipient_user_ids(
            self._channel_access, thread.channel_id
        )
        await publish_events(
            [
                event_thread_created(
                    thread, company_id=company_id, recipient_user_ids=recipients
                ),
            ]
        )
        return thread
