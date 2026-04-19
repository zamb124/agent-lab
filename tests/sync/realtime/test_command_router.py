"""register_sync_ws_commands и register_sync_ws_read_handlers регистрируют все
sync-команды (мутации + read) в core registry.

Тест уровня unit, без БД и WS-сокета: вызываем регистраторы и проверяем,
что для каждого канонического WS-имени есть handler. Имена выводятся из
`SYNC_COMMAND_TYPE_MAP` (мутации), явный `call.signal` (быстрый путь) и
`_READ_HANDLERS` (list/get для resource-collection и messages).
"""

from __future__ import annotations

import pytest

from apps.sync.realtime.command_router import (
    SIGNAL_COMMAND_TYPE,
    SYNC_COMMAND_TYPE_MAP,
    register_sync_ws_commands,
)
from apps.sync.realtime.read_handlers import (
    _READ_HANDLERS,
    register_sync_ws_read_handlers,
)
from core.websocket import has_ws_command_handler, list_ws_command_types
from core.websocket.command_router import _reset_handlers_for_tests


@pytest.fixture(autouse=True)
def _reset_ws_handlers():
    _reset_handlers_for_tests()
    yield
    _reset_handlers_for_tests()


def test_register_sync_ws_commands_registers_all_canonical_names() -> None:
    register_sync_ws_commands()

    for canonical in SYNC_COMMAND_TYPE_MAP.keys():
        assert has_ws_command_handler(canonical), f"Нет handler для {canonical}"

    assert has_ws_command_handler(SIGNAL_COMMAND_TYPE), "call.signal не зарегистрирован"

    registered = set(list_ws_command_types())
    expected = set(SYNC_COMMAND_TYPE_MAP.keys()) | {SIGNAL_COMMAND_TYPE}
    assert expected.issubset(registered)


def test_register_sync_ws_commands_command_count_is_stable() -> None:
    register_sync_ws_commands()
    expected_count = len(SYNC_COMMAND_TYPE_MAP) + 1
    sync_handlers = [t for t in list_ws_command_types() if t.startswith("sync/")]
    assert len(sync_handlers) == expected_count


def test_canonical_names_have_required_suffix() -> None:
    """Все sync command-имена обязаны заканчиваться на _requested."""
    for canonical in SYNC_COMMAND_TYPE_MAP.keys():
        assert canonical.endswith("_requested"), f"{canonical} нарушает контракт"
    assert SIGNAL_COMMAND_TYPE.endswith("_requested")


def test_register_sync_ws_read_handlers_registers_all_read_commands() -> None:
    register_sync_ws_read_handlers()

    for canonical in _READ_HANDLERS.keys():
        assert has_ws_command_handler(canonical), f"Нет read-handler для {canonical}"
        assert canonical.endswith("_requested"), f"{canonical} нарушает контракт"


def test_full_registration_covers_resource_collection_list_and_get() -> None:
    """Каноничные list/get-команды для resource-collection (sync/spaces, sync/channels,
    sync/threads, sync/messages) обязательно зарегистрированы read-handler'ами."""
    register_sync_ws_commands()
    register_sync_ws_read_handlers()

    required = {
        "sync/spaces/list_requested",
        "sync/channels/list_requested",
        "sync/threads/list_requested",
        "sync/threads/item_requested",
        "sync/messages/list_requested",
    }
    for canonical in required:
        assert has_ws_command_handler(canonical), f"{canonical} обязателен для resource-collection"
