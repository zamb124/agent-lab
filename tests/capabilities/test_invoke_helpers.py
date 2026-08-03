"""Tests for capability gateway text invoke helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.capability_gateway.services.invoke_helpers import (
    invoke_text_format_markdown,
    invoke_text_summarize,
)


@pytest.mark.asyncio
async def test_invoke_text_summarize_returns_summary_object() -> None:
    service = MagicMock()
    service.summarize = AsyncMock(return_value="short")
    payload = await invoke_text_summarize(
        service,
        text="long text",
        instruction="brief",
        max_output_tokens=64,
    )
    assert payload == {"summary": "short"}
    service.summarize.assert_awaited_once_with(
        "long text",
        instruction="brief",
        provider=None,
        model=None,
        max_output_tokens=64,
    )


@pytest.mark.asyncio
async def test_invoke_text_format_markdown_returns_markdown_object() -> None:
    service = MagicMock()
    service.format_markdown = AsyncMock(return_value="# Title")
    payload = await invoke_text_format_markdown(service, text="Title")
    assert payload == {"markdown": "# Title"}
    service.format_markdown.assert_awaited_once_with("Title")
