"""OpenAI-compatible request helpers shared by LLM clients."""

from __future__ import annotations

import json
from typing import Any, Dict


def masked_headers(headers: Dict[str, str]) -> Dict[str, str]:
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


def pretty_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def merge_openai_compatible_usage_into_usage_data(
    usage: Dict[str, Any], usage_data: Dict[str, Any]
) -> None:
    """
    Заполняет usage_data из объекта usage финального чанка/ответа chat completions.

    Токены — стандартные поля OpenAI. Поля cost / cost_details — расширения
    (OpenRouter и др. совместимые шлюзы); пишем только если ключ есть и значение число.
    """
    usage_data["input_tokens"] = int(usage.get("prompt_tokens") or 0)
    usage_data["output_tokens"] = int(usage.get("completion_tokens") or 0)
    total = usage.get("total_tokens")
    if total is not None:
        usage_data["total_tokens"] = int(total)
    else:
        usage_data["total_tokens"] = usage_data["input_tokens"] + usage_data["output_tokens"]

    cost = usage.get("cost")
    if isinstance(cost, (int, float)):
        usage_data["provider_reported_cost"] = float(cost)

    details = usage.get("cost_details")
    if isinstance(details, dict):
        upstream = details.get("upstream_inference_cost")
        if isinstance(upstream, (int, float)):
            usage_data["provider_upstream_inference_cost"] = float(upstream)


__all__ = [
    "masked_headers",
    "merge_openai_compatible_usage_into_usage_data",
    "pretty_json",
]
