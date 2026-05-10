"""Ответ POST ``/v1/text/format_markdown`` (проверка payload без импорта ``apps``)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FormatMarkdownUsage(BaseModel):
    """Счётчики токенов для биллинга (локальный инференс)."""

    prompt_tokens: int = Field(ge=0, default=0)
    completion_tokens: int = Field(ge=0, default=0)
    total_tokens: int = Field(ge=0, default=0)


class FormatMarkdownResponseBody(BaseModel):
    """Ответ POST ``/v1/text/format_markdown``."""

    markdown: str
    chunks_total: int = Field(ge=0)
    chunks_processed: int = Field(ge=0)
    model: str
    usage: FormatMarkdownUsage = Field(default_factory=FormatMarkdownUsage)


def validate_format_markdown_response(payload: dict[str, Any]) -> FormatMarkdownResponseBody:
    return FormatMarkdownResponseBody.model_validate(payload)
