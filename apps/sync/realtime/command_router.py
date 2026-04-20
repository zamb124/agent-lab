"""Регистрация WS command-handler'ов Sync в платформенном `core.websocket`.

Канон: каждая операция Sync — запись в `SYNC_OPERATIONS`. Один handler
(`op_*` из `apps.sync.realtime.operations`) обслуживает оба транспорта:

  - WS frame `{type, payload, request_id}` → `_make_ws_handler(op)` валидирует
    payload через Pydantic и зовёт `op.fn(...)`. `WsCommandError` →
    `*_failed`-фрейм.
  - REST route в `apps/sync/api/**` сам собирает Pydantic-payload и зовёт
    ту же `op.fn(...)`.

Никаких CommandEnvelope / dispatch_sync_command / handle_command.kiq
для обычных операций. TaskIQ путь оставлен ТОЛЬКО внутри
`op_messages_transcribe_*` для запуска долгих фоновых задач.
"""

from __future__ import annotations

from typing import Any

from apps.sync.container import get_sync_container
from apps.sync.realtime.operations import (
    Operation,
    dump_result,
    op_calls_accept,
    op_calls_admin_transfer,
    op_calls_decline,
    op_calls_get,
    op_calls_hangup,
    op_calls_invite,
    op_calls_join_accept,
    op_calls_join_info,
    op_calls_links_create,
    op_calls_links_list,
    op_calls_links_remove,
    op_calls_links_update,
    op_calls_recording_start,
    op_calls_recording_stop,
    op_calls_recordings_list,
    op_calls_signal,
    op_calls_token,
    op_calls_turn_credentials,
    op_channels_add_member,
    op_channels_create,
    op_channels_list,
    op_channels_list_members,
    op_channels_mark_read,
    op_channels_notification_settings_update,
    op_channels_typing,
    op_channels_update,
    op_company_members_list,
    op_company_shared_channels_list,
    op_files_upload_completed,
    op_git_resources_get,
    op_git_resources_upsert,
    op_messages_delete,
    op_messages_edit,
    op_messages_forward,
    op_messages_list,
    op_messages_mark_read,
    op_messages_pin,
    op_messages_react,
    op_messages_send,
    op_messages_transcribe_audio,
    op_messages_transcribe_call,
    op_messages_transcribe_video,
    op_platform_namespaces_list,
    op_spaces_create,
    op_spaces_list,
    op_spaces_update,
    op_threads_create,
    op_threads_item,
    op_threads_list,
    parse_payload,
    CallsAcceptPayload,
    CallsAdminTransferPayload,
    CallsDeclinePayload,
    CallsGetPayload,
    CallsHangupPayload,
    CallsInvitePayload,
    CallsJoinAcceptPayload,
    CallsJoinInfoPayload,
    CallsLinksCreatePayload,
    CallsLinksListPayload,
    CallsLinksRemovePayload,
    CallsLinksUpdatePayload,
    CallsRecordingStartPayload,
    CallsRecordingStopPayload,
    CallsRecordingsListPayload,
    CallsSignalPayload,
    CallsTokenPayload,
    CallsTurnCredentialsPayload,
    ChannelsAddMemberPayload,
    ChannelsCreatePayload,
    ChannelsListMembersPayload,
    ChannelsListPayload,
    ChannelsMarkReadPayload,
    ChannelsNotificationSettingsUpdatePayload,
    ChannelsTypingPayload,
    ChannelsUpdatePayload,
    CompanyMembersListPayload,
    CompanySharedChannelsListPayload,
    FilesUploadCompletedPayload,
    GitResourcesGetPayload,
    GitResourcesUpsertPayload,
    MessagesDeletePayload,
    MessagesEditPayload,
    MessagesForwardPayload,
    MessagesListPayload,
    MessagesMarkReadPayload,
    MessagesPinPayload,
    MessagesReactPayload,
    MessagesSendPayload,
    MessagesTranscribeAudioPayload,
    MessagesTranscribeCallPayload,
    MessagesTranscribeVideoPayload,
    PlatformNamespacesListPayload,
    SpacesCreatePayload,
    SpacesListPayload,
    SpacesUpdatePayload,
    ThreadsCreatePayload,
    ThreadsItemPayload,
    ThreadsListPayload,
)
from core.logging import get_logger
from core.models.identity_models import User
from core.websocket import register_ws_command_handler

