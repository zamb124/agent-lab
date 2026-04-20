"""Валидация payload-моделей операций Sync (без БД).

Транспорт фрейма WS — единый платформенный command-router
(`core.websocket.command_router`), формат `{ request_id, type, payload }`
проверяется в `tests/sync/api/test_sync_websocket.py`. Здесь — только
Pydantic payload-модели из `apps.sync.realtime.operations`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.sync.realtime.operations import (
    CallsRecordingStartPayload,
    ChannelsCreatePayload,
    ChannelsTypingPayload,
)


def test_channels_create_payload_requires_body() -> None:
    """Без `body` payload не валидируется (zero-fallback canon)."""
    with pytest.raises(ValidationError):
        ChannelsCreatePayload.model_validate({})


def test_channels_create_payload_topic_requires_namespace_at_runtime() -> None:
    """`namespace` для topic — обязательное поле канала (валидируется в `_create_channel`).

    Pydantic-уровень валидации `ChannelCreate` допускает опциональный
    `namespace` (для DM/calendar_meeting); проверка обязательности для
    topic — в бизнес-логике handler'а.
    """
    p = ChannelsCreatePayload.model_validate(
        {"body": {"type": "topic", "name": "t", "namespace": "default"}}
    )
    assert p.body.namespace == "default"


def test_channels_typing_payload_valid() -> None:
    p = ChannelsTypingPayload.model_validate(
        {"channel_id": "ch1", "typing": False}
    )
    assert p.channel_id == "ch1"
    assert p.typing is False
    assert p.thread_id is None


def test_channels_typing_payload_missing_channel_raises() -> None:
    with pytest.raises(ValidationError):
        ChannelsTypingPayload.model_validate({"typing": True})


def test_calls_recording_start_payload_valid() -> None:
    p = CallsRecordingStartPayload.model_validate({"call_id": "call1"})
    assert p.call_id == "call1"


def test_calls_recording_start_payload_missing_call_id_raises() -> None:
    with pytest.raises(ValidationError):
        CallsRecordingStartPayload.model_validate({})
