"""OpenAI-compatible request helpers shared by LLM clients."""

from __future__ import annotations

import json

from core.types import JsonObject, require_json_object


def masked_headers(headers: dict[str, str]) -> dict[str, str]:
    sanitized = dict(headers)
    for key in list(sanitized.keys()):
        lower_key = key.lower()
        if (
            lower_key == "authorization"
            or lower_key in ("api-key", "x-api-key")
            or lower_key.endswith("-api-key")
        ):
            sanitized[key] = "***"
    return sanitized


def pretty_json(payload: JsonObject) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def merge_openai_compatible_usage_into_usage_data(
    usage: JsonObject, usage_data: JsonObject
) -> None:
    """
    Заполняет usage_data из объекта usage финального чанка/ответа chat completions.

    Токены — стандартные поля OpenAI. Поля cost / cost_details — расширения
    (OpenRouter и др. совместимые шлюзы); пишем только если ключ есть и значение число.
    """
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    input_tokens = (
        int(prompt_tokens)
        if isinstance(prompt_tokens, (int, float)) and not isinstance(prompt_tokens, bool)
        else 0
    )
    output_tokens = (
        int(completion_tokens)
        if isinstance(completion_tokens, (int, float)) and not isinstance(completion_tokens, bool)
        else 0
    )
    usage_data["input_tokens"] = input_tokens
    usage_data["output_tokens"] = output_tokens
    total = usage.get("total_tokens")
    if isinstance(total, (int, float)) and not isinstance(total, bool):
        usage_data["total_tokens"] = int(total)
    else:
        usage_data["total_tokens"] = input_tokens + output_tokens

    cost = usage.get("cost")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        usage_data["provider_reported_cost"] = float(cost)

    details = usage.get("cost_details")
    if isinstance(details, dict):
        cost_details = require_json_object(details, "llm.usage.cost_details")
        upstream = cost_details.get("upstream_inference_cost")
        if isinstance(upstream, (int, float)) and not isinstance(upstream, bool):
            usage_data["provider_upstream_inference_cost"] = float(upstream)


__all__ = [
    "masked_headers",
    "merge_openai_compatible_usage_into_usage_data",
    "pretty_json",
]
