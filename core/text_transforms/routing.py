"""Маршрутизация provider/model для текстовых трансформаций (префикс ``openrouter:model`` и т.д.)."""

from __future__ import annotations

from core.clients.llm.model_routing import split_provider_prefixed_model

__all__ = ["split_provider_prefixed_model", "should_use_litserve_format_markdown_http"]


def should_use_litserve_format_markdown_http(resolved_provider: str | None) -> bool:
    """
    Путь HTTP ``POST /v1/text/format_markdown`` используется, если провайдер не задан
    (дефолт платформы для структурирования в Markdown) или явно ``provider_litserve``.
    Любой другой разрешённый провайдер LLM идёт через ``get_llm`` (чанкованный промпт).
    """
    if resolved_provider is None:
        return True
    return resolved_provider == "provider_litserve"
