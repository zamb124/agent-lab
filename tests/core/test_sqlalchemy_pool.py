"""Канон connection pool: TESTING-стек и pytest-xdist."""

from __future__ import annotations

import pytest

from core.db.sqlalchemy_pool import (
    SqlAlchemyPoolConfig,
    resolve_sqlalchemy_pool_config,
    sqlalchemy_async_engine_pool_kwargs,
)


def test_resolve_sqlalchemy_pool_config_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TESTING", raising=False)
    assert resolve_sqlalchemy_pool_config() == SqlAlchemyPoolConfig(
        pool_size=5,
        max_overflow=10,
        pool_timeout=30.0,
    )


def test_resolve_sqlalchemy_pool_config_testing_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TESTING", "true")
    assert resolve_sqlalchemy_pool_config() == SqlAlchemyPoolConfig(
        pool_size=1,
        max_overflow=2,
        pool_timeout=60.0,
    )


def test_sqlalchemy_async_engine_pool_kwargs_pytest_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    assert sqlalchemy_async_engine_pool_kwargs() == {
        "pool_size": 1,
        "max_overflow": 0,
        "pool_timeout": 30.0,
    }


def test_sqlalchemy_async_engine_pool_kwargs_testing_stack_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert sqlalchemy_async_engine_pool_kwargs() == {
        "pool_size": 1,
        "max_overflow": 2,
        "pool_timeout": 60.0,
    }
