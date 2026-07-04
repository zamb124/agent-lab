"""Единые параметры SQLAlchemy connection pool для платформы."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TypedDict


@dataclass(frozen=True)
class SqlAlchemyPoolConfig:
    pool_size: int
    max_overflow: int
    pool_timeout: float


class SqlAlchemyAsyncEnginePoolKwargs(TypedDict, total=False):
    pool_size: int
    max_overflow: int
    pool_timeout: float


def _testing_mode() -> bool:
    return os.environ.get("TESTING") == "true"


def _pytest_parallel_worker() -> bool:
    return (
        os.environ.get("PYTEST_XDIST_WORKER") is not None
        or os.environ.get("PYTEST_CURRENT_TEST") is not None
    )


def resolve_sqlalchemy_pool_config() -> SqlAlchemyPoolConfig:
    """Пул для долгоживущих сервисов (granian, TaskIQ)."""
    if _testing_mode():
        return SqlAlchemyPoolConfig(pool_size=1, max_overflow=2, pool_timeout=60.0)
    return SqlAlchemyPoolConfig(pool_size=5, max_overflow=10, pool_timeout=30.0)


def sqlalchemy_async_engine_pool_kwargs() -> SqlAlchemyAsyncEnginePoolKwargs:
    """pytest-xdist: один idle connection на engine; TESTING-стек — компактный пул."""
    if _pytest_parallel_worker():
        return {"pool_size": 1, "max_overflow": 0, "pool_timeout": 30.0}
    pool_config = resolve_sqlalchemy_pool_config()
    return {
        "pool_size": pool_config.pool_size,
        "max_overflow": pool_config.max_overflow,
        "pool_timeout": pool_config.pool_timeout,
    }
