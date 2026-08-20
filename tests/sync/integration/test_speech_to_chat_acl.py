"""ACL speech-to-chat: сегмент по call_id, без joined."""

from __future__ import annotations

import pytest

from apps.sync.container import SyncContainer
from apps.sync.models.calls import CallsInvitePayload
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageCreate,
)
from apps.sync.realtime.handlers import _ensure_actor_may_send_to_channel
from apps.sync.realtime.operations import op_calls_invite
from core.files.models import AudioAttachmentContent, AudioTranscriptionStatus
from core.models.identity_models import User
from tests.sync.integration._helpers import create_test_topic_channel


def _speech_audio_body(*, call_id: str | None) -> MessageCreate:
    return MessageCreate(
        thread_id=None,
        parent_message_id=None,
        contents=[
            MessageContentModel(
                type=MessageContentType.FILE_AUDIO,
                data=AudioAttachmentContent(
                    file_id="file_speech_acl",
                    original_name="seg.wav",
                    content_type="audio/wav",
                    file_size=64,
                    duration_ms=1000,
                    waveform=None,
                    transcription_status=AudioTranscriptionStatus.IDLE,
                    transcription_text=None,
                    transcription_error=None,
                    source_speech_to_chat=True,
                ),
                order=0,
            )
        ],
        mentioned_user_ids=None,
        call_id=call_id,
    )


@pytest.mark.asyncio
async def test_speech_to_chat_guest_without_joined_allowed(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    _ = op_context
    channel_id = await create_test_topic_channel(
        op_user, op_container, unique_id, name_suffix="s2cacl"
    )
    call = await op_calls_invite(
        CallsInvitePayload(channel_id=channel_id),
        user=op_user,
        container=op_container,
    )
    company_id = op_user.active_company_id
    if company_id is None or company_id == "":
        raise AssertionError("op_user.active_company_id обязателен")
    await _ensure_actor_may_send_to_channel(
        channel_id=channel_id,
        company_id=company_id,
        actor_user_id="guest:deadbeef:Гость",
        body=_speech_audio_body(call_id=call.call_id),
        authz=op_container.authz_service,
        calls=op_container.call_repository,
    )


@pytest.mark.asyncio
async def test_speech_to_chat_without_call_id_raises(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    _ = op_context
    channel_id = await create_test_topic_channel(
        op_user, op_container, unique_id, name_suffix="s2cnocall"
    )
    company_id = op_user.active_company_id
    if company_id is None or company_id == "":
        raise AssertionError("op_user.active_company_id обязателен")
    with pytest.raises(PermissionError, match="call_id"):
        await _ensure_actor_may_send_to_channel(
            channel_id=channel_id,
            company_id=company_id,
            actor_user_id="guest:deadbeef:Гость",
            body=_speech_audio_body(call_id=None),
            authz=op_container.authz_service,
            calls=op_container.call_repository,
        )