logger = get_logger(__name__)


SYNC_OPERATIONS: dict[str, Operation] = {
    # spaces
    "sync/spaces/list_requested": Operation(
        canonical_type="sync/spaces/list_requested",
        payload_model=SpacesListPayload,
        fn=op_spaces_list,
    ),
    "sync/spaces/create_requested": Operation(
        canonical_type="sync/spaces/create_requested",
        payload_model=SpacesCreatePayload,
        fn=op_spaces_create,
    ),
    "sync/spaces/update_requested": Operation(
        canonical_type="sync/spaces/update_requested",
        payload_model=SpacesUpdatePayload,
        fn=op_spaces_update,
    ),
    # channels
    "sync/channels/list_requested": Operation(
        canonical_type="sync/channels/list_requested",
        payload_model=ChannelsListPayload,
        fn=op_channels_list,
    ),
    "sync/channels/create_requested": Operation(
        canonical_type="sync/channels/create_requested",
        payload_model=ChannelsCreatePayload,
        fn=op_channels_create,
    ),
    "sync/channels/update_requested": Operation(
        canonical_type="sync/channels/update_requested",
        payload_model=ChannelsUpdatePayload,
        fn=op_channels_update,
    ),
    "sync/channels/mark_read_requested": Operation(
        canonical_type="sync/channels/mark_read_requested",
        payload_model=ChannelsMarkReadPayload,
        fn=op_channels_mark_read,
    ),
    "sync/channels/typing_requested": Operation(
        canonical_type="sync/channels/typing_requested",
        payload_model=ChannelsTypingPayload,
        fn=op_channels_typing,
    ),
    "sync/channels/notification_settings_update_requested": Operation(
        canonical_type="sync/channels/notification_settings_update_requested",
        payload_model=ChannelsNotificationSettingsUpdatePayload,
        fn=op_channels_notification_settings_update,
    ),
    "sync/channels/add_member_requested": Operation(
        canonical_type="sync/channels/add_member_requested",
        payload_model=ChannelsAddMemberPayload,
        fn=op_channels_add_member,
    ),
    "sync/channels/list_members_requested": Operation(
        canonical_type="sync/channels/list_members_requested",
        payload_model=ChannelsListMembersPayload,
        fn=op_channels_list_members,
    ),
    # threads
    "sync/threads/list_requested": Operation(
        canonical_type="sync/threads/list_requested",
        payload_model=ThreadsListPayload,
        fn=op_threads_list,
    ),
    "sync/threads/item_requested": Operation(
        canonical_type="sync/threads/item_requested",
        payload_model=ThreadsItemPayload,
        fn=op_threads_item,
    ),
    "sync/threads/create_requested": Operation(
        canonical_type="sync/threads/create_requested",
        payload_model=ThreadsCreatePayload,
        fn=op_threads_create,
    ),
    # messages
    "sync/messages/list_requested": Operation(
        canonical_type="sync/messages/list_requested",
        payload_model=MessagesListPayload,
        fn=op_messages_list,
    ),
    "sync/messages/send_requested": Operation(
        canonical_type="sync/messages/send_requested",
        payload_model=MessagesSendPayload,
        fn=op_messages_send,
    ),
    "sync/messages/edit_requested": Operation(
        canonical_type="sync/messages/edit_requested",
        payload_model=MessagesEditPayload,
        fn=op_messages_edit,
    ),
    "sync/messages/delete_requested": Operation(
        canonical_type="sync/messages/delete_requested",
        payload_model=MessagesDeletePayload,
        fn=op_messages_delete,
    ),
    "sync/messages/forward_requested": Operation(
        canonical_type="sync/messages/forward_requested",
        payload_model=MessagesForwardPayload,
        fn=op_messages_forward,
    ),
    "sync/messages/react_requested": Operation(
        canonical_type="sync/messages/react_requested",
        payload_model=MessagesReactPayload,
        fn=op_messages_react,
    ),
    "sync/messages/pin_requested": Operation(
        canonical_type="sync/messages/pin_requested",
        payload_model=MessagesPinPayload,
        fn=op_messages_pin,
    ),
    "sync/messages/mark_read_requested": Operation(
        canonical_type="sync/messages/mark_read_requested",
        payload_model=MessagesMarkReadPayload,
        fn=op_messages_mark_read,
    ),
    "sync/messages/transcribe_audio_requested": Operation(
        canonical_type="sync/messages/transcribe_audio_requested",
        payload_model=MessagesTranscribeAudioPayload,
        fn=op_messages_transcribe_audio,
    ),
    "sync/messages/transcribe_video_requested": Operation(
        canonical_type="sync/messages/transcribe_video_requested",
        payload_model=MessagesTranscribeVideoPayload,
        fn=op_messages_transcribe_video,
    ),
    "sync/messages/transcribe_call_requested": Operation(
        canonical_type="sync/messages/transcribe_call_requested",
        payload_model=MessagesTranscribeCallPayload,
        fn=op_messages_transcribe_call,
    ),
    # git
    "sync/git_resources/upsert_requested": Operation(
        canonical_type="sync/git_resources/upsert_requested",
        payload_model=GitResourcesUpsertPayload,
        fn=op_git_resources_upsert,
    ),
    "sync/git_resources/get_requested": Operation(
        canonical_type="sync/git_resources/get_requested",
        payload_model=GitResourcesGetPayload,
        fn=op_git_resources_get,
    ),
    # calls (mutating)
    "sync/calls/invite_requested": Operation(
        canonical_type="sync/calls/invite_requested",
        payload_model=CallsInvitePayload,
        fn=op_calls_invite,
    ),
    "sync/calls/accept_requested": Operation(
        canonical_type="sync/calls/accept_requested",
        payload_model=CallsAcceptPayload,
        fn=op_calls_accept,
    ),
    "sync/calls/decline_requested": Operation(
        canonical_type="sync/calls/decline_requested",
        payload_model=CallsDeclinePayload,
        fn=op_calls_decline,
    ),
    "sync/calls/hangup_requested": Operation(
        canonical_type="sync/calls/hangup_requested",
        payload_model=CallsHangupPayload,
        fn=op_calls_hangup,
    ),
    "sync/calls/recording_start_requested": Operation(
        canonical_type="sync/calls/recording_start_requested",
        payload_model=CallsRecordingStartPayload,
        fn=op_calls_recording_start,
    ),
    "sync/calls/recording_stop_requested": Operation(
        canonical_type="sync/calls/recording_stop_requested",
        payload_model=CallsRecordingStopPayload,
        fn=op_calls_recording_stop,
    ),
    "sync/calls/admin_transfer_requested": Operation(
        canonical_type="sync/calls/admin_transfer_requested",
        payload_model=CallsAdminTransferPayload,
        fn=op_calls_admin_transfer,
    ),
    "sync/calls/signal_requested": Operation(
        canonical_type="sync/calls/signal_requested",
        payload_model=CallsSignalPayload,
        fn=op_calls_signal,
    ),
    # calls (read + links + join)
    "sync/calls/get_requested": Operation(
        canonical_type="sync/calls/get_requested",
        payload_model=CallsGetPayload,
        fn=op_calls_get,
    ),
    "sync/calls/recordings_list_requested": Operation(
        canonical_type="sync/calls/recordings_list_requested",
        payload_model=CallsRecordingsListPayload,
        fn=op_calls_recordings_list,
    ),
    "sync/calls/token_requested": Operation(
        canonical_type="sync/calls/token_requested",
        payload_model=CallsTokenPayload,
        fn=op_calls_token,
    ),
    "sync/calls/turn_credentials_requested": Operation(
        canonical_type="sync/calls/turn_credentials_requested",
        payload_model=CallsTurnCredentialsPayload,
        fn=op_calls_turn_credentials,
    ),
    "sync/calls/links_list_requested": Operation(
        canonical_type="sync/calls/links_list_requested",
        payload_model=CallsLinksListPayload,
        fn=op_calls_links_list,
    ),
    "sync/calls/links_create_requested": Operation(
        canonical_type="sync/calls/links_create_requested",
        payload_model=CallsLinksCreatePayload,
        fn=op_calls_links_create,
    ),
    "sync/calls/links_update_requested": Operation(
        canonical_type="sync/calls/links_update_requested",
        payload_model=CallsLinksUpdatePayload,
        fn=op_calls_links_update,
    ),
    "sync/calls/links_remove_requested": Operation(
        canonical_type="sync/calls/links_remove_requested",
        payload_model=CallsLinksRemovePayload,
        fn=op_calls_links_remove,
    ),
    "sync/calls/join_info_requested": Operation(
        canonical_type="sync/calls/join_info_requested",
        payload_model=CallsJoinInfoPayload,
        fn=op_calls_join_info,
    ),
    "sync/calls/join_accept_requested": Operation(
        canonical_type="sync/calls/join_accept_requested",
        payload_model=CallsJoinAcceptPayload,
        fn=op_calls_join_accept,
    ),
    # company
    "sync/company_members/list_requested": Operation(
        canonical_type="sync/company_members/list_requested",
        payload_model=CompanyMembersListPayload,
        fn=op_company_members_list,
    ),
    "sync/shared_channels/list_requested": Operation(
        canonical_type="sync/shared_channels/list_requested",
        payload_model=CompanySharedChannelsListPayload,
        fn=op_company_shared_channels_list,
    ),
    # platform namespaces
    "sync/platform_namespaces/list_requested": Operation(
        canonical_type="sync/platform_namespaces/list_requested",
        payload_model=PlatformNamespacesListPayload,
        fn=op_platform_namespaces_list,
    ),
    # files (метаданные после REST upload)
    "sync/files/upload_completed_requested": Operation(
        canonical_type="sync/files/upload_completed_requested",
        payload_model=FilesUploadCompletedPayload,
        fn=op_files_upload_completed,
    ),
}


