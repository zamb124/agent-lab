"""Остановка прокси WebSocket: отмена соседних задач — штатный исход."""

import asyncio

import pytest

from core.clients.service_websocket import _stop_pending_websocket_tasks


@pytest.mark.asyncio
async def test_stop_pending_websocket_tasks_absorbs_cancel() -> None:
    async def hang() -> None:
        _ = await asyncio.Event().wait()

    task = asyncio.create_task(hang())
    await _stop_pending_websocket_tasks({task})
    assert task.cancelled()


@pytest.mark.asyncio
async def test_stop_pending_websocket_tasks_raises_task_error() -> None:
    async def boom() -> None:
        raise RuntimeError("pump down")

    task = asyncio.create_task(boom())
    _ = await asyncio.wait({task})
    with pytest.raises(RuntimeError, match="pump down"):
        await _stop_pending_websocket_tasks({task})
