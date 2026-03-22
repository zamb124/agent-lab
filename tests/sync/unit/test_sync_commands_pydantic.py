"""Валидация DTO команд Sync (без БД)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.sync.realtime.commands import (
    CommandEnvelope,
    SpacesCreatePayload,
    WsCommandFrame,
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


def test_ws_command_frame() -> None:
    f = WsCommandFrame.model_validate(
        {"id": "id1", "type": "spaces.create", "payload": {"body": {"name": "W", "description": None}}}
    )
    assert f.type == "spaces.create"
