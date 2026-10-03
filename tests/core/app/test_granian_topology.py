"""Локальный Granian берёт число workers из Settings."""

import pytest

from core.config.base import BaseSettings


def test_granian_topology_defaults() -> None:
    settings = BaseSettings()
    assert settings.server.granian_workers == 1
    assert settings.server.granian_runtime_threads == 2


def test_granian_topology_reads_nested_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVER__GRANIAN_WORKERS", "3")
    monkeypatch.setenv("SERVER__GRANIAN_RUNTIME_THREADS", "4")
    settings = BaseSettings()
    assert settings.server.granian_workers == 3
    assert settings.server.granian_runtime_threads == 4
