"""Каталог владельцев `_requested` и регистрация command-типов в шине."""

from __future__ import annotations

import pytest

from core.events.registry import is_registered_platform_event
from core.models.identity_models import User
from core.realtime.command_owners import is_command_event_type, owner_service_for_event_type
from core.types import JsonObject
from core.websocket.command_router import (
    derive_failed_type,
    derive_succeeded_type,
    has_ws_command_handler,
    register_ws_command_handler,
)


def test_owner_service_for_known_scopes() -> None:
    assert owner_service_for_event_type("sync/messages/send_requested") == "sync"
    assert owner_service_for_event_type("crm/entity/create_requested") == "crm"
    assert owner_service_for_event_type("wiki/pages/content_update_requested") == "wiki"
    assert owner_service_for_event_type("worktracker/work_items/create_requested") == "worktracker"
    assert owner_service_for_event_type("office/document/rename_requested") == "office"
    assert owner_service_for_event_type("flows/flow/create_requested") == "flows"
    assert owner_service_for_event_type("frontend/company/switch_requested") == "frontend"


def test_owner_service_unknown_scope_raises() -> None:
    with pytest.raises(ValueError, match="No command owner"):
        owner_service_for_event_type("notify/crm/system_received")


def test_is_command_event_type() -> None:
    assert is_command_event_type("sync/messages/send_requested") is True
    assert is_command_event_type("sync/message/created") is False


async def _noop_handler(payload: JsonObject, user: User) -> JsonObject | None:
    _ = payload, user
    return None


def test_register_ws_command_registers_catalog_types() -> None:
    command_type = "rag/document/reindex_requested"
    if not has_ws_command_handler(command_type):
        register_ws_command_handler(command_type, _noop_handler)
    assert is_registered_platform_event(command_type)
    assert is_registered_platform_event(derive_succeeded_type(command_type))
    assert is_registered_platform_event(derive_failed_type(command_type))
