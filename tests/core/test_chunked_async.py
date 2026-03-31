"""Тесты chunk_sequence, run_chunked_map, map_reduce_tree без LLM."""

import pytest

from core.utils.chunked_async import chunk_sequence, map_reduce_tree, run_chunked_map


def test_chunk_sequence_empty():
    assert chunk_sequence([], 5) == []


def test_chunk_sequence_sizes():
    assert chunk_sequence([1, 2, 3, 4, 5], 5) == [[1, 2, 3, 4, 5]]
    assert chunk_sequence([1, 2, 3, 4, 5, 6], 5) == [[1, 2, 3, 4, 5], [6]]
    assert chunk_sequence([1, 2, 3], 2) == [[1, 2], [3]]


def test_chunk_sequence_invalid():
    with pytest.raises(ValueError):
        chunk_sequence([1], 0)


@pytest.mark.asyncio
async def test_run_chunked_map_sums_lengths():
    async def proc(chunk: list[int]) -> int:
        return sum(chunk)

    out = await run_chunked_map([1, 2, 3, 4, 5], 2, proc, max_concurrent=2)
    assert out == [3, 7, 5]


@pytest.mark.asyncio
async def test_map_reduce_tree_single_chunk():
    async def mb(items: list[int]) -> str:
        return ",".join(str(x) for x in items)

    async def merge(items: list[str]) -> str:
        return "|".join(items)

    r = await map_reduce_tree(
        [1, 2, 3],
        chunk_size=5,
        map_batch=mb,
        merge_batch=merge,
        max_concurrent=2,
    )
    assert r == "1,2,3"


@pytest.mark.asyncio
async def test_map_reduce_tree_multi_level():
    calls: list[tuple[str, int]] = []

    async def mb(items: list[int]) -> str:
        calls.append(("map", len(items)))
        return f"m({sum(items)})"

    async def merge(items: list[str]) -> str:
        calls.append(("merge", len(items)))
        return "+".join(items)

    r = await map_reduce_tree(
        list(range(12)),
        chunk_size=5,
        map_batch=mb,
        merge_batch=merge,
        max_concurrent=4,
    )
    assert "m(" in r
    assert calls[0][0] == "map"
    assert calls[0][1] == 5


@pytest.mark.asyncio
async def test_map_reduce_tree_empty_leaves_raises():
    async def mb(items: list[int]) -> str:
        return ""

    async def merge(items: list[str]) -> str:
        return ""

    with pytest.raises(ValueError, match="non-empty"):
        await map_reduce_tree(
            [],
            chunk_size=5,
            map_batch=mb,
            merge_batch=merge,
            max_concurrent=2,
        )
