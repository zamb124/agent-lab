"""
Нарезка последовательностей на чанки и асинхронный map / map-reduce без зависимости от apps/.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, List, Sequence, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def chunk_sequence(items: Sequence[T], chunk_size: int) -> List[List[T]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    if not items:
        return []
    return [list(items[i : i + chunk_size]) for i in range(0, len(items), chunk_size)]


async def run_chunked_map(
    items: Sequence[T],
    chunk_size: int,
    process_chunk: Callable[[List[T]], Awaitable[R]],
    *,
    max_concurrent: int,
) -> List[R]:
    """
    Нарезает items на чанки размера chunk_size и для каждого чанка вызывает process_chunk.
    Параллельность ограничена семафором max_concurrent.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    if max_concurrent < 1:
        raise ValueError("max_concurrent must be >= 1")
    chunks = chunk_sequence(list(items), chunk_size)
    if not chunks:
        return []

    sem = asyncio.Semaphore(max_concurrent)

    async def run_one(chunk: List[T]) -> R:
        async with sem:
            return await process_chunk(chunk)

    return list(await asyncio.gather(*[run_one(c) for c in chunks]))


async def map_reduce_tree(
    leaves: List[T],
    *,
    chunk_size: int,
    map_batch: Callable[[List[T]], Awaitable[R]],
    merge_batch: Callable[[List[R]], Awaitable[R]],
    max_concurrent: int,
) -> R:
    """
    Дерево map-reduce: листья режутся на чанки не больше chunk_size, map_batch на каждый чанк;
    промежуточные уровни — merge_batch по чанкам, пока не останется один результат или финальный merge.

    Если len(leaves) <= chunk_size — один вызов map_batch(leaves).
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    if max_concurrent < 1:
        raise ValueError("max_concurrent must be >= 1")
    if not leaves:
        raise ValueError("leaves must be non-empty")

    if len(leaves) <= chunk_size:
        return await map_batch(leaves)

    current: List[R] = await run_chunked_map(
        leaves,
        chunk_size,
        map_batch,
        max_concurrent=max_concurrent,
    )

    while len(current) > chunk_size:
        current = await run_chunked_map(
            current,
            chunk_size,
            merge_batch,
            max_concurrent=max_concurrent,
        )

    if len(current) == 1:
        return current[0]
    return await merge_batch(current)
