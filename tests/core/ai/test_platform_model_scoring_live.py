"""Live platform LLM scoring tests on real provider catalog data."""

from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest

from core.ai.free_pool import platform_free_records_from_model_records
from core.ai.models import AIModelRecord
from core.ai.providers import AICapability, PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
from core.clients.llm.client import LLMClient
from core.clients.llm.runtime import create_llm_transport_client as create_transport_llm_client
from core.config import get_settings
from core.http.egress_route_preference import (
    egress_prefer_proxy_delete,
    normalized_http_origin,
)
from tests.core.ai.scoring_fixture_support import (
    assert_scoring_expectations,
    catalog_by_key,
    pool_rows_from_records,
)
from tests.core.clients.live_llm_provider_helpers import (
    EXPECTED_CHAT_MARKER,
    OPENROUTER_ROUTER_MODEL_ID,
    SMOKE_MAX_TOKENS,
    build_scored_free_pool,
    configured_provider,
    disable_testing_mode,
    is_provider_rate_limit,
    is_provider_transient_unavailable,
    live_chat_smoke_prompt,
    live_model_service,
    skip_provider_auth_error,
    skip_provider_content_filter,
    skip_provider_rate_limit,
    skip_provider_transient_unavailable,
    smoke_message,
)

pytestmark = [pytest.mark.network, pytest.mark.timeout(180)]


def _free_pool_catalog_records(
    service_records: Sequence[AIModelRecord],
    provider: str,
) -> list[AIModelRecord]:
    _ = provider
    settings_records = platform_free_records_from_model_records(
        service_records,
        settings=get_settings(),
    )
    eligible_ids = {record.id for record in settings_records}
    return [
        record
        for record in service_records
        if record.model_id in eligible_ids
        and AICapability.LLM_CHAT in record.capabilities
    ]


@pytest.mark.parametrize("provider", PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER)
async def test_live_provider_catalog_free_models_normalize(provider: str) -> None:
    _ = configured_provider(provider)
    service = live_model_service()
    try:
        records = await service.discover_model_records_by_provider(provider)
    except httpx.HTTPStatusError as exc:
        skip_provider_rate_limit(provider, exc)
        skip_provider_auth_error(provider, exc)
        raise

    free_records = _free_pool_catalog_records(records, provider)
    if not free_records:
        pytest.skip(f"{provider}: нет free-pool моделей после normalize")
    for record in free_records:
        assert record.provider == provider
        assert AICapability.LLM_CHAT in record.capabilities


@pytest.mark.parametrize("provider", PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER)
async def test_live_provider_computed_scoring_matches_invariants(provider: str) -> None:
    _ = configured_provider(provider)
    service = live_model_service()
    try:
        records = await service.discover_model_records_by_provider(provider)
    except httpx.HTTPStatusError as exc:
        skip_provider_rate_limit(provider, exc)
        skip_provider_auth_error(provider, exc)
        raise

    free_records = _free_pool_catalog_records(records, provider)
    if not free_records:
        pytest.skip(f"{provider}: нет free-pool моделей для scoring")

    records_by_provider = {provider: free_records}
    pool_records = build_scored_free_pool(records_by_provider, providers=(provider,))
    catalog_index = catalog_by_key(records_by_provider)
    rows = pool_rows_from_records(pool_records, catalog_index)
    assert_scoring_expectations(rows, catalog_index)


async def test_live_openrouter_anchor_models_ranking() -> None:
    _ = configured_provider("openrouter")
    service = live_model_service()
    try:
        records = await service.discover_model_records_by_provider("openrouter")
    except httpx.HTTPStatusError as exc:
        skip_provider_rate_limit("openrouter", exc)
        skip_provider_auth_error("openrouter", exc)
        raise

    free_records = _free_pool_catalog_records(records, "openrouter")
    records_by_provider = {"openrouter": free_records}
    pool_records = build_scored_free_pool(records_by_provider, providers=("openrouter",))
    scores = {(record.provider, record.id): record.score for record in pool_records}
    catalog_ids = {record.model_id for record in free_records}

    if "tencent/hy3:free" in catalog_ids:
        assert scores[("openrouter", "tencent/hy3:free")] > 20.0
    if "qwen/qwen3-coder:free" in catalog_ids:
        assert scores[("openrouter", "qwen/qwen3-coder:free")] > 20.0
    if ("openrouter", OPENROUTER_ROUTER_MODEL_ID) in scores:
        assert scores[("openrouter", OPENROUTER_ROUTER_MODEL_ID)] <= 10.0


def _chat_smoke_top_n(provider: str) -> int:
    if provider == "openrouter":
        return 5
    return 1


@pytest.mark.parametrize("provider", PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER)
async def test_live_free_pool_top_n_chat_smoke(provider: str) -> None:
    _ = configured_provider(provider)
    service = live_model_service()
    try:
        records = await service.discover_model_records_by_provider(provider)
    except httpx.HTTPStatusError as exc:
        skip_provider_rate_limit(provider, exc)
        skip_provider_auth_error(provider, exc)
        raise

    free_records = _free_pool_catalog_records(records, provider)
    if not free_records:
        pytest.skip(f"{provider}: нет free-pool моделей")

    records_by_provider = {provider: free_records}
    pool_records = build_scored_free_pool(records_by_provider, providers=(provider,))
    top_n = _chat_smoke_top_n(provider)
    candidates = pool_records[:top_n]
    if not candidates:
        pytest.skip(f"{provider}: scored pool пуст")

    prompt = live_chat_smoke_prompt(EXPECTED_CHAT_MARKER)
    last_rate_limit: httpx.HTTPStatusError | None = None
    last_unavailable: httpx.HTTPStatusError | None = None

    for record in candidates:
        with disable_testing_mode():
            llm = create_transport_llm_client(
                model_name=record.id,
                provider=record.provider,
                temperature=0.0,
                max_tokens=SMOKE_MAX_TOKENS,
            )
        assert isinstance(llm, LLMClient)
        await egress_prefer_proxy_delete(normalized_http_origin(llm.base_url))
        try:
            result = await llm.invoke([smoke_message(prompt)], max_tokens=SMOKE_MAX_TOKENS)
        except httpx.HTTPStatusError as exc:
            if is_provider_rate_limit(provider, exc):
                last_rate_limit = exc
                continue
            if is_provider_transient_unavailable(exc):
                last_unavailable = exc
                continue
            skip_provider_content_filter(provider, exc)
            if exc.response.status_code == 402:
                pytest.skip(f"{provider}: inference requires positive balance")
            raise

        if not isinstance(result, str):
            continue
        if EXPECTED_CHAT_MARKER not in result.strip():
            continue
        return

    if last_unavailable is not None:
        skip_provider_transient_unavailable(provider, last_unavailable)
    if last_rate_limit is not None:
        skip_provider_rate_limit(provider, last_rate_limit)
    pytest.fail(f"{provider}: none of top-{top_n} pool models responded successfully")
