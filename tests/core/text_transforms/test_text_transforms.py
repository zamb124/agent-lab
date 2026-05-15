"""Тесты ``TextTransformService``, контракта Markdown и фасада namespace."""

from __future__ import annotations

import pytest

from apps.flows.src.eval.namespace import PythonNamespaceBuilder
from core.clients.llm.model_routing import split_provider_prefixed_model
from core.context import clear_context, set_context
from core.text_transforms import TextTransformService, validate_format_markdown_response
from core.text_transforms.routing import should_use_litserve_format_markdown_http


@pytest.mark.parametrize(
    ("provider", "model", "exp_p", "exp_m"),
    [
        (None, "openrouter:anthropic/claude-3-haiku", "openrouter", "anthropic/claude-3-haiku"),
        ("openai", "gpt-4o", "openai", "gpt-4o"),
        (None, "plain-model-no-prefix", None, "plain-model-no-prefix"),
    ],
)
def test_split_provider_prefixed_model_for_text_tools(
    provider: str | None,
    model: str | None,
    exp_p: str | None,
    exp_m: str | None,
) -> None:
    p, m = split_provider_prefixed_model(provider, model)
    assert p == exp_p
    assert m == exp_m


def test_should_use_litserve_http_default_and_explicit() -> None:
    assert should_use_litserve_format_markdown_http(None) is False
    assert should_use_litserve_format_markdown_http("provider_litserve") is True
    assert should_use_litserve_format_markdown_http("openrouter") is False


def test_validate_format_markdown_response_includes_usage() -> None:
    raw = {
        "markdown": "# Title\n\nBody",
        "chunks_total": 1,
        "chunks_processed": 1,
        "model": "test-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    body = validate_format_markdown_response(raw)
    assert body.markdown.startswith("# Title")
    assert body.usage.total_tokens == 15


@pytest.mark.asyncio
async def test_summarize_uses_mock_llm(mock_llm_with_queue, mock_context, container) -> None:
    _ = container
    mock_llm_with_queue(["Кратко: один два три."])
    set_context(mock_context)
    try:
        svc = TextTransformService()
        out = await svc.summarize("длинный текст про то как важно тестировать код")
        assert "Кратко" in out
    finally:
        clear_context()


def test_namespace_includes_get_text_transform_service() -> None:
    ns = PythonNamespaceBuilder().build()
    assert "get_text_transform_service" in ns
    assert callable(ns["get_text_transform_service"])
