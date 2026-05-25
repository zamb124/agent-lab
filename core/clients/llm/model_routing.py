"""LLM client package import path for model routing helpers."""

from __future__ import annotations

from core.llm_model_routing import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    LLM_ROUTING_PROVIDER_SLUGS,
    split_provider_prefixed_model,
)

__all__ = [
    "HUMANITEC_LLM_AUTO_MODEL",
    "HUMANITEC_LLM_PROVIDER",
    "LLM_ROUTING_PROVIDER_SLUGS",
    "split_provider_prefixed_model",
]
