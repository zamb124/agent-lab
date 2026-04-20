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
    ChannelsTypingPayload,
    SpacesCreatePayload,
)


def test_spaces_create_payload_requires_body() -> None:
    """Без `body` payload не валидируется (zero-fallback canon)."""
    with pytest.raises(ValidationError):
        SpacesCreatePayload.model_validate({})


def test_spaces_create_payload_requires_namespace() -> None:
    """`namespace` обязателен — никаких back-compat slug-генераций."""
    with pytest.raises(ValidationError):
        SpacesCreatePayload.model_validate({"body": {"name": "S"}})


def test_spaces_create_payload_valid() -> None:
    p = SpacesCreatePayload.model_validate(
        {"body": {"name": "S", "description": None, "namespace": "s"}}
    )
    assert p.body.name == "S"
    assert p.body.namespace == "s"


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