def _make_ws_handler(op: Operation):
    """Тонкая обвязка WS-handler'а: validate payload → call op.fn → dump result.

    `WsCommandError` пробрасываем как есть — `core.websocket.command_router`
    превратит её в `*_failed`-фрейм. Любые другие исключения пускаем выше:
    middleware/log/observer обработают.
    """

    async def handler(payload: dict[str, Any], user: User) -> dict[str, Any] | None:
        validated = parse_payload(op.payload_model, payload)
        container = get_sync_container()
        result = await op.fn(validated, user=user, container=container)
        return dump_result(result)

    handler.__name__ = f"ws_handler_{op.canonical_type.replace('/', '_')}"
    return handler


def register_sync_ws_commands() -> None:
    """Зарегистрировать все sync command-handler'ы. Вызывать на on_startup."""
    for canonical_type, op in SYNC_OPERATIONS.items():
        if canonical_type != op.canonical_type:
            raise ValueError(
                f"SYNC_OPERATIONS key {canonical_type!r} != Operation.canonical_type "
                f"{op.canonical_type!r}"
            )
        register_ws_command_handler(canonical_type, _make_ws_handler(op))
    logger.info(
        "Sync WS command-handlers зарегистрированы (%d операций)", len(SYNC_OPERATIONS)
    )
