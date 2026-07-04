"""Хелперы фильтрации кандидатов для fallback-маршрутизации LLM."""

from __future__ import annotations

import hashlib

from core.ai.llm_config import LLMCallConfig


def candidate_key(candidate: LLMCallConfig) -> str:
    key_hash = (
        hashlib.sha256(candidate.api_key.encode()).hexdigest()[:12]
        if candidate.api_key
        else "nokey"
    )
    return f"{candidate.provider}:{candidate.base_url}:{candidate.model}:{key_hash}"


def candidate_capability_metadata_is_strict(candidate: LLMCallConfig) -> bool:
    return candidate.capability_metadata_verified or candidate.source == "platform_free"


def candidate_supports_request(
    candidate: LLMCallConfig,
    *,
    has_files: bool,
    has_tools: bool,
    has_response_format: bool,
) -> bool:
    # Пустые metadata означают "unknown" для explicit-моделей. Verified free-pool
    # записи являются результатом provider discovery, поэтому отсутствие capability
    # там трактуется как отсутствие поддержки request-shaping возможностей.
    strict_metadata = candidate_capability_metadata_is_strict(candidate)
    if has_files and candidate.input_modalities and not (
        "image" in candidate.input_modalities or "file" in candidate.input_modalities
    ):
        return False
    if has_tools and (
        (strict_metadata and "tools" not in candidate.supported_parameters)
        or (candidate.supported_parameters and "tools" not in candidate.supported_parameters)
    ):
        return False
    if has_response_format and (
        (
            strict_metadata
            and "structured_outputs" not in candidate.supported_parameters
            and "json_schema" not in candidate.supported_parameters
        )
        or (
            candidate.supported_parameters
            and "structured_outputs" not in candidate.supported_parameters
            and "json_schema" not in candidate.supported_parameters
        )
    ):
        return False
    return True


__all__ = [
    "candidate_key",
    "candidate_supports_request",
]
