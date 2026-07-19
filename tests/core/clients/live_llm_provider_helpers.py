"""Shared helpers for live OpenAI-compatible LLM provider tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from typing import cast

import httpx
import pytest
from a2a.types import Message, Part
from a2a.types.a2a_pb2 import (
    ROLE_USER,
)

from apps.flows.src.services.llm_models_service import LLMModelsService
from core.ai.free_pool import (
    PlatformFreeModelRecord,
    compute_platform_free_record_scores,
    platform_free_records_from_model_records,
    sort_platform_free_records,
)
from core.ai.model_catalog_repository import AIModelCatalogRepository
from core.ai.models import AIModelRecord
from core.ai.providers import (
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER,
    AICapability,
)
from core.ai.scoring import PlatformModelScoreHint
from core.clients.redis_client import RedisClient
from core.clients.scheduler_client import SchedulerClient
from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.config.base import BaseSettings
from core.config.models import LLMModelScoreSeedItem
from core.db.storage import Storage

PLACEHOLDER_PREFIXES = ("YOUR_",)
PLACEHOLDER_KEYS = {"sk-test-key", "test-key", "placeholder"}
EXPECTED_CHAT_MARKER = "PONG42"
OPENROUTER_ROUTER_MODEL_ID = "openrouter/free"
SMOKE_MAX_TOKENS = 32
_PROVIDER_ROUTER_MODEL_KEYS = frozenset({("openrouter", OPENROUTER_ROUTER_MODEL_ID)})

LIVE_LLM_PROVIDERS = OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER


def is_provider_rate_limit(provider: str, exc: httpx.HTTPStatusError) -> bool:
    if exc.response.status_code == 429:
        return True
    if (
        provider == "openrouter"
        and exc.response.status_code == 401
        and "Missing Authentication header" in exc.response.text
    ):
        return True
    return False


def skip_provider_rate_limit(provider: str, exc: httpx.HTTPStatusError) -> None:
    if not is_provider_rate_limit(provider, exc):
        return
    retry_after = cast(str | None, exc.response.headers.get("retry-after"))
    suffix = f"; retry-after={retry_after}" if retry_after else ""
    pytest.skip(f"{provider}: provider rate limit{suffix}")


def skip_provider_auth_error(provider: str, exc: httpx.HTTPStatusError) -> None:
    if exc.response.status_code not in (401, 403):
        return
    pytest.skip(f"{provider}: catalog API rejected credentials ({exc.response.status_code})")


def is_provider_transient_unavailable(exc: httpx.HTTPStatusError) -> bool:
    return exc.response.status_code in (502, 503, 504)


def skip_provider_transient_unavailable(provider: str, exc: httpx.HTTPStatusError) -> None:
    if not is_provider_transient_unavailable(exc):
        return
    pytest.skip(f"{provider}: provider temporarily unavailable ({exc.response.status_code})")


def skip_provider_content_filter(provider: str, exc: httpx.HTTPStatusError) -> None:
    if exc.response.status_code != 400:
        return
    response_text = exc.response.text
    if (
        "content_filter" in response_text
        or "ResponsibleAIPolicyViolation" in response_text
    ):
        pytest.skip(f"{provider}: smoke prompt rejected by provider content policy")


def live_chat_smoke_prompt(marker: str) -> str:
    return (
        f"Platform API connectivity check. "
        f"Write one short sentence that includes the token {marker}."
    )


def skip_openrouter_post_route_issue(response: httpx.Response) -> None:
    if response.status_code == 429:
        pytest.skip("openrouter: provider rate limit")
    if (
        response.status_code == 401
        and "Missing Authentication header" in response.text
    ):
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
    cfg = getattr(get_settings().llm, provider, None)
    api_key = getattr(cfg, "api_key", None)
    if cfg is None or not isinstance(api_key, str) or not api_key.strip():
        return False
    stripped_api_key = api_key.strip()
    if stripped_api_key in PLACEHOLDER_KEYS or stripped_api_key.startswith(PLACEHOLDER_PREFIXES):
        return False
    return True


def configured_provider(provider: str) -> object:
    if not provider_api_key_configured(provider):
        pytest.skip(f"{provider}: api_key не настроен или placeholder")
    cfg = getattr(get_settings().llm, provider, None)
    if cfg is None:
        pytest.skip(f"{provider}: provider config missing")
    return cast(object, cfg)


def configured_free_pool_providers() -> tuple[str, ...]:
    configured: list[str] = []
    for provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER:
        if provider_api_key_configured(provider):
            configured.append(provider)
    return tuple(configured)


def live_model_service() -> LLMModelsService:
    settings = get_settings()
    db_url = settings.database.shared_url
    if not db_url:
        pytest.skip("database.shared_url не настроен для real AIModelCatalogRepository")
    repository = AIModelCatalogRepository(Storage(db_url=db_url))
    scheduler_client = SchedulerClient(ServiceClient())
    redis_client = RedisClient(settings.database.redis_url)
    return LLMModelsService(repository, scheduler_client, redis_client)


def configured_smoke_model(provider: str) -> str | None:
    _ = configured_provider(provider)
    cfg = getattr(get_settings().llm, provider, None)
    smoke_model = getattr(cfg, "smoke_model", None)
    if isinstance(smoke_model, str) and smoke_model.strip():
        return smoke_model.strip()
    return None


def hint_from_seed_item(item: LLMModelScoreSeedItem) -> PlatformModelScoreHint:
    editorial_prior = float(item.editorial_prior)
    score_dimensions = {key: float(value) for key, value in item.score_dimensions.items()}
    if not score_dimensions and item.score is not None:
        score_dimensions = {"general_chat": float(item.score)}
    return PlatformModelScoreHint(
        editorial_prior=editorial_prior,
        score_dimensions=score_dimensions,
        enabled=bool(item.enabled),
        source="config_seed",
        note=item.note,
    )


def hints_from_settings(settings: BaseSettings | None = None) -> dict[tuple[str, str], PlatformModelScoreHint]:
    resolved_settings = settings or get_settings()
    hints: dict[tuple[str, str], PlatformModelScoreHint] = {}
    for item in resolved_settings.llm.model_scoring.items:
        if item.capability != AICapability.LLM_CHAT:
            continue
        hints[(item.provider, item.model_id)] = hint_from_seed_item(item)
    return hints


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
    hints: Mapping[tuple[str, str], PlatformModelScoreHint] | None = None,
    providers: Sequence[str] | None = None,
) -> list[PlatformFreeModelRecord]:
    resolved_settings = settings or get_settings()
    pool_config = resolved_settings.llm.platform_free_pool
    scoring_config = resolved_settings.llm.model_scoring
    hint_map = hints if hints is not None else hints_from_settings(resolved_settings)
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
            hints=hint_map,
            scoring_config=scoring_config,
        )
        provider_records = sort_provider_free_records(
            provider_records,
            max_candidates=pool_config.max_candidates_per_provider,
            include_provider_router_as_last=pool_config.include_provider_router_as_last_free_fallback,
        )
        all_records.extend(provider_records)

    return sort_platform_free_records(
        all_records,
        max_candidates=pool_config.max_candidates_total,
    )


async def live_smoke_model(provider: str, service: LLMModelsService) -> str:
    configured = configured_smoke_model(provider)
    if provider == "openrouter" and configured == OPENROUTER_ROUTER_MODEL_ID:
        return (await live_smoke_model_candidates(provider, service))[0]
    if configured is not None:
        return configured
    if provider != "yandex":
        pytest.fail(f"{provider}: llm.{provider}.smoke_model должен быть непустой строкой")
    records = await service.discover_model_records_by_provider(provider)
    for record in records:
        if AICapability.LLM_CHAT in record.capabilities:
            return record.model_id
    pytest.fail("yandex: live catalog не содержит LLM_CHAT модели")


async def openrouter_live_free_smoke_models(service: LLMModelsService) -> tuple[str, ...]:
    records = await service.discover_model_records_by_provider("openrouter")
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
