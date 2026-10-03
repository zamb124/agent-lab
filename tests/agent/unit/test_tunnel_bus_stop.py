"""Остановка Redis listener: отмена — штатный исход, прочая ошибка задачи всплывает."""

import asyncio

import pytest

from core.utils.background import finish_background_task


@pytest.mark.asyncio
async def test_finish_listener_task_on_cancel() -> None:
    async def hang() -> None:
        _ = await asyncio.Event().wait()

    task = asyncio.create_task(hang())
    await finish_background_task(task)
    assert task.cancelled()


@pytest.mark.asyncio
async def test_finish_listener_task_raises_task_error() -> None:
    async def boom() -> None:
        raise RuntimeError("bus down")

    task = asyncio.create_task(boom())
    _ = await asyncio.wait({task})
    with pytest.raises(RuntimeError, match="bus down"):
        await finish_background_task(task)
