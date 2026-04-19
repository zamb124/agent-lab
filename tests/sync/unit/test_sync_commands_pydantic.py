"""Валидация DTO команд Sync (без БД).

Транспорт фрейма WS — единый платформенный command-router
(`core.websocket.command_router`), формат `{ request_id, type, payload }`
проверяется в `tests/sync/api/test_sync_websocket.py`. Здесь — только
внутренние Pydantic-модели CommandEnvelope + payload-классы.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.sync.realtime.commands import (
    CommandEnvelope,
    SpacesCreatePayload,
)


def test_command_envelope_valid() -> None:
    env = CommandEnvelope(
        id="a" * 32,
        actor_user_id="u1",
        company_id="c1",
        type="spaces.create",
        payload={"body": {"name": "N", "description": None}},
    )
    assert env.type == "spaces.create"


def test_command_envelope_invalid_type_raises() -> None:
    with pytest.raises(ValidationError):
        CommandEnvelope(
            id="x",
            actor_user_id="u1",
            company_id="c1",
            type="invalid.type",
            payload={},
        )


def test_spaces_create_payload() -> None:
    p = SpacesCreatePayload.model_validate({"body": {"name": "S", "description": None}})
    assert p.body.name == "S"


def test_command_envelope_channels_typing() -> None:
    env = CommandEnvelope(
        id="b" * 32,
        actor_user_id="u1",
        company_id="c1",
        type="channels.typing",
        payload={"channel_id": "ch1", "typing": False},
    )
    assert env.type == "channels.typing"


def test_command_envelope_call_recording_start() -> None:
    env = CommandEnvelope(
        id="c" * 32,
        actor_user_id="u1",
        company_id="c1",
        type="call.recording.start",
        payload={"call_id": "call1"},
    )
    assert env.type == "call.recording.start"
