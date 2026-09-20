"""Realtime E2E: живой Centrifugo :19000 + Granian bus :9025, без ASGI-патча."""

from __future__ import annotations

import pytest

from apps.realtime.container import get_realtime_container
from apps.realtime.db.repository import PlatformEventLogRepository


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    no_doubles = pytest.mark.no_test_doubles
    no_asgi = pytest.mark.no_service_client_patch
    timeout_20 = pytest.mark.timeout(20)
    for item in items:
        if not item.nodeid.startswith("tests/realtime/"):
            continue
        item.add_marker(no_doubles)
        item.add_marker(no_asgi)
        if item.get_closest_marker("timeout") is None:
            item.add_marker(timeout_20)


@pytest.fixture
def realtime_event_log(realtime_service: None) -> PlatformEventLogRepository:
    _ = realtime_service
    return get_realtime_container().event_log_repository
