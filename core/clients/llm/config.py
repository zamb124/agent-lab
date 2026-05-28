"""Типизированная per-call конфигурация LLM.

Та же модель используется для основной LLM-попытки и каждой fallback-попытки.
Намеренно независима от сервисных моделей, чтобы apps могли импортировать её
из core без зависимости core -> apps.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from pydantic import Field, field_validator, model_validator

from core.clients.llm.model_routing import split_provider_prefixed_model
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue, require_json_object

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]


class LLMCallConfig(StrictBaseModel):
    """Конфиг одной конкретной LLM-попытки.

    ``provider`` и ``model`` могут быть частичными на этапе authoring для primary
    override ноды; к моменту HTTP-вызова клиентом оба разрешены.
    """

    provider: str | None = Field(default=None)
    model: str | None = Field(default=None)
    temperature: float | None = Field(default=None)
    max_tokens: int | None = Field(default=None)
    api_key: str | None = Field(default=None)
    folder_id: str | None = Field(default=None)
    base_url: str | None = Field(default=None)
    top_p: float | None = Field(default=None)
    top_k: int | None = Field(default=None)
    frequency_penalty: float | None = Field(default=None)
    presence_penalty: float | None = Field(default=None)
    seed: int | None = Field(default=None)
    reasoning_effort: ReasoningEffort | None = Field(default=None)
    extra_request_body: JsonObject | None = Field(default=None)
    extra_request_headers: dict[str, str] | None = Field(default=None)

    # Runtime-метаданные, которые core LLM client использует для resolved attempts.
    default_headers: dict[str, str] = Field(default_factory=dict, exclude=True)
    source: str = Field(default="explicit", exclude=True)
    supported_parameters: frozenset[str] = Field(default_factory=frozenset, exclude=True)
    input_modalities: frozenset[str] = Field(default_factory=frozenset, exclude=True)
    output_modalities: frozenset[str] = Field(default_factory=frozenset, exclude=True)
    context_length: int | None = Field(default=None, exclude=True)

    @field_validator("provider", "model", "api_key", "folder_id", "base_url", mode="before")
    @classmethod
    def _strip_optional_strings(cls, value: JsonValue) -> JsonValue:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value

    @field_validator("extra_request_body", mode="before")
    @classmethod
    def _extra_body_must_be_object(cls, value: JsonValue) -> JsonObject | None:
        if value is None:
            return None
        return require_json_object(value, "extra_request_body")

    @field_validator("extra_request_headers", mode="before")
    @classmethod
    def _extra_headers_must_be_object(cls, value: JsonValue) -> dict[str, str] | None:
        if value is None:
            return None
        headers = require_json_object(value, "extra_request_headers")
        out: dict[str, str] = {}
        for key, header_value in headers.items():
            if not key.strip():
                raise ValueError("extra_request_headers: ключи — непустые строки")
            if not isinstance(header_value, str):
                raise ValueError("extra_request_headers: значения должны быть строками")
            out[key] = header_value
        return out

    @model_validator(mode="before")
    @classmethod
    def _split_provider_prefixed_model(cls, raw_config: object) -> object:
        if not isinstance(raw_config, Mapping):
            return raw_config
        config: dict[str, object] = dict(cast(Mapping[str, object], raw_config))
        raw_provider = config.get("provider")
        provider_is_set = (
            raw_provider is not None
            and isinstance(raw_provider, str)
            and raw_provider.strip() != ""
        )
        if provider_is_set:
            return config
        raw_model = config.get("model")
        if isinstance(raw_model, str):
            raw_model = raw_model.strip()
        split_provider, split_model = split_provider_prefixed_model(
            None,
            raw_model if isinstance(raw_model, str) else None,
        )
        if split_provider is None:
            return config
        normalized_config = dict(config)
        normalized_config["provider"] = split_provider
        normalized_config["model"] = split_model
        return normalized_config


def validate_fallback_model_configs(
    configs: list[LLMCallConfig] | None,
) -> list[LLMCallConfig] | None:
    if configs is None:
        return None
    for fallback_index, fallback_config in enumerate(configs):
        if fallback_config.model is None or not str(fallback_config.model).strip():
            raise ValueError(f"fallback_models[{fallback_index}].model обязателен")
    return configs


__all__ = ["LLMCallConfig", "ReasoningEffort", "validate_fallback_model_configs"]
