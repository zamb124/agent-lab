"""Unit-тесты превью ленты (без БД)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.sync.channel_lane_preview import lane_preview_from_content
from apps.sync.models.messages import (
    CodeBlockContent,
    CustomToolResponseContent,
    GitReferenceContent,
    MessageContentModel,
    MessageContentType,
    MockImageContent,
    TextPlainContent,
)


def _content(content_type: MessageContentType, data: TextPlainContent) -> MessageContentModel:
    return MessageContentModel(type=content_type, data=data, order=0)


def test_lane_preview_text_plain() -> None:
    content = _content(MessageContentType.TEXT_PLAIN, TextPlainContent(body="  hello  "))
    assert lane_preview_from_content(content) == "hello"


def test_lane_preview_text_plain_truncate() -> None:
    long_text = "x" * 200
    out = lane_preview_from_content(
        _content(MessageContentType.TEXT_PLAIN, TextPlainContent(body=long_text))
    )
    assert len(out) == 120
    assert out.endswith("…")


def test_lane_preview_text_plain_empty_body() -> None:
    content = _content(MessageContentType.TEXT_PLAIN, TextPlainContent(body="   "))
    assert lane_preview_from_content(content) == ""


def test_lane_preview_text_plain_body_not_str_fails_at_model_boundary() -> None:
    with pytest.raises(ValidationError, match="body"):
        _ = MessageContentModel.model_validate(
            {"type": MessageContentType.TEXT_PLAIN.value, "data": {"body": 1}, "order": 0}
        )


def test_lane_preview_known_types() -> None:
    assert (
        lane_preview_from_content(
            MessageContentModel(
                type=MessageContentType.CODE_BLOCK,
                data=CodeBlockContent(language="python", source="print(1)"),
                order=0,
            )
        )
        == "[Код]"
    )
    assert (
        lane_preview_from_content(
            MessageContentModel(
                type=MessageContentType.MOCK_IMAGE,
                data=MockImageContent(file_id="file-1"),
                order=0,
            )
        )
        == "[Изображение]"
    )
    assert (
        lane_preview_from_content(
            MessageContentModel(
                type=MessageContentType.GIT_REFERENCE,
                data=GitReferenceContent(git_ref_id="git-1"),
                order=0,
            )
        )
        == "[Git]"
    )
    assert (
        lane_preview_from_content(
            MessageContentModel(
                type=MessageContentType.CUSTOM_TOOL_RESPONSE,
                data=CustomToolResponseContent(tool_name="tool", response_data={}),
                order=0,
            )
        )
        == "[Инструмент]"
    )
