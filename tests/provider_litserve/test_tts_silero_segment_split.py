"""Сегментация текста для Silero ``apply_tts`` (лимит длины входа)."""

from __future__ import annotations

import pytest

from apps.provider_litserve.tts.engines import _split_text_for_silero_apply

pytestmark = pytest.mark.timeout(15)


def test_split_empty_and_short() -> None:
    assert _split_text_for_silero_apply("", max_chars=10) == []
    assert _split_text_for_silero_apply("   ", max_chars=10) == []
    assert _split_text_for_silero_apply("abc", max_chars=10) == ["abc"]
    assert _split_text_for_silero_apply("абв", max_chars=3) == ["абв"]


def test_split_prefers_space_boundary() -> None:
    text = "one " + "x" * 50 + " two"
    parts = _split_text_for_silero_apply(text, max_chars=20)
    assert len(parts) == 4
    assert parts[0] == "one"
    assert "".join(parts) == "one" + "x" * 50 + " two"


def test_split_hard_breaks_long_token() -> None:
    token = "z" * 25
    parts = _split_text_for_silero_apply(token, max_chars=10)
    assert parts == ["z" * 10, "z" * 10, "z" * 5]


def test_split_max_chars_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_chars"):
        _split_text_for_silero_apply("a", max_chars=0)
