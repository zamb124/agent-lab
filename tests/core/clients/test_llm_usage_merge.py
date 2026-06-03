"""Парсинг usage из OpenAI-совместимых ответов (в т.ч. OpenRouter)."""

from core.clients.llm.openai_compat import (
    merge_openai_compatible_usage_into_usage_data as _merge_openai_compatible_usage_into_usage_data,
)
from core.types import JsonObject


def test_merge_tokens_only() -> None:
    target: JsonObject = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    _merge_openai_compatible_usage_into_usage_data(
        {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10},
        target,
    )
    assert target["input_tokens"] == 3
    assert target["output_tokens"] == 7
    assert target["total_tokens"] == 10
    assert "provider_reported_cost" not in target


def test_merge_openrouter_cost_and_upstream() -> None:
    target: JsonObject = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    _merge_openai_compatible_usage_into_usage_data(
        {
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
            "cost": 0.00042,
            "cost_details": {"upstream_inference_cost": 0.0001},
        },
        target,
    )
    assert target["provider_reported_cost"] == 0.00042
    assert target["provider_upstream_inference_cost"] == 0.0001
