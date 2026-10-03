"""Единый реестр операций Sync — один handler, два транспорта.

Контракт:
    async def op_<entity>_<verb>(
        payload: <Op>Payload,
        *,
        user: User,
        di: Di,
    ) -> <Op>Result | None

Для каждой операции:
  - REST-route в `apps/sync/api/**` валидирует входное тело через Pydantic
    (FastAPI), вызывает `op_*` напрямую и сериализует результат.
  - WS command-handler (`core.websocket.register_service_operations`)
    валидирует payload через тот же Pydantic-класс и вызывает ту же `op_*`.

Zero-fallback canon (см. `main.mdc`):
  - Никаких `or default` / `getattr(payload, k, default)` — поля валидирует
    Pydantic, отсутствие = `ValidationError` → `WsCommandError("ws_invalid_payload", ...)`.
  - Никаких `try/except Exception` вокруг repository-вызовов. IO-ошибки
    идут наверх как 500.
  - Бизнес-инварианты: явный `raise WsCommandError(code, detail)`.
    Не «вернуть пустой результат».
  - `require_company` бросает, если контекста нет, — никаких неявных
    дефолтов на `system` или `user.active_company_id`.

Mutating-операции исполняются in-process. TaskIQ — только для явно
помеченных heavy-операций (`messages.transcribe_audio/video/call`):
`op_*` зовёт `SyncMessageService`, постановка в очередь — в сервисе.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from apps.sync.di import Di
from apps.sync.models.calls import (
    CallLinkCreate,
    CallLinkInfo,
    CallLinkRead,
    CallRead,
    CallsAcceptPayload,
    CallScheduledLinkRead,
    CallsDeclinePayload,
    CallsHangupPayload,
    CallsInvitePayload,
    CallsJoinAcceptPayload,
    CallsJoinInfoPayload,
    CallsLinksListPayload,
    CallsLinksRemovePayload,
    CallsLinksUpdatePayload,
    CallsSignalPayload,
    JoinResponse,
)
from apps.sync.models.channels import (
    ChannelCreate,
    ChannelMemberRead,
    ChannelMemberRole,
    ChannelRead,
    ChannelUpdate,
)
from apps.sync.models.company_members import CompanyMemberRead
from apps.sync.models.git import (
    GitResourceRefCreate,
    GitResourceRefRead,
)
from apps.sync.models.meetings import CallRecordingRead
from apps.sync.models.messages import (
    MessageCreate,
    MessageEdit,
    MessageRead,
)
from apps.sync.models.threads import ThreadCreate, ThreadRead, ThreadRow
from core.calls.models import TurnCredentials
from core.files.file_ref import FileRef
from core.logging import get_logger
from core.models.identity_models import User
from core.pagination import CursorPage, ListResponse, OffsetPage
from core.request_scope import require_company

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Кодирование cursor (общий формат для cursor списка messages через WS и REST)
# ---------------------------------------------------------------------------








# ===========================================================================
# Каналы
# ===========================================================================


class ChannelsListPayload(BaseModel):
    namespace: str | None = Field(default=None)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ChannelsUpdatePayload(BaseModel):
    channel_id: str = Field(min_length=1)
    body: ChannelUpdate


class ChannelsMarkReadPayload(BaseModel):
    channel_id: str = Field(min_length=1)


class ChannelsTypingPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    typing: bool
    thread_id: str | None = Field(default=None)


class ChannelsNotificationSettingsUpdatePayload(BaseModel):
    channel_id: str = Field(min_length=1)
    notifications_muted: bool


class ChannelsAddMemberPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    role: ChannelMemberRole = "member"


class ChannelsListMembersPayload(BaseModel):
    channel_id: str = Field(min_length=1)


async def op_channels_list(
    payload: ChannelsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[ChannelRead]:
    company_id = require_company().company_id
    return await di.channel_service.list_channels(
        user_id=user.user_id,
        company_id=company_id,
        namespace=payload.namespace,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_channels_create(
    payload: ChannelCreate,
    *,
    user: User,
    di: Di,
) -> ChannelRead:
    company_id = require_company().company_id
    return await di.channel_service.create_channel(
        payload, actor_user_id=user.user_id, company_id=company_id
    )


async def op_channels_update(
    payload: ChannelsUpdatePayload,
    *,
    user: User,
    di: Di,
) -> ChannelRead:
    company_id = require_company().company_id
    return await di.channel_service.update_channel(
        payload.channel_id,
        payload.body,
        actor_user_id=user.user_id,
        company_id=company_id,
    )


async def op_channels_mark_read(
    payload: ChannelsMarkReadPayload,
    *,
    user: User,
    di: Di,
) -> None:
    company_id = require_company().company_id
    await di.channel_service.mark_read(
        channel_id=payload.channel_id, user_id=user.user_id, company_id=company_id
    )
    return None


async def op_channels_typing(
    payload: ChannelsTypingPayload,
    *,
    user: User,
    di: Di,
) -> None:
    company_id = require_company().company_id
    await di.channel_service.set_typing(
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        typing=payload.typing,
        user_id=user.user_id,
        company_id=company_id,
    )
    return None


async def op_channels_notification_settings_update(
    payload: ChannelsNotificationSettingsUpdatePayload,
    *,
    user: User,
    di: Di,
) -> ChannelRead:
    company_id = require_company().company_id
    return await di.channel_service.update_notification_settings(
        channel_id=payload.channel_id,
        notifications_muted=payload.notifications_muted,
        user_id=user.user_id,
        company_id=company_id,
    )


async def op_channels_add_member(
    payload: ChannelsAddMemberPayload,
    *,
    user: User,
    di: Di,
) -> ChannelMemberRead:
    company_id = require_company().company_id
    return await di.channel_service.add_member(
        channel_id=payload.channel_id,
        member_user_id=payload.user_id,
        role=payload.role,
        actor_user_id=user.user_id,
        company_id=company_id,
    )


async def op_channels_list_members(
    payload: ChannelsListMembersPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[ChannelMemberRead]:
    company_id = require_company().company_id
    return await di.channel_service.list_members(
        channel_id=payload.channel_id, user_id=user.user_id, company_id=company_id
    )


# ===========================================================================
# Треды
# ===========================================================================


class ThreadsListPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ThreadsItemPayload(BaseModel):
    thread_id: str = Field(min_length=1)


class ThreadsCreatePayload(BaseModel):
    body: ThreadCreate


async def op_threads_list(
    payload: ThreadsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[ThreadRow]:
    _ = user
    company_id = require_company().company_id
    return await di.thread_service.list_threads(
        company_id=company_id,
        channel_id=payload.channel_id,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_threads_item(
    payload: ThreadsItemPayload,
    *,
    user: User,
    di: Di,
) -> ThreadRow:
    _ = user
    _ = require_company()
    return await di.thread_service.get_thread(payload.thread_id)


async def op_threads_create(
    payload: ThreadsCreatePayload,
    *,
    user: User,
    di: Di,
) -> ThreadRead:
    company_id = require_company().company_id
    return await di.thread_service.create_thread(
        payload.body,
        actor_user_id=user.user_id,
        company_id=company_id,
    )


# ===========================================================================
# Сообщения
# ===========================================================================


class MessagesListPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    before: str | None = Field(default=None)
    after: str | None = Field(default=None)





class MessagesSendPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    body: MessageCreate


class MessagesEditPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    body: MessageEdit


class MessagesDeletePayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class MessagesForwardPayload(BaseModel):
    from_channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    to_channel_id: str = Field(min_length=1)
    thread_id: str | None = Field(default=None)


class MessagesReactPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    emoji: str | None = Field(default=None)


class MessagesPinPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    action: Literal["add", "remove"]


class MessagesMarkReadPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class MessagesTranscribeAudioPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class MessagesTranscribeVideoPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class MessagesTranscribeCallPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)


class MessagesTranscribeCallResult(BaseModel):
    status: Literal["queued"] = "queued"


async def op_messages_list(
    payload: MessagesListPayload,
    *,
    user: User,
    di: Di,
) -> CursorPage[MessageRead]:
    _ = user
    company_id = require_company().company_id
    return await di.message_service.list_messages(
        company_id=company_id,
        channel_id=payload.channel_id,
        limit=payload.limit,
        before=payload.before,
        after=payload.after,
    )



class MessagesListThreadPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


async def op_messages_list_thread(
    payload: MessagesListThreadPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[MessageRead]:
    company_id = require_company().company_id
    return await di.message_service.list_thread(
        company_id=company_id,
        user_id=user.user_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        limit=payload.limit,
        offset=payload.offset,
    )



async def op_messages_send(
    payload: MessagesSendPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    return await di.message_service.send(
        user=user,
        channel_id=payload.channel_id,
        body=payload.body,
    )



async def op_messages_mark_read(
    payload: MessagesMarkReadPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    company_id = require_company().company_id
    await di.message_service.mark_read(
        company_id=company_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
    )
    return None



async def op_messages_edit(
    payload: MessagesEditPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    company_id = require_company().company_id
    return await di.message_service.edit_message(
        company_id=company_id,
        user_id=user.user_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        contents=payload.body.contents,
    )



async def op_messages_delete(
    payload: MessagesDeletePayload,
    *,
    user: User,
    di: Di,
) -> MessagesDeletePayload:
    company_id = require_company().company_id
    await di.message_service.delete_message(
        company_id=company_id,
        user_id=user.user_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
    )
    return payload



async def op_messages_forward(
    payload: MessagesForwardPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    company_id = require_company().company_id
    return await di.message_service.forward_message(
        company_id=company_id,
        user_id=user.user_id,
        from_channel_id=payload.from_channel_id,
        message_id=payload.message_id,
        to_channel_id=payload.to_channel_id,
        thread_id=payload.thread_id,
    )






async def op_messages_react(
    payload: MessagesReactPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    company_id = require_company().company_id
    return await di.message_service.react(
        company_id=company_id,
        user_id=user.user_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        emoji=payload.emoji,
    )



async def op_messages_pin(
    payload: MessagesPinPayload,
    *,
    user: User,
    di: Di,
) -> ChannelRead:
    company_id = require_company().company_id
    return await di.message_service.pin(
        company_id=company_id,
        user_id=user.user_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        action=payload.action,
    )



async def op_messages_transcribe_audio(
    payload: MessagesTranscribeAudioPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    company_id = require_company().company_id
    return await di.message_service.transcribe_audio(
        company_id=company_id,
        user_id=user.user_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
    )



async def op_messages_transcribe_video(
    payload: MessagesTranscribeVideoPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    company_id = require_company().company_id
    return await di.message_service.transcribe_video(
        company_id=company_id,
        user_id=user.user_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
    )



async def op_messages_transcribe_call(
    payload: MessagesTranscribeCallPayload,
    *,
    user: User,
    di: Di,
) -> MessagesTranscribeCallResult:
    company_id = require_company().company_id
    await di.message_service.transcribe_call(
        company_id=company_id,
        user_id=user.user_id,
        channel_id=payload.channel_id,
        call_id=payload.call_id,
    )
    return MessagesTranscribeCallResult(status="queued")



# ===========================================================================
# Git-ресурсы
# ===========================================================================


class GitResourcesUpsertPayload(BaseModel):
    body: GitResourceRefCreate


class GitResourcesGetPayload(BaseModel):
    git_ref_id: str = Field(min_length=1)


async def op_git_resources_upsert(
    payload: GitResourcesUpsertPayload,
    *,
    user: User,
    di: Di,
) -> GitResourceRefRead:
    _ = user
    company_id = require_company().company_id
    return await di.git_service.upsert(payload.body, company_id=company_id)


async def op_git_resources_get(
    payload: GitResourcesGetPayload,
    *,
    user: User,
    di: Di,
) -> GitResourceRefRead:
    _ = user
    _ = require_company()
    return await di.git_service.get(payload.git_ref_id)


# ===========================================================================
# Звонки (изменяющие WS-команды)
# ===========================================================================


class CallsRecordingStartPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsRecordingStopPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsAdminTransferPayload(BaseModel):
    call_id: str = Field(min_length=1)
    target_user_id: str = Field(min_length=1)


async def op_calls_invite(
    payload: CallsInvitePayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    company_id = require_company().company_id
    return await di.call_service.invite(
        payload,
        user_id=user.user_id,
        company_id=company_id,
    )


async def op_calls_accept(
    payload: CallsAcceptPayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    company_id = require_company().company_id
    return await di.call_service.accept(
        payload,
        user_id=user.user_id,
        company_id=company_id,
    )


async def op_calls_decline(
    payload: CallsDeclinePayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    company_id = require_company().company_id
    return await di.call_service.decline(
        payload,
        user_id=user.user_id,
        company_id=company_id,
    )


async def op_calls_hangup(
    payload: CallsHangupPayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    company_id = require_company().company_id
    return await di.call_service.hangup(
        payload,
        user_id=user.user_id,
        company_id=company_id,
    )


async def op_calls_recording_start(
    payload: CallsRecordingStartPayload,
    *,
    user: User,
    di: Di,
) -> CallRecordingRead:
    company_id = require_company().company_id
    return await di.call_recording_service.start(
        call_id=payload.call_id,
        company_id=company_id,
        user_id=user.user_id,
    )


async def op_calls_recording_stop(
    payload: CallsRecordingStopPayload,
    *,
    user: User,
    di: Di,
) -> CallRecordingRead:
    company_id = require_company().company_id
    return await di.call_recording_service.stop(
        call_id=payload.call_id,
        company_id=company_id,
        user_id=user.user_id,
    )


async def op_calls_admin_transfer(
    payload: CallsAdminTransferPayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    company_id = require_company().company_id
    return await di.call_service.transfer_admin(
        call_id=payload.call_id,
        target_user_id=payload.target_user_id,
        user_id=user.user_id,
        company_id=company_id,
    )


async def op_calls_signal(
    payload: CallsSignalPayload,
    *,
    user: User,
    di: Di,
) -> None:
    company_id = require_company().company_id
    await di.call_service.signal(
        payload,
        user_id=user.user_id,
        company_id=company_id,
    )
    return None


# ===========================================================================
# Звонки (чтение + ссылки + join)
# ===========================================================================


class CallsGetPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsRecordingsListPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsTokenPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsTokenResult(BaseModel):
    token: str
    livekit_url: str


class CallsTurnCredentialsPayload(BaseModel):
    pass

























async def op_calls_get(
    payload: CallsGetPayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    _ = user
    company_id = require_company().company_id
    return await di.call_service.get_call(call_id=payload.call_id, company_id=company_id)


async def op_calls_recordings_list(
    payload: CallsRecordingsListPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[CallRecordingRead]:
    company_id = require_company().company_id
    return await di.call_service.list_recordings(
        call_id=payload.call_id,
        company_id=company_id,
        user_id=user.user_id,
    )


async def op_calls_token(
    payload: CallsTokenPayload,
    *,
    user: User,
    di: Di,
) -> CallsTokenResult:
    company_id = require_company().company_id
    token, livekit_url = await di.call_service.token(
        call_id=payload.call_id,
        company_id=company_id,
        user_id=user.user_id,
    )
    return CallsTokenResult(token=token, livekit_url=livekit_url)


async def op_calls_turn_credentials(
    payload: CallsTurnCredentialsPayload,
    *,
    user: User,
    di: Di,
) -> TurnCredentials:
    _ = payload
    return await di.call_service.turn_credentials(user_id=user.user_id)


async def op_calls_links_list(
    payload: CallsLinksListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[CallScheduledLinkRead]:
    company_id = require_company().company_id
    return await di.call_link_service.list_links(payload, user=user, company_id=company_id)



async def op_calls_links_create(
    body: CallLinkCreate,
    *,
    user: User,
    di: Di,
) -> CallLinkRead:
    company_id = require_company().company_id
    return await di.call_link_service.create_link(body, user=user, company_id=company_id)



async def op_calls_links_update(
    payload: CallsLinksUpdatePayload,
    *,
    user: User,
    di: Di,
) -> CallLinkRead:
    company_id = require_company().company_id
    return await di.call_link_service.update_link(payload, user=user, company_id=company_id)



async def op_calls_links_remove(
    payload: CallsLinksRemovePayload,
    *,
    user: User,
    di: Di,
) -> None:
    company_id = require_company().company_id
    await di.call_link_service.remove_link(payload, user=user, company_id=company_id)
    return None



async def op_calls_join_info(
    payload: CallsJoinInfoPayload,
    *,
    user: User,
    di: Di,
) -> CallLinkInfo:
    _ = user
    return await di.call_link_service.join_info(payload)



async def op_calls_join_accept(
    payload: CallsJoinAcceptPayload,
    *,
    user: User,
    di: Di,
) -> JoinResponse:
    return await di.call_link_service.join_accept(payload, user=user)



# ===========================================================================
# Участники компании + общие каналы
# ===========================================================================


class CompanyMembersListPayload(BaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class CompanySharedChannelsListPayload(BaseModel):
    peer_user_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


async def op_company_members_list(
    payload: CompanyMembersListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[CompanyMemberRead]:
    company_id = require_company().company_id
    return await di.channel_service.list_company_members(
        company_id=company_id,
        user_id=user.user_id,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_company_shared_channels_list(
    payload: CompanySharedChannelsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[ChannelRead]:
    company_id = require_company().company_id
    return await di.channel_service.list_shared_channels(
        company_id=company_id,
        user_id=user.user_id,
        peer_user_id=payload.peer_user_id,
        limit=payload.limit,
        offset=payload.offset,
    )


# ===========================================================================
# Файлы (метаданные после REST upload)
# ===========================================================================


class FilesUploadCompletedPayload(BaseModel):
    file_id: str = Field(min_length=1)


async def op_files_upload_completed(
    payload: FilesUploadCompletedPayload,
    *,
    user: User,
    di: Di,
) -> FileRef:
    """Подтверждение метаданных файла после chunked REST upload.

    Бинарный поток идёт через `POST /sync/api/v1/files/uploads*` (chunked),
    а через WS клиент шлёт этот фрейм с `file_id` и получает `FileRef`.
    """
    _ = user
    return await di.files_service.require_stored_file_ref(payload.file_id)
