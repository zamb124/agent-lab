"""Shared helpers for live OpenAI-compatible LLM provider tests."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, cast

import httpx
import pytest
from a2a.types import Message, Part
from a2a.types.a2a_pb2 import (
    ROLE_USER,
)

from core.ai.adapters.catalog_base import AIProviderAdapterError
from core.ai.free_pool import (
    PlatformFreeModelRecord,
    compute_platform_free_record_scores,
    fetch_artificial_analysis_indices,
    platform_free_records_from_model_records,
    sort_platform_free_records,
)
from core.ai.llm_models_service import LLMModelsService
from core.ai.models import AIModelRecord
from core.ai.provider_error import (
    AIProviderErrorClass,
    classify_ai_provider_error,
    classify_ai_provider_http,
    truncate_llm_provider_error_text,
)
from core.ai.providers import (
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS,
    AICapability,
)
from core.ai.scoring import PlatformModelScoreOverlay, attach_artificial_analysis
from core.clients.llm.client import LLMClient
from core.clients.llm.runtime import create_llm_transport_client as create_transport_llm_client
from core.clients.redis_client import RedisClient
from core.clients.scheduler_client import SchedulerClient
from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.config.base import BaseSettings
from core.config.llm_openai_compat import (
    collect_provider_api_keys,
    llm_provider_block,
    provider_is_configured_for_free_pool,
)
from core.db.oxyde_runtime import init_oxyde_databases
from core.http.egress_route_preference import (
    egress_prefer_proxy_delete,
    normalized_http_origin,
)

PLACEHOLDER_PREFIXES = ("YOUR_",)
PLACEHOLDER_KEYS = {"sk-test-key", "test-key", "placeholder"}
EXPECTED_CHAT_MARKER = "PONG42"
OPENROUTER_ROUTER_MODEL_ID = "openrouter/free"
SMOKE_MAX_TOKENS = 32
_PROVIDER_ROUTER_MODEL_KEYS = frozenset({("openrouter", OPENROUTER_ROUTER_MODEL_ID)})

LIVE_LLM_PROVIDERS = OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER


_CATALOG_GONE_HTTP_STATUS = 410

_SOFT_PROVIDER_ERROR_CLASSES = frozenset(
    {
        AIProviderErrorClass.RATE_LIMITED,
        AIProviderErrorClass.PAYMENT_REQUIRED,
        AIProviderErrorClass.CONTENT_FILTER,
        AIProviderErrorClass.TRANSIENT,
    }
)
_SOFT_CATALOG_ERROR_CLASSES = frozenset(
    {
        AIProviderErrorClass.RATE_LIMITED,
        AIProviderErrorClass.PAYMENT_REQUIRED,
        AIProviderErrorClass.TRANSIENT,
    }
)


def classify_http_status_error(provider: str, exc: httpx.HTTPStatusError) -> AIProviderErrorClass:
    return classify_ai_provider_http(provider, exc.response.status_code, exc.response.text)


def skip_provider_rate_limit(provider: str, exc: httpx.HTTPStatusError) -> None:
    if classify_http_status_error(provider, exc) != AIProviderErrorClass.RATE_LIMITED:
        return
    retry_after = cast(str | None, exc.response.headers.get("retry-after"))
    suffix = f"; retry-after={retry_after}" if retry_after else ""
    pytest.skip(f"{provider}: provider rate limit{suffix}")


def skip_provider_auth_error(provider: str, exc: httpx.HTTPStatusError) -> None:
    if classify_http_status_error(provider, exc) != AIProviderErrorClass.AUTH_REJECTED:
        return
    pytest.skip(f"{provider}: catalog API rejected credentials ({exc.response.status_code})")


def skip_catalog_http_error(provider: str, exc: AIProviderAdapterError) -> None:
    if exc.status_code == _CATALOG_GONE_HTTP_STATUS:
        pytest.skip(f"{provider}: catalog endpoint gone ({exc.status_code})")
    if exc.status_code is None:
        return
    error_class = classify_ai_provider_http(provider, exc.status_code, str(exc))
    if error_class == AIProviderErrorClass.AUTH_REJECTED:
        pytest.skip(f"{provider}: catalog API rejected credentials ({exc.status_code})")
    if error_class == AIProviderErrorClass.RATE_LIMITED:
        pytest.skip(f"{provider}: provider rate limit")
    if error_class == AIProviderErrorClass.TRANSIENT:
        pytest.skip(f"{provider}: catalog temporarily unavailable ({exc.status_code})")


def skip_provider_transient_unavailable(provider: str, exc: httpx.HTTPStatusError) -> None:
    if classify_http_status_error(provider, exc) != AIProviderErrorClass.TRANSIENT:
        return
    pytest.skip(f"{provider}: provider temporarily unavailable ({exc.response.status_code})")


def skip_provider_content_filter(provider: str, exc: httpx.HTTPStatusError) -> None:
    if classify_http_status_error(provider, exc) != AIProviderErrorClass.CONTENT_FILTER:
        return
    pytest.skip(f"{provider}: smoke prompt rejected by provider content policy")


def live_chat_smoke_prompt(marker: str) -> str:
    return (
        f"Platform API connectivity check. "
        f"Write one short sentence that includes the token {marker}."
    )


def skip_openrouter_post_route_issue(response: httpx.Response) -> None:
    error_class = classify_ai_provider_http(
        "openrouter",
        response.status_code,
        response.text,
    )
    if error_class != AIProviderErrorClass.RATE_LIMITED:
        return
    if response.status_code == 429:
        pytest.skip("openrouter: provider rate limit")
    pytest.skip("openrouter: POST route returned Missing Authentication header")


@contextmanager
def disable_testing_mode() -> Generator[None]:
    old_testing = os.environ.get("TESTING")
    old_pytest = os.environ.pop("PYTEST_CURRENT_TEST", None)
    old_pytest_raise = os.environ.pop("_PYTEST_RAISE", None)
    os.environ["TESTING"] = "false"
    try:
        yield
    finally:
        if old_testing is None:
            _ = os.environ.pop("TESTING", None)
        else:
            os.environ["TESTING"] = old_testing
        if old_pytest is not None:
            os.environ["PYTEST_CURRENT_TEST"] = old_pytest
        if old_pytest_raise is not None:
            os.environ["_PYTEST_RAISE"] = old_pytest_raise


def smoke_message(text: str) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        role=ROLE_USER,
        parts=[Part(text=text)],
    )


def provider_api_key_configured(provider: str) -> bool:
    llm = get_settings().llm
    if provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS:
        if not provider_is_configured_for_free_pool(llm, provider):
            return False
    cfg = llm_provider_block(llm, provider)
    if cfg is None:
        return False
    keys = collect_provider_api_keys(cfg)
    if not keys:
        return False
    return not any(
        key in PLACEHOLDER_KEYS or key.startswith(PLACEHOLDER_PREFIXES) for key in keys
    )


def configured_provider(provider: str) -> object:
    if not provider_api_key_configured(provider):
        pytest.skip(f"{provider}: api_key не настроен или placeholder")
    cfg = llm_provider_block(get_settings().llm, provider)
    if cfg is None:
        pytest.skip(f"{provider}: provider config missing")
    return cfg


def configured_free_pool_providers() -> tuple[str, ...]:
    configured: list[str] = []
    for provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER:
        if provider_api_key_configured(provider):
            configured.append(provider)
    return tuple(configured)


async def live_model_service() -> LLMModelsService:
    settings = get_settings()
    db_url = settings.database.shared_url
    if not db_url:
        pytest.skip("database.shared_url не настроен")
    await init_oxyde_databases(default_url=db_url, shared_url=db_url)
    scheduler_client = SchedulerClient(ServiceClient())
    redis_client = RedisClient(settings.database.redis_url)
    return LLMModelsService(scheduler_client, redis_client)


def _skip_or_raise_catalog_error(provider: str, exc: BaseException) -> NoReturn:
    if isinstance(exc, httpx.HTTPStatusError):
        skip_provider_rate_limit(provider, exc)
        skip_provider_auth_error(provider, exc)
        raise
    if isinstance(exc, AIProviderAdapterError):
        skip_catalog_http_error(provider, exc)
        raise
    raise exc


async def discover_live_catalog(provider: str) -> list[AIModelRecord]:
    service = await live_model_service()
    try:
        return await service.discover_model_records_by_provider(provider)
    except (httpx.HTTPStatusError, AIProviderAdapterError) as exc:
        _skip_or_raise_catalog_error(provider, exc)


async def fetch_live_model_ids(provider: str) -> list[str]:
    service = await live_model_service()
    try:
        return await service.fetch_models_by_provider(provider)
    except (httpx.HTTPStatusError, AIProviderAdapterError) as extra:
        _skip_or_raise_catalog_error(provider, extra)


async def fetch_live_model_records(provider: str) -> list[AIModelRecord]:
    service = await live_model_service()
    try:
        return await service.fetch_model_records_by_provider(provider)
    except (httpx.HTTPStatusError, AIProviderAdapterError) as extra:
        _skip_or_raise_catalog_error(provider, extra)


def configured_smoke_model(provider: str) -> str | None:
    _ = configured_provider(provider)
    return _configured_smoke_model_or_none(provider)


def sort_provider_free_records(
    records: Iterable[PlatformFreeModelRecord],
    *,
    max_candidates: int,
    include_provider_router_as_last: bool,
) -> list[PlatformFreeModelRecord]:
    records_list = list(records)
    if not include_provider_router_as_last:
        return sort_platform_free_records(records_list, max_candidates=max_candidates)

    pinned_last = [
        record
        for record in records_list
        if (record.provider, record.id) in _PROVIDER_ROUTER_MODEL_KEYS
    ]
    normal_records = [
        record
        for record in records_list
        if (record.provider, record.id) not in _PROVIDER_ROUTER_MODEL_KEYS
    ]
    sorted_records = sort_platform_free_records(
        normal_records,
        max_candidates=max_candidates,
    )
    for record in pinned_last:
        if all(record.provider != existing.provider or record.id != existing.id for existing in sorted_records):
            sorted_records.append(record)
    return sorted_records


def build_scored_free_pool(
    records_by_provider: Mapping[str, Sequence[AIModelRecord]],
    settings: BaseSettings | None = None,
    *,
    overlays: Mapping[tuple[str, str], PlatformModelScoreOverlay] | None = None,
    providers: Sequence[str] | None = None,
) -> list[PlatformFreeModelRecord]:
    resolved_settings = settings or get_settings()
    pool_config = resolved_settings.llm.platform_free_pool
    provider_order = providers or PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER

    all_records: list[PlatformFreeModelRecord] = []
    for provider_slug in provider_order:
        catalog_records = list(records_by_provider.get(provider_slug, ()))
        if not catalog_records:
            continue
        provider_records = platform_free_records_from_model_records(
            catalog_records,
            settings=resolved_settings,
        )
        provider_records = compute_platform_free_record_scores(
            provider_records,
            catalog_records=catalog_records,
            overlays=overlays,
        )
        provider_records = sort_provider_free_records(
            provider_records,
            max_candidates=pool_config.max_candidates_per_provider,
            include_provider_router_as_last=pool_config.include_provider_router_as_last_free_fallback,
        )
        all_records.extend(provider_records)

    return sort_platform_free_records(
        all_records,
        max_candidates=0,
    )


async def attach_live_artificial_analysis(
    records: Sequence[AIModelRecord],
) -> list[AIModelRecord]:
    if not provider_api_key_configured("openrouter"):
        return list(records)
    indices = await fetch_artificial_analysis_indices(get_settings())
    return attach_artificial_analysis(list(records), indices)


async def live_smoke_model(provider: str, service: LLMModelsService) -> str:
    configured = configured_smoke_model(provider)
    if provider == "openrouter" and configured == OPENROUTER_ROUTER_MODEL_ID:
        return (await live_smoke_model_candidates(provider, service))[0]
    if configured is not None:
        return configured
    if provider != "yandex":
        pytest.fail(f"{provider}: llm.{provider}.smoke_model должен быть непустой строкой")
    records = await discover_live_catalog(provider)
    for record in records:
        if AICapability.LLM_CHAT in record.capabilities:
            return record.model_id
    pytest.fail("yandex: live catalog не содержит LLM_CHAT модели")


async def openrouter_live_free_smoke_models(service: LLMModelsService) -> tuple[str, ...]:
    _ = service
    records = await discover_live_catalog("openrouter")
    text_records = [
        record
        for record in records
        if record.model_id != OPENROUTER_ROUTER_MODEL_ID
        and AICapability.LLM_CHAT in record.capabilities
        and record.is_free is True
        and "text" in record.input_modalities
        and "text" in record.output_modalities
    ]
    if not text_records:
        pytest.fail("openrouter: live free-pool catalog не содержит конкретной text модели")
    return tuple(record.model_id for record in text_records[:8])


async def live_smoke_model_candidates(provider: str, service: LLMModelsService) -> tuple[str, ...]:
    configured = configured_smoke_model(provider)
    if provider == "openrouter" and configured == OPENROUTER_ROUTER_MODEL_ID:
        return await openrouter_live_free_smoke_models(service)
    return (await live_smoke_model(provider, service),)


def catalog_id_candidates_for_runtime_model(provider: str, runtime_model: str) -> tuple[str, ...]:
    candidates = [runtime_model]
    if provider == "huggingface":
        model_without_router_suffix, separator, router_suffix = runtime_model.rpartition(":")
        if separator and router_suffix in {"fastest", "auto"} and model_without_router_suffix:
            candidates.append(model_without_router_suffix)
    return tuple(dict.fromkeys(candidates))


def catalog_id_for_runtime_model(
    provider: str,
    runtime_model: str,
    catalog_model_ids: list[str],
) -> str:
    for candidate in catalog_id_candidates_for_runtime_model(provider, runtime_model):
        if candidate in catalog_model_ids:
            return candidate
    tried = catalog_id_candidates_for_runtime_model(provider, runtime_model)
    pytest.fail(
        f"{provider}: smoke_model={runtime_model!r} отсутствует в live catalog; tried={tried!r}"
    )


class LiveProbePhaseResult(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    NOT_CONFIGURED = "not_configured"
    CATALOG_EMPTY = "catalog_empty"
    CATALOG_FAILED = "catalog_failed"
    CHAT_FAILED = "chat_failed"
    CHAT_NO_MARKER = "chat_no_marker"


@dataclass(frozen=True)
class ProviderLiveProbe:
    provider: str
    configured: bool
    catalog_result: LiveProbePhaseResult
    catalog_detail: str
    catalog_model_count: int
    catalog_error_class: AIProviderErrorClass | None
    chat_result: LiveProbePhaseResult
    chat_detail: str
    chat_error_class: AIProviderErrorClass | None
    smoke_model: str | None


def _http_error_detail(exc: httpx.HTTPStatusError) -> str:
    return truncate_llm_provider_error_text(f"HTTP {exc.response.status_code}: {exc.response.text}")


def _catalog_failure(
    provider: str,
    *,
    status_code: int | None,
    detail: str,
) -> tuple[LiveProbePhaseResult, AIProviderErrorClass | None, str]:
    if status_code is None:
        return LiveProbePhaseResult.CATALOG_FAILED, None, truncate_llm_provider_error_text(detail)
    if status_code == _CATALOG_GONE_HTTP_STATUS:
        return LiveProbePhaseResult.SKIPPED, None, truncate_llm_provider_error_text(detail)
    error_class = classify_ai_provider_http(provider, status_code, detail)
    return LiveProbePhaseResult.CATALOG_FAILED, error_class, truncate_llm_provider_error_text(detail)


def provider_live_probe_is_hard_failure(probe: ProviderLiveProbe) -> bool:
    if not probe.configured:
        return False
    if probe.catalog_result in {
        LiveProbePhaseResult.NOT_CONFIGURED,
        LiveProbePhaseResult.SKIPPED,
    }:
        return False
    if probe.catalog_result == LiveProbePhaseResult.OK:
        if probe.chat_result in {
            LiveProbePhaseResult.OK,
            LiveProbePhaseResult.SKIPPED,
            LiveProbePhaseResult.NOT_CONFIGURED,
            LiveProbePhaseResult.CHAT_NO_MARKER,
        }:
            return False
        return probe.chat_error_class not in _SOFT_PROVIDER_ERROR_CLASSES
    if (
        probe.catalog_result == LiveProbePhaseResult.CATALOG_FAILED
        and probe.catalog_error_class in _SOFT_CATALOG_ERROR_CLASSES
    ):
        return False
    return True


def provider_live_probe_is_revoked_key(probe: ProviderLiveProbe) -> bool:
    if not probe.configured:
        return False
    return (
        probe.catalog_error_class == AIProviderErrorClass.AUTH_REJECTED
        or probe.chat_error_class == AIProviderErrorClass.AUTH_REJECTED
    )


def _phase_report_label(
    result: LiveProbePhaseResult,
    error_class: AIProviderErrorClass | None,
) -> str:
    if error_class is not None:
        return error_class.value
    return result.value


def format_provider_live_report(probes: Sequence[ProviderLiveProbe]) -> str:
    lines = [
        "LLM providers live report",
        f"{'provider':<14} {'cfg':<5} {'catalog':<18} {'chat':<18} detail",
    ]
    for probe in probes:
        configured_label = "yes" if probe.configured else "no"
        catalog_label = _phase_report_label(probe.catalog_result, probe.catalog_error_class)
        if probe.catalog_result == LiveProbePhaseResult.OK:
            catalog_label = f"ok n={probe.catalog_model_count}"
        chat_label = _phase_report_label(probe.chat_result, probe.chat_error_class)
        if probe.chat_result == LiveProbePhaseResult.OK and probe.smoke_model is not None:
            chat_label = f"ok {probe.smoke_model}"
        if probe.chat_result in {LiveProbePhaseResult.SKIPPED, LiveProbePhaseResult.NOT_CONFIGURED}:
            detail = probe.catalog_detail
        elif probe.chat_result == LiveProbePhaseResult.OK:
            detail = probe.smoke_model or probe.catalog_detail
        else:
            detail = probe.chat_detail
        lines.append(
            f"{probe.provider:<14} {configured_label:<5} {catalog_label:<18} {chat_label:<18} {detail}"
        )

    ok_count = sum(
        1 for probe in probes if probe.configured and probe.chat_result == LiveProbePhaseResult.OK
    )
    configured_count = sum(1 for probe in probes if probe.configured)
    hard_failures = [probe.provider for probe in probes if provider_live_probe_is_hard_failure(probe)]
    lines.append("")
    lines.append(
        f"configured={configured_count}/{len(probes)} chat_ok={ok_count} hard_fail={len(hard_failures)}"
    )
    if hard_failures:
        lines.append("hard_fail: " + ", ".join(hard_failures))
    return "\n".join(lines)


def _configured_smoke_model_or_none(provider: str) -> str | None:
    cfg = llm_provider_block(get_settings().llm, provider)
    if cfg is None:
        return None
    smoke_model = cfg.smoke_model
    if isinstance(smoke_model, str) and smoke_model.strip():
        return smoke_model.strip()
    return None


async def probe_openai_compat_provider(provider: str) -> ProviderLiveProbe:
    if not provider_api_key_configured(provider):
        return ProviderLiveProbe(
            provider=provider,
            configured=False,
            catalog_result=LiveProbePhaseResult.NOT_CONFIGURED,
            catalog_detail="api_key отсутствует или placeholder",
            catalog_model_count=0,
            catalog_error_class=None,
            chat_result=LiveProbePhaseResult.NOT_CONFIGURED,
            chat_detail="api_key отсутствует или placeholder",
            chat_error_class=None,
            smoke_model=None,
        )

    service = await live_model_service()
    smoke_model = _configured_smoke_model_or_none(provider)
    try:
        records = await service.discover_model_records_by_provider(provider)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == _CATALOG_GONE_HTTP_STATUS:
            return ProviderLiveProbe(
                provider=provider,
                configured=True,
                catalog_result=LiveProbePhaseResult.SKIPPED,
                catalog_detail=_http_error_detail(exc),
                catalog_model_count=0,
                catalog_error_class=None,
                chat_result=LiveProbePhaseResult.SKIPPED,
                chat_detail="chat не вызван: catalog endpoint gone",
                chat_error_class=None,
                smoke_model=smoke_model,
            )
        return ProviderLiveProbe(
            provider=provider,
            configured=True,
            catalog_result=LiveProbePhaseResult.CATALOG_FAILED,
            catalog_detail=_http_error_detail(exc),
            catalog_model_count=0,
            catalog_error_class=classify_http_status_error(provider, exc),
            chat_result=LiveProbePhaseResult.SKIPPED,
            chat_detail="chat не вызван: catalog недоступен",
            chat_error_class=None,
            smoke_model=smoke_model,
        )
    except AIProviderAdapterError as exc:
        _catalog_result, catalog_error_class, catalog_detail = _catalog_failure(
            provider,
            status_code=exc.status_code,
            detail=str(exc),
        )
        return ProviderLiveProbe(
            provider=provider,
            configured=True,
            catalog_result=_catalog_result,
            catalog_detail=catalog_detail,
            catalog_model_count=0,
            catalog_error_class=catalog_error_class,
            chat_result=LiveProbePhaseResult.SKIPPED,
            chat_detail="chat не вызван: catalog недоступен",
            chat_error_class=None,
            smoke_model=smoke_model,
        )
    except httpx.RequestError as exc:
        record = classify_ai_provider_error(provider, exc)
        return ProviderLiveProbe(
            provider=provider,
            configured=True,
            catalog_result=LiveProbePhaseResult.CATALOG_FAILED,
            catalog_detail=record.error_text,
            catalog_model_count=0,
            catalog_error_class=record.error_class,
            chat_result=LiveProbePhaseResult.SKIPPED,
            chat_detail="chat не вызван: catalog недоступен",
            chat_error_class=None,
            smoke_model=smoke_model,
        )

    if not records:
        return ProviderLiveProbe(
            provider=provider,
            configured=True,
            catalog_result=LiveProbePhaseResult.CATALOG_EMPTY,
            catalog_detail="GET /models вернул пустой список",
            catalog_model_count=0,
            catalog_error_class=None,
            chat_result=LiveProbePhaseResult.SKIPPED,
            chat_detail="chat не вызван: пустой catalog",
            chat_error_class=None,
            smoke_model=smoke_model,
        )

    catalog_ids = [record.model_id for record in records]
    if smoke_model is None and provider == "yandex":
        for record in records:
            if AICapability.LLM_CHAT in record.capabilities:
                smoke_model = record.model_id
                break
    if smoke_model is None:
        return ProviderLiveProbe(
            provider=provider,
            configured=True,
            catalog_result=LiveProbePhaseResult.OK,
            catalog_detail=f"n={len(records)}",
            catalog_model_count=len(records),
            catalog_error_class=None,
            chat_result=LiveProbePhaseResult.CHAT_FAILED,
            chat_detail=f"llm.{provider}.smoke_model пустой",
            chat_error_class=None,
            smoke_model=None,
        )

    candidate_models: tuple[str, ...]
    if provider == "openrouter" and smoke_model == OPENROUTER_ROUTER_MODEL_ID:
        text_records = [
            record
            for record in records
            if record.model_id != OPENROUTER_ROUTER_MODEL_ID
            and AICapability.LLM_CHAT in record.capabilities
            and record.is_free is True
            and "text" in record.input_modalities
            and "text" in record.output_modalities
        ]
        candidate_models = tuple(record.model_id for record in text_records[:8])
        if not candidate_models:
            return ProviderLiveProbe(
                provider=provider,
                configured=True,
                catalog_result=LiveProbePhaseResult.OK,
                catalog_detail=f"n={len(records)}",
                catalog_model_count=len(records),
                catalog_error_class=None,
                chat_result=LiveProbePhaseResult.CHAT_FAILED,
                chat_detail="openrouter: нет конкретной free text модели для smoke",
                chat_error_class=None,
                smoke_model=smoke_model,
            )
    else:
        candidate_models = (smoke_model,)

    catalog_detail = f"n={len(records)}"
    if smoke_model not in catalog_ids and not any(
        candidate in catalog_ids
        for candidate in catalog_id_candidates_for_runtime_model(provider, smoke_model)
    ):
        catalog_detail = f"n={len(records)}; smoke {smoke_model!r} нет в catalog"

    prompt = live_chat_smoke_prompt(EXPECTED_CHAT_MARKER)
    last_soft: ProviderLiveProbe | None = None
    last_hard_detail = ""
    last_hard_error_class: AIProviderErrorClass | None = None
    last_tried_model = smoke_model

    for model in candidate_models:
        last_tried_model = model
        with disable_testing_mode():
            llm = create_transport_llm_client(
                model_name=model,
                provider=provider,
                temperature=0.0,
                max_tokens=128,
            )
        if not isinstance(llm, LLMClient):
            return ProviderLiveProbe(
                provider=provider,
                configured=True,
                catalog_result=LiveProbePhaseResult.OK,
                catalog_detail=catalog_detail,
                catalog_model_count=len(records),
                catalog_error_class=None,
                chat_result=LiveProbePhaseResult.CHAT_FAILED,
                chat_detail=f"create_llm_transport_client вернул {type(llm).__name__}",
                chat_error_class=None,
                smoke_model=model,
            )
        await egress_prefer_proxy_delete(normalized_http_origin(llm.base_url))
        try:
            completion = await llm.invoke([smoke_message(prompt)], max_tokens=128)
        except httpx.HTTPStatusError as exc:
            error_class = classify_http_status_error(provider, exc)
            detail = _http_error_detail(exc)
            if error_class in _SOFT_PROVIDER_ERROR_CLASSES:
                last_soft = ProviderLiveProbe(
                    provider=provider,
                    configured=True,
                    catalog_result=LiveProbePhaseResult.OK,
                    catalog_detail=catalog_detail,
                    catalog_model_count=len(records),
                    catalog_error_class=None,
                    chat_result=LiveProbePhaseResult.CHAT_FAILED,
                    chat_detail=detail,
                    chat_error_class=error_class,
                    smoke_model=model,
                )
                continue
            last_hard_error_class = error_class
            last_hard_detail = detail
            continue
        except httpx.RequestError as exc:
            record = classify_ai_provider_error(provider, exc)
            last_hard_error_class = record.error_class
            last_hard_detail = record.error_text
            continue

        if not isinstance(completion, str) or EXPECTED_CHAT_MARKER not in completion.strip():
            last_soft = ProviderLiveProbe(
                provider=provider,
                configured=True,
                catalog_result=LiveProbePhaseResult.OK,
                catalog_detail=catalog_detail,
                catalog_model_count=len(records),
                catalog_error_class=None,
                chat_result=LiveProbePhaseResult.CHAT_NO_MARKER,
                chat_detail=truncate_llm_provider_error_text(
                    f"HTTP 200, marker {EXPECTED_CHAT_MARKER!r} отсутствует в {completion!r}"
                ),
                chat_error_class=None,
                smoke_model=model,
            )
            continue

        return ProviderLiveProbe(
            provider=provider,
            configured=True,
            catalog_result=LiveProbePhaseResult.OK,
            catalog_detail=catalog_detail,
            catalog_model_count=len(records),
            catalog_error_class=None,
            chat_result=LiveProbePhaseResult.OK,
            chat_detail=model,
            chat_error_class=None,
            smoke_model=model,
        )

    if last_soft is not None:
        return last_soft
    return ProviderLiveProbe(
        provider=provider,
        configured=True,
        catalog_result=LiveProbePhaseResult.OK,
        catalog_detail=catalog_detail,
        catalog_model_count=len(records),
        catalog_error_class=None,
        chat_result=LiveProbePhaseResult.CHAT_FAILED,
        chat_detail=last_hard_detail or f"нет доступной smoke модели среди {candidate_models!r}",
        chat_error_class=last_hard_error_class,
        smoke_model=last_tried_model,
    )


async def probe_all_openai_compat_providers() -> tuple[ProviderLiveProbe, ...]:
    probes = await asyncio.gather(
        *[probe_openai_compat_provider(provider) for provider in LIVE_LLM_PROVIDERS]
    )
    return tuple(probes)
