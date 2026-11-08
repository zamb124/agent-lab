"""Обёртки capability-gateway над TextTransformService."""

from __future__ import annotations

import pytest

from apps.capability_gateway.services.invoke_helpers import (
    invoke_text_format_markdown,
    invoke_text_summarize,
)
from core.text_transforms.service import TextTransformService
from tests.fixtures.billing import make_test_billing_service

_MOCK_LLM_TEXT = "Mock LLM ответ"


@pytest.mark.asyncio
async def test_invoke_text_summarize_returns_summary_object() -> None:
    payload = await invoke_text_summarize(
        TextTransformService(make_test_billing_service()),
        text="long text",
        instruction="shorten",
        provider="mock",
        model="mock-gpt-4",
        max_output_tokens=40,
    )

    assert payload == {"summary": _MOCK_LLM_TEXT}


@pytest.mark.asyncio
async def test_invoke_text_format_markdown_returns_markdown_object() -> None:
    payload = await invoke_text_format_markdown(TextTransformService(make_test_billing_service()), text="Title")

    assert payload == {"markdown": _MOCK_LLM_TEXT}
