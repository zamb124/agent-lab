"""Регистрация WS command-handler'ов Sync в платформенном `core.websocket`.

Канон: каждая операция Sync — запись в `SYNC_OPERATIONS`. Один `op_*`
обслуживает оба транспорта через `core.websocket.Operation`.
"""

from __future__ import annotations

from apps.sync.container import SyncContainer, get_sync_container
from apps.sync.models.calls import (
    CallLinkCreate,
    CallsAcceptPayload,
    CallsDeclinePayload,
    CallsHangupPayload,
    CallsInvitePayload,
    CallsSignalPayload,
)
from apps.sync.models.channels import ChannelCreate
from apps.sync.realtime.operations import (
    CallsAdminTransferPayload,
    CallsGetPayload,
    CallsJoinAcceptPayload,
    CallsJoinInfoPayload,
    CallsLinksListPayload,
    CallsLinksRemovePayload,
    CallsLinksUpdatePayload,
    CallsRecordingsListPayload,
    CallsRecordingStartPayload,
    CallsRecordingStopPayload,
    CallsTokenPayload,
    CallsTurnCredentialsPayload,
    ChannelsAddMemberPayload,
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
    MessagesListThreadPayload,
    MessagesMarkReadPayload,
    MessagesPinPayload,
    MessagesReactPayload,
    MessagesSendPayload,
    MessagesTranscribeAudioPayload,
    MessagesTranscribeCallPayload,
    MessagesTranscribeVideoPayload,
    ThreadsCreatePayload,
    ThreadsItemPayload,
    ThreadsListPayload,
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
    op_messages_list_thread,
    op_messages_mark_read,
    op_messages_pin,
    op_messages_react,
    op_messages_send,
    op_messages_transcribe_audio,
    op_messages_transcribe_call,
    op_messages_transcribe_video,
    op_threads_create,
    op_threads_item,
    op_threads_list,
)
from core.logging import get_logger
from core.websocket import Operation, RegisteredOperation, register_service_operations

logger = get_logger(__name__)


