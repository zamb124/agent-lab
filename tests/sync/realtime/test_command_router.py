"""`register_sync_ws_commands` регистрирует все sync-операции в core registry.

Тест уровня unit, без БД и WS-сокета: вызываем регистратор и проверяем,
что для каждого канонического WS-имени из `SYNC_OPERATIONS` есть handler.
"""

from __future__ import annotations

import pytest

from apps.sync.realtime.command_router import SYNC_OPERATIONS, register_sync_ws_commands
from core.websocket import has_ws_command_handler, list_ws_command_types
from core.websocket.command_router import _reset_handlers_for_tests


@pytest.fixture(autouse=True)
def _reset_ws_handlers():
    _reset_handlers_for_tests()
    yield
    _reset_handlers_for_tests()


def test_register_sync_ws_commands_registers_all_canonical_names() -> None:
    register_sync_ws_commands()

    for canonical in SYNC_OPERATIONS:
        assert has_ws_command_handler(canonical), f"Нет handler для {canonical}"

    registered = set(list_ws_command_types())
    expected = set(SYNC_OPERATIONS.keys())
    assert expected.issubset(registered)


def test_register_sync_ws_commands_command_count_is_stable() -> None:
    register_sync_ws_commands()
    sync_handlers = [t for t in list_ws_command_types() if t.startswith("sync/")]
    assert len(sync_handlers) == len(SYNC_OPERATIONS)


def test_each_operation_canonical_type_matches_key() -> None:
    """SYNC_OPERATIONS ключ должен совпадать с Operation.canonical_type."""
    for canonical, op in SYNC_OPERATIONS.items():
        assert canonical == op.canonical_type
        assert canonical.endswith("_requested")
