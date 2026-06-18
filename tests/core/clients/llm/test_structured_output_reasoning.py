"""Structured output assembly from LLM stream artifacts."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from core.clients.llm.mock import MockLLM
from core.clients.llm.structured_output import resolve_structured_output_source_text

pytestmark = pytest.mark.unit


def test_resolve_structured_output_source_text_prefers_content() -> None:
    resolved = resolve_structured_output_source_text(
        content='{"a": 1}',
        last_status_text='{"b": 2}',
        reasoning_text='{"c": 3}',
    )
    assert resolved == '{"a": 1}'


def test_resolve_structured_output_source_text_falls_back_to_reasoning() -> None:
    resolved = resolve_structured_output_source_text(
        content="",
        last_status_text="",
        reasoning_text='{"page_title": "Title"}',
    )
    assert resolved == '{"page_title": "Title"}'


class _TitlePayload(BaseModel):
    page_title: str


@pytest.mark.asyncio
async def test_mock_llm_chat_parses_structured_output_from_reasoning_only() -> None:
    llm = MockLLM()
    llm.configure(
        response_queue=[
            {
                "type": "text",
                "content": "",
                "reasoning": '{"page_title": "From reasoning"}',
            }
        ]
    )
    payload = await llm.chat("extract", response_model=_TitlePayload)
    assert payload.page_title == "From reasoning"
