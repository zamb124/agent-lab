"""DI scheduler: тот же SchedulerDi, что собирает lifespan приложения."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI

from apps.scheduler.di import SchedulerDi
from core.di import require_di


@pytest_asyncio.fixture
async def scheduler_app() -> AsyncIterator[FastAPI]:
    from apps.scheduler.main import app

    yield app


@pytest_asyncio.fixture
async def scheduler_di(
    scheduler_app: FastAPI,
    setup_database_before_tests: None,
) -> AsyncIterator[SchedulerDi]:
    _ = setup_database_before_tests
    async with scheduler_app.router.lifespan_context(scheduler_app):
        yield require_di(scheduler_app, SchedulerDi)
