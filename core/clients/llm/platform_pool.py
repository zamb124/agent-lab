"""Runtime candidate resolver for the provider-neutral platform free pool."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING

from core.ai.free_pool import (
    PLATFORM_FREE_MODEL_SOURCE,
    PLATFORM_FREE_MODELS_CACHE_KEY,
    PLATFORM_PAID_FALLBACK_SOURCE,
    PlatformFreeModelRecord,
    parse_platform_free_models,
)
from core.ai.llm_config import LLMCallConfig
from core.ai.providers import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    split_humanitec_llms_model_ref,
)
from core.clients.llm.provider_resolution import _resolve_headers_vars, _resolve_llm_call_config
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.config.base import BaseSettings
from core.config.llm_openai_compat import (
    collect_provider_api_keys,
    llm_provider_block,
)
from core.types import JsonObject

if TYPE_CHECKING:
    from core.state import ExecutionState

_platform_free_pool_redis: RedisClient | None = None


def _api_keys_for_free_pool_provider(settings: BaseSettings, provider: str) -> list[str]:
    """Ключи для кандидата free-pool; пустой список = провайдер недоступен локально."""
    cfg = llm_provider_block(settings.llm, provider)
    if cfg is None:
        return []
    return collect_provider_api_keys(cfg)


def llm_call_configs_for_provider_model(
    *,
    provider: str,
    model_id: str,
    settings: BaseSettings,
) -> list[LLMCallConfig]:
    """Те же candidate keys, что runtime free-pool: provider × model × каждый api_key."""
    return [
        _resolve_llm_call_config(
            LLMCallConfig(
                provider=provider,
                model=model_id,
                api_key=api_key,
                source=PLATFORM_FREE_MODEL_SOURCE,
            ),
            settings=settings,
            source=PLATFORM_FREE_MODEL_SOURCE,
        )
        for api_key in _api_keys_for_free_pool_provider(settings, provider)
    ]


def _candidate_from_platform_free_record(
    record: PlatformFreeModelRecord,
    *,
    settings: BaseSettings,
    api_key: str | None = None,
) -> LLMCallConfig:
    return _resolve_llm_call_config(
        LLMCallConfig(
            provider=record.provider,
            model=record.id,
            api_key=api_key,
            source=PLATFORM_FREE_MODEL_SOURCE,
            supported_parameters=frozenset(record.supported_parameters),
            input_modalities=frozenset(record.input_modalities),
            output_modalities=frozenset(record.output_modalities),
            context_length=record.context_length,
            capability_metadata_verified=True,
        ),
        settings=settings,
        source=PLATFORM_FREE_MODEL_SOURCE,
    )


def _platform_paid_fallback_candidate(settings: BaseSettings) -> LLMCallConfig:
    paid_fallback = settings.llm.platform_free_pool.paid_fallback
    return _resolve_llm_call_config(
        LLMCallConfig(
            provider=paid_fallback.provider,
            model=paid_fallback.model,
            source=PLATFORM_PAID_FALLBACK_SOURCE,
        ),
        settings=settings,
        source=PLATFORM_PAID_FALLBACK_SOURCE,
    )


async def _read_platform_free_records() -> list[PlatformFreeModelRecord]:
    global _platform_free_pool_redis

    if _platform_free_pool_redis is None:
        settings = get_settings()
        _platform_free_pool_redis = RedisClient(settings.database.redis_url)
    raw_cache_payload = await _platform_free_pool_redis.get(PLATFORM_FREE_MODELS_CACHE_KEY)
    return parse_platform_free_models(raw_cache_payload)


def _find_platform_free_record(
    records: Sequence[PlatformFreeModelRecord],
    *,
    provider: str,
    model_id: str,
) -> PlatformFreeModelRecord | None:
    for record in records:
        if record.provider == provider and record.id == model_id:
            return record
    return None


def _authoring_overrides(
    config: LLMCallConfig,
    *,
    state: "ExecutionState | None",
) -> dict[str, object]:
    return {
        field: value
        for field, value in {
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "top_k": config.top_k,
            "frequency_penalty": config.frequency_penalty,
            "presence_penalty": config.presence_penalty,
            "seed": config.seed,
            "reasoning_effort": config.reasoning_effort,
            "extra_request_body": (
                dict(config.extra_request_body) if config.extra_request_body else None
            ),
            "extra_request_headers": (
                _resolve_headers_vars(config.extra_request_headers, state)
                if config.extra_request_headers
                else None
            ),
        }.items()
        if value is not None
    }


def _with_authoring_overrides(
    candidate: LLMCallConfig,
    config: LLMCallConfig,
    *,
    state: "ExecutionState | None",
) -> LLMCallConfig:
    overrides = _authoring_overrides(config, state=state)
    if not overrides:
        return candidate
    return candidate.model_copy(update=overrides)


def _humanitec_llms_model(config: LLMCallConfig, settings: BaseSettings) -> str:
    model = config.model or settings.llm.default_model or HUMANITEC_LLM_AUTO_MODEL
    return str(model).strip() or HUMANITEC_LLM_AUTO_MODEL


def _humanitec_llms_ref_or_raise(model: str) -> tuple[str, str]:
    parsed = split_humanitec_llms_model_ref(model)
    if parsed is None:
        raise ValueError(
            "humanitec_llm model must be 'auto' or a provider-prefixed "
            + "free-pool model '<provider>:<model_id>'"
        )
    return parsed


def _candidate_from_humanitec_llms_ref(
    model: str,
    *,
    settings: BaseSettings,
    state: "ExecutionState | None",
    source: str = PLATFORM_FREE_MODEL_SOURCE,
) -> LLMCallConfig:
    provider, model_id = _humanitec_llms_ref_or_raise(model)
    return _resolve_llm_call_config(
        LLMCallConfig(provider=provider, model=model_id, source=source),
        settings=settings,
        state=state,
        source=source,
    )


def bootstrap_humanitec_llms_config(
    config: LLMCallConfig,
    *,
    settings: BaseSettings,
    state: "ExecutionState | None",
) -> LLMCallConfig:
    model = _humanitec_llms_model(config, settings)
    if model == HUMANITEC_LLM_AUTO_MODEL:
        return _platform_paid_fallback_candidate(settings)
    return _candidate_from_humanitec_llms_ref(
        model,
        settings=settings,
        state=state,
        source=PLATFORM_FREE_MODEL_SOURCE,
    )


def _config_uses_humanitec_llms(config: LLMCallConfig) -> bool:
    return config.provider == HUMANITEC_LLM_PROVIDER


def candidate_chain_uses_humanitec_llms(
    primary_config: LLMCallConfig,
    fallback_models: Sequence[LLMCallConfig | JsonObject] | None,
) -> bool:
    if _config_uses_humanitec_llms(primary_config):
        return True
    for raw_fallback in fallback_models or ():
        fallback = (
            raw_fallback
            if isinstance(raw_fallback, LLMCallConfig)
            else LLMCallConfig.model_validate(raw_fallback)
        )
        if _config_uses_humanitec_llms(fallback):
            return True
    return False


async def _expand_humanitec_llms_config(
    config: LLMCallConfig,
    *,
    settings: BaseSettings,
    records: Sequence[PlatformFreeModelRecord],
    state: "ExecutionState | None",
    include_paid_fallback: bool,
) -> list[LLMCallConfig]:
    model = _humanitec_llms_model(config, settings)
    candidates: list[LLMCallConfig] = []
    if model == HUMANITEC_LLM_AUTO_MODEL:
        for record in records:
            api_keys = _api_keys_for_free_pool_provider(settings, record.provider)
            for api_key in api_keys:
                candidates.append(
                    _with_authoring_overrides(
                        _candidate_from_platform_free_record(
                            record,
                            settings=settings,
                            api_key=api_key,
                        ),
                        config,
                        state=state,
                    )
                )
        if include_paid_fallback:
            candidates.append(
                _with_authoring_overrides(
                    _platform_paid_fallback_candidate(settings),
                    config,
                    state=state,
                )
            )
        return candidates

    provider, model_id = _humanitec_llms_ref_or_raise(model)
    record = _find_platform_free_record(records, provider=provider, model_id=model_id)
    if record is None:
        return []
    return [
        _with_authoring_overrides(
            _candidate_from_platform_free_record(
                record,
                settings=settings,
                api_key=api_key,
            ),
            config,
            state=state,
        )
        for api_key in _api_keys_for_free_pool_provider(settings, provider)
    ]


def _first_non_humanitec_fallback(
    fallback_models: Sequence[LLMCallConfig | JsonObject] | None,
) -> LLMCallConfig | None:
    for raw_fallback in fallback_models or ():
        fallback = _fallback_to_config(raw_fallback)
        if fallback.provider != HUMANITEC_LLM_PROVIDER:
            return fallback
    return None


def _humanitec_empty_chain_error(
    primary_config: LLMCallConfig,
    *,
    settings: BaseSettings,
    had_fallback_models: bool,
) -> RuntimeError:
    if had_fallback_models:
        return RuntimeError(
            "humanitec_llm: нет кандидатов после primary и fallback_models — "
            + "пустой free-pool cache и fallbacks не дали конфигов."
        )
    if primary_config.provider == HUMANITEC_LLM_PROVIDER:
        model = _humanitec_llms_model(primary_config, settings)
        if model != HUMANITEC_LLM_AUTO_MODEL:
            parsed = split_humanitec_llms_model_ref(model)
            if parsed is not None:
                provider, model_id = parsed
                return RuntimeError(
                    "humanitec_llm model не найден в verified free-pool cache: "
                    + f"{provider}:{model_id}. Обновите llm.platform_free_pool cache."
                )
    return RuntimeError(
        "humanitec_llm auto: нет кандидатов — задайте api_key хотя бы "
        + "для одного провайдера из free-pool (обычно llm.openrouter) "
        + "или включите paid_fallback."
    )


def _fallback_to_config(raw_fallback: LLMCallConfig | JsonObject) -> LLMCallConfig:
    if isinstance(raw_fallback, LLMCallConfig):
        return raw_fallback
    return LLMCallConfig.model_validate(raw_fallback)


def _make_humanitec_llms_candidate_chain_resolver(
    primary_config: LLMCallConfig,
    fallback_models: Sequence[LLMCallConfig | JsonObject] | None,
    *,
    settings: BaseSettings,
    state: "ExecutionState | None",
    include_paid_fallback: bool,
) -> Callable[[], Awaitable[list[LLMCallConfig]]]:
    async def _resolve() -> list[LLMCallConfig]:
        records = await _read_platform_free_records()
        candidates: list[LLMCallConfig] = []
        if primary_config.provider == HUMANITEC_LLM_PROVIDER:
            candidates.extend(
                await _expand_humanitec_llms_config(
                    primary_config,
                    settings=settings,
                    records=records,
                    state=state,
                    include_paid_fallback=include_paid_fallback,
                )
            )
            inherit_transport_from = candidates[0] if candidates else None
        else:
            primary = _resolve_llm_call_config(
                primary_config,
                settings=settings,
                state=state,
                source=primary_config.source,
            )
            candidates.append(primary)
            inherit_transport_from = primary

        for raw_fallback in fallback_models or ():
            fallback = _fallback_to_config(raw_fallback)
            if fallback.provider == HUMANITEC_LLM_PROVIDER:
                candidates.extend(
                    await _expand_humanitec_llms_config(
                        fallback,
                        settings=settings,
                        records=records,
                        state=state,
                        include_paid_fallback=include_paid_fallback,
                    )
                )
                continue
            candidates.append(
                _resolve_llm_call_config(
                    fallback,
                    settings=settings,
                    state=state,
                    inherit_transport_from=inherit_transport_from,
                    source="fallback",
                )
            )
        if not candidates:
            raise _humanitec_empty_chain_error(
                primary_config,
                settings=settings,
                had_fallback_models=bool(fallback_models),
            )
        return candidates

    return _resolve


def _make_platform_default_candidate_resolver(
    settings: BaseSettings,
    *,
    include_paid_fallback: bool,
) -> Callable[[], Awaitable[list[LLMCallConfig]]]:
    async def _resolve() -> list[LLMCallConfig]:
        candidates: list[LLMCallConfig] = []
        records = await _read_platform_free_records()
        for record in records:
            api_keys = _api_keys_for_free_pool_provider(settings, record.provider)
            for api_key in api_keys:
                candidates.append(
                    _candidate_from_platform_free_record(
                        record,
                        settings=settings,
                        api_key=api_key,
                    )
                )

        if include_paid_fallback:
            candidates.append(_platform_paid_fallback_candidate(settings))
        if not candidates:
            raise RuntimeError(
                "platform free-pool: no candidates — set api_key for at least "
                + "one free-pool provider (usually llm.openrouter) "
                + "or enable paid_fallback."
            )
        return candidates

    return _resolve


__all__ = [
    "_first_non_humanitec_fallback",
    "_make_platform_default_candidate_resolver",
    "_make_humanitec_llms_candidate_chain_resolver",
    "bootstrap_humanitec_llms_config",
    "candidate_chain_uses_humanitec_llms",
    "llm_call_configs_for_provider_model",
]
