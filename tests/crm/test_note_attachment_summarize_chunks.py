"""Юнит-тесты разбиения текста для суммаризации вложений."""

from __future__ import annotations

import pytest

from apps.crm.services.note_attachment_description import split_text_into_summarize_chunks


def test_split_empty_returns_empty_list() -> None:
    assert split_text_into_summarize_chunks("   ", 100) == []


def test_split_short_is_single_chunk() -> None:
    s = "один кусок"
    assert split_text_into_summarize_chunks(s, 100) == [s]


def test_split_invalid_max_raises() -> None:
    with pytest.raises(ValueError, match="положительным"):
        split_text_into_summarize_chunks("a", 0)


def test_split_prefers_paragraph_boundary() -> None:
    max_c = 50
    p1 = "a\n" * 20
    p2 = "b\n" * 20
    text = f"{p1}\n\n{p2}"
    chunks = split_text_into_summarize_chunks(text, max_c)
    assert len(chunks) >= 2
    assert all(len(c) <= max_c for c in chunks)
    joined = "\n\n".join(chunks)
    assert joined.replace("\n", "") == text.replace("\n", "")


def test_split_hard_slices_when_no_breaks() -> None:
    max_c = 30
    text = "x" * 100
    chunks = split_text_into_summarize_chunks(text, max_c)
    assert len(chunks) >= 3
    assert "".join(chunks) == text
