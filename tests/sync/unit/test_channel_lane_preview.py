"""Unit-тесты превью ленты (без БД)."""

from __future__ import annotations

import pytest

from apps.sync.channel_lane_preview import lane_preview_from_content_row
from apps.sync.models.messages import MessageContentType


def test_lane_preview_text_plain() -> None:
    assert lane_preview_from_content_row(MessageContentType.TEXT_PLAIN.value, {"body": "  hello  "}) == "hello"


def test_lane_preview_text_plain_truncate() -> None:
    long_text = "x" * 200
    out = lane_preview_from_content_row(MessageContentType.TEXT_PLAIN.value, {"body": long_text})
    assert len(out) == 120
    assert out.endswith("…")


def test_lane_preview_text_plain_empty_body() -> None:
    assert lane_preview_from_content_row(MessageContentType.TEXT_PLAIN.value, {"body": "   "}) == ""


def test_lane_preview_text_plain_body_not_str_raises() -> None:
    with pytest.raises(ValueError, match="body"):
        lane_preview_from_content_row(MessageContentType.TEXT_PLAIN.value, {"body": 1})


def test_lane_preview_known_types() -> None:
    assert lane_preview_from_content_row(MessageContentType.CODE_BLOCK.value, {}) == "[Код]"
    assert lane_preview_from_content_row(MessageContentType.MOCK_IMAGE.value, {}) == "[Изображение]"
    assert lane_preview_from_content_row(MessageContentType.GIT_REFERENCE.value, {}) == "[Git]"
    assert lane_preview_from_content_row(MessageContentType.CUSTOM_TOOL_RESPONSE.value, {}) == "[Инструмент]"


def test_lane_preview_unknown_type_raises() -> None:
    with pytest.raises(ValueError, match="Неизвестный тип"):
        lane_preview_from_content_row("unknown/type", {})
