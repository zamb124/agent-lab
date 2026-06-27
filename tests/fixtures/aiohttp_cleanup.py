"""Закрытие незавершённых aiohttp ClientSession в pytest-процессе."""

from __future__ import annotations

import asyncio
import gc
import logging
from typing import cast

import aiohttp


async def close_all_open_aiohttp_sessions() -> int:
    """Закрывает все открытые ClientSession, найденные через gc."""
    closed_count = 0
    for obj in cast(list[object], gc.get_objects()):
        if isinstance(obj, aiohttp.ClientSession) and not obj.closed:
            await obj.close()
            closed_count += 1
    return closed_count


def close_all_open_aiohttp_sessions_sync() -> int:
    """Sync-обёртка для pytest_sessionfinish."""
    try:
        _ = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(close_all_open_aiohttp_sessions())

    raise RuntimeError(
        "close_all_open_aiohttp_sessions_sync: event loop уже запущен; "
        + "вызовите close_all_open_aiohttp_sessions() из async teardown"
    )


def shutdown_test_logging_handlers() -> None:
    """Сбрасывает handlers до GC, чтобы избежать emit в закрытый stdout."""
    logging.shutdown()
