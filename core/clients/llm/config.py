"""Typed per-call LLM configuration.

The same model is used for the primary LLM attempt and every fallback attempt.
It is intentionally independent from service-specific models so apps can import
it from core without creating a core -> apps dependency.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Literal, Optional

from pydantic import Field, field_validator, model_validator

from core.clients.llm.model_routing import split_provider_prefixed_model
from core.models import StrictBaseModel

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]


class LLMCallConfig(StrictBaseModel):
    """One concrete LLM attempt config.

    `provider` and `model` may be partial at authoring time for primary node
    overrides; by the time the HTTP client attempts a call, both are resolved.
    """

    provider: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    temperature: Optional[float] = Field(default=None)
    max_tokens: Optional[int] = Field(default=None)
    api_key: Optional[str] = Field(default=None)
    folder_id: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    top_p: Optional[float] = Field(default=None)
    top_k: Optional[int] = Field(default=None)
    frequency_penalty: Optional[float] = Field(default=None)
    presence_penalty: Optional[float] = Field(default=None)
    seed: Optional[int] = Field(default=None)
    reasoning_effort: Optional[ReasoningEffort] = Field(default=None)
    extra_request_body: Optional[Dict[str, Any]] = Field(default=None)
    extra_request_headers: Optional[Dict[str, str]] = Field(default=None)

    # Runtime metadata used by the core LLM client for resolved attempts.
    default_headers: Dict[str, str] = Field(default_factory=dict, exclude=True)
    source: str = Field(default="explicit", exclude=True)
    supported_parameters: FrozenSet[str] = Field(default_factory=frozenset, exclude=True)
    input_modalities: FrozenSet[str] = Field(default_factory=frozenset, exclude=True)
    output_modalities: FrozenSet[str] = Field(default_factory=frozenset, exclude=True)
    context_length: Optional[int] = Field(default=None, exclude=True)

    @field_validator("provider", "model", "api_key", "folder_id", "base_url", mode="before")
    @classmethod
    def _strip_optional_strings(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value

    @field_validator("extra_request_body", mode="before")
    @classmethod
    def _extra_body_must_be_object(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        raise ValueError("extra_request_body должен быть объектом JSON, не массивом и не скаляром")

    @field_validator("extra_request_headers", mode="before")
    @classmethod
    def _extra_headers_must_be_object(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("extra_request_headers должен быть объектом JSON, не массивом и не скаляром")
        for key, header_value in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("extra_request_headers: ключи — непустые строки")
            if not isinstance(header_value, str):
                raise ValueError("extra_request_headers: значения должны быть строками")
        return value

    @model_validator(mode="before")
    @classmethod
    def _split_provider_prefixed_model(cls, raw_config: Any) -> Any:
        if not isinstance(raw_config, dict):
            return raw_config
        raw_provider = raw_config.get("provider")
        provider_is_set = (
            raw_provider is not None
            and isinstance(raw_provider, str)
            and raw_provider.strip() != ""
        )
        if provider_is_set:
            return raw_config
        raw_model = raw_config.get("model")
        if isinstance(raw_model, str):
            raw_model = raw_model.strip()
        split_provider, split_model = split_provider_prefixed_model(
            None,
            raw_model if isinstance(raw_model, str) else None,
        )
        if split_provider is None:
            return raw_config
        normalized_config = dict(raw_config)
        normalized_config["provider"] = split_provider
        normalized_config["model"] = split_model
        return normalized_config


def validate_fallback_model_configs(
    configs: Optional[list[LLMCallConfig]],
) -> Optional[list[LLMCallConfig]]:
    if configs is None:
        return None
    for fallback_index, fallback_config in enumerate(configs):
        if fallback_config.model is None or not str(fallback_config.model).strip():
            raise ValueError(f"fallback_models[{fallback_index}].model обязателен")
    return configs


__all__ = ["LLMCallConfig", "ReasoningEffort", "validate_fallback_model_configs"]
