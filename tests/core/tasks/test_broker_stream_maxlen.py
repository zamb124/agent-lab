"""Tests for TaskIQ broker stream maxlen configuration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.config.models import TasksConfig
from core.tasks import broker as broker_module
from core.tasks import registry as registry_module
from core.tasks.registry import queue_broker, register_queue_broker


@pytest.mark.asyncio
async def test_create_broker_passes_maxlen_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    previous_broker = queue_broker("search")

    class _FakeBroker:
        def __init__(
            self,
            *,
            url: str,
            queue_name: str,
            maxlen: int | None = None,
            approximate: bool = True,
        ) -> None:
            captured["url"] = url
            captured["queue_name"] = queue_name
            captured["maxlen"] = maxlen
            captured["approximate"] = approximate

        def with_result_backend(self, _backend: object) -> "_FakeBroker":
            return self

        def with_middlewares(self, *_middlewares: object) -> "_FakeBroker":
            return self

    fake_settings = MagicMock()
    fake_settings.tasks = TasksConfig(
        broker_url="redis://localhost:6379/1",
        stream_maxlen_by_queue={"search": 50_000},
    )
    fake_settings.tasks.default_retry_count = 3
    fake_settings.server.name = "test_service"

    monkeypatch.setattr(broker_module, "RedisStreamBroker", _FakeBroker)
    monkeypatch.setattr(broker_module, "RedisAsyncResultBackend", lambda **_: MagicMock())
    monkeypatch.setattr(broker_module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(broker_module, "build_logging_middleware", lambda **_: MagicMock())
    monkeypatch.setattr(broker_module, "session_lock_middleware", MagicMock())

    try:
        created = broker_module.create_broker(queue_name="search", service_name="search_worker")

        assert isinstance(created, _FakeBroker)
        assert captured["queue_name"] == "search"
        assert captured["maxlen"] == 50_000
        assert captured["approximate"] is True
    finally:
        # create_broker регистрирует брокер глобально — не оставляем Fake в registry.
        if previous_broker is not None:
            register_queue_broker("search", previous_broker)
        else:
            _ = registry_module._QUEUE_BROKERS.pop("search", None)
