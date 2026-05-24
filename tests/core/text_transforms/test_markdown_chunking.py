"""Чанки для платформенного Markdown formatter."""

from __future__ import annotations

import pytest

from core.text_transforms.chunking import split_text_into_markdown_chunks


def test_split_single_chunk_under_limit() -> None:
    t = "hello\n\nworld"
    assert split_text_into_markdown_chunks(t, 1000) == [t]


def test_split_multiple_chunks_respects_paragraph_boundary() -> None:
    parts = ["a" * 100, "b" * 100]
    body = "\n\n".join(parts)
    chunks = split_text_into_markdown_chunks(body, 150)
    assert len(chunks) >= 2
    assert all(c.strip() for c in chunks)


def test_split_invalid_max_raises() -> None:
    with pytest.raises(ValueError):
        split_text_into_markdown_chunks("x", 0)