SYNC_OPERATIONS: dict[str, RegisteredOperation[SyncContainer]] = {
    # каналы
    "sync/channels/list_requested": Operation(
        payload_model=ChannelsListPayload,
        fn=op_channels_list,
    ),
    "sync/channels/create_requested": Operation(
        payload_model=ChannelCreate,
        fn=op_channels_create,
    ),
    "sync/channels/update_requested": Operation(
        payload_model=ChannelsUpdatePayload,
        fn=op_channels_update,
    ),
    "sync/channels/mark_read_requested": Operation(
        payload_model=ChannelsMarkReadPayload,
        fn=op_channels_mark_read,
    ),
    "sync/channels/typing_requested": Operation(
        payload_model=ChannelsTypingPayload,
        fn=op_channels_typing,
    ),
    "sync/channels/notification_settings_update_requested": Operation(
        payload_model=ChannelsNotificationSettingsUpdatePayload,
        fn=op_channels_notification_settings_update,
    ),
    "sync/channels/add_member_requested": Operation(
        payload_model=ChannelsAddMemberPayload,
        fn=op_channels_add_member,
    ),
    "sync/channels/list_members_requested": Operation(
        payload_model=ChannelsListMembersPayload,
        fn=op_channels_list_members,
    ),
    # треды
    "sync/threads/list_requested": Operation(
        payload_model=ThreadsListPayload,
        fn=op_threads_list,
    ),
    "sync/threads/item_requested": Operation(
        payload_model=ThreadsItemPayload,
        fn=op_threads_item,
    ),
    "sync/threads/create_requested": Operation(
        payload_model=ThreadsCreatePayload,
        fn=op_threads_create,
    ),
    # сообщения
    "sync/messages/list_requested": Operation(
        payload_model=MessagesListPayload,
        fn=op_messages_list,
    ),
    "sync/messages/list_thread_requested": Operation(
        payload_model=MessagesListThreadPayload,
        fn=op_messages_list_thread,
    ),
    "sync/messages/send_requested": Operation(
        payload_model=MessagesSendPayload,
        fn=op_messages_send,
    ),
    "sync/messages/edit_requested": Operation(
        payload_model=MessagesEditPayload,
        fn=op_messages_edit,
    ),
    "sync/messages/delete_requested": Operation(
        payload_model=MessagesDeletePayload,
        fn=op_messages_delete,
    ),
    "sync/messages/forward_requested": Operation(
        payload_model=MessagesForwardPayload,
        fn=op_messages_forward,
    ),
    "sync/messages/react_requested": Operation(
        payload_model=MessagesReactPayload,
        fn=op_messages_react,
    ),
    "sync/messages/pin_requested": Operation(
        payload_model=MessagesPinPayload,
        fn=op_messages_pin,
    ),
    "sync/messages/mark_read_requested": Operation(
        payload_model=MessagesMarkReadPayload,
        fn=op_messages_mark_read,
    ),
    "sync/messages/transcribe_audio_requested": Operation(
        payload_model=MessagesTranscribeAudioPayload,
        fn=op_messages_transcribe_audio,
    ),
    "sync/messages/transcribe_video_requested": Operation(
        payload_model=MessagesTranscribeVideoPayload,
        fn=op_messages_transcribe_video,
    ),
    "sync/messages/transcribe_call_requested": Operation(
        payload_model=MessagesTranscribeCallPayload,
        fn=op_messages_transcribe_call,
    ),
    # git-ресурсы
    "sync/git_resources/upsert_requested": Operation(
        payload_model=GitResourcesUpsertPayload,
        fn=op_git_resources_upsert,
    ),
    "sync/git_resources/get_requested": Operation(
        payload_model=GitResourcesGetPayload,
        fn=op_git_resources_get,
    ),
    # звонки (изменяющие)
    "sync/calls/invite_requested": Operation(
        payload_model=CallsInvitePayload,
        fn=op_calls_invite,
    ),
    "sync/calls/accept_requested": Operation(
        payload_model=CallsAcceptPayload,
        fn=op_calls_accept,
    ),
    "sync/calls/decline_requested": Operation(
        payload_model=CallsDeclinePayload,
        fn=op_calls_decline,
    ),
    "sync/calls/hangup_requested": Operation(
        payload_model=CallsHangupPayload,
        fn=op_calls_hangup,
    ),
    "sync/calls/recording_start_requested": Operation(
        payload_model=CallsRecordingStartPayload,
        fn=op_calls_recording_start,
    ),
    "sync/calls/recording_stop_requested": Operation(
        payload_model=CallsRecordingStopPayload,
        fn=op_calls_recording_stop,
    ),
    "sync/calls/admin_transfer_requested": Operation(
        payload_model=CallsAdminTransferPayload,
        fn=op_calls_admin_transfer,
    ),
    "sync/calls/signal_requested": Operation(
        payload_model=CallsSignalPayload,
        fn=op_calls_signal,
    ),
    # звонки (чтение + ссылки + join)
    "sync/calls/get_requested": Operation(
        payload_model=CallsGetPayload,
        fn=op_calls_get,
    ),
    "sync/calls/recordings_list_requested": Operation(
        payload_model=CallsRecordingsListPayload,
        fn=op_calls_recordings_list,
    ),
    "sync/calls/token_requested": Operation(
        payload_model=CallsTokenPayload,
        fn=op_calls_token,
    ),
    "sync/calls/turn_credentials_requested": Operation(
        payload_model=CallsTurnCredentialsPayload,
        fn=op_calls_turn_credentials,
    ),
    "sync/calls/links_list_requested": Operation(
        payload_model=CallsLinksListPayload,
        fn=op_calls_links_list,
    ),
    "sync/calls/links_create_requested": Operation(
        payload_model=CallLinkCreate,
        fn=op_calls_links_create,
    ),
    "sync/calls/links_update_requested": Operation(
        payload_model=CallsLinksUpdatePayload,
        fn=op_calls_links_update,
    ),
    "sync/calls/links_remove_requested": Operation(
        payload_model=CallsLinksRemovePayload,
        fn=op_calls_links_remove,
    ),
    "sync/calls/join_info_requested": Operation(
        payload_model=CallsJoinInfoPayload,
        fn=op_calls_join_info,
    ),
    "sync/calls/join_accept_requested": Operation(
        payload_model=CallsJoinAcceptPayload,
        fn=op_calls_join_accept,
    ),
    # компания
    "sync/company_members/list_requested": Operation(
        payload_model=CompanyMembersListPayload,
        fn=op_company_members_list,
    ),
    "sync/shared_channels/list_requested": Operation(
        payload_model=CompanySharedChannelsListPayload,
        fn=op_company_shared_channels_list,
    ),
    # файлы (метаданные после REST upload)
    "sync/files/upload_completed_requested": Operation(
        payload_model=FilesUploadCompletedPayload,
        fn=op_files_upload_completed,
    ),
}



def register_sync_ws_commands() -> None:
    """Зарегистрировать все sync command-handler'ы. Вызывать на on_startup."""
    register_service_operations(SYNC_OPERATIONS, get_sync_container)
    logger.info(
        "Sync WS command-handlers зарегистрированы (%d операций)", len(SYNC_OPERATIONS)
    )
