"""Live platform LLM scoring tests on real provider catalog data."""

from __future__ import annotations

from collections.abc import Sequence

import httpx2
import pytest

from core.ai.free_pool import (
    PlatformFreeModelRecord,
    fetch_artificial_analysis_indices,
    platform_free_records_from_model_records,
)
from core.ai.models import AIModelRecord
from core.ai.provider_error import AIProviderErrorClass
from core.ai.providers import PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER, AICapability
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
    attach_live_artificial_analysis,
    build_scored_free_pool,
    classify_http_status_error,
    configured_provider,
    configured_smoke_model,
    disable_testing_mode,
    discover_live_catalog,
    live_chat_smoke_prompt,
    skip_provider_content_filter,
    skip_provider_rate_limit,
    skip_provider_transient_unavailable,
    smoke_message,
)

pytestmark = [pytest.mark.network, pytest.mark.timeout(180)]

_SMOKE_CANDIDATE_LIMIT = 5


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
    records = await discover_live_catalog(provider)

    free_records = _free_pool_catalog_records(records, provider)
    if not free_records:
        pytest.skip(f"{provider}: нет free-pool моделей после normalize")
    for record in free_records:
        assert record.provider == provider
        assert AICapability.LLM_CHAT in record.capabilities


@pytest.mark.parametrize("provider", PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER)
async def test_live_provider_computed_scoring_matches_invariants(provider: str) -> None:
    _ = configured_provider(provider)
    records = await discover_live_catalog(provider)

    free_records = _free_pool_catalog_records(records, provider)
    if not free_records:
        pytest.skip(f"{provider}: нет free-pool моделей для scoring")

    attached = await attach_live_artificial_analysis(free_records)
    records_by_provider = {provider: attached}
    pool_records = build_scored_free_pool(records_by_provider, providers=(provider,))
    catalog_index = catalog_by_key(records_by_provider)
    rows = pool_rows_from_records(pool_records, catalog_index)
    assert_scoring_expectations(rows, catalog_index)


async def test_live_openrouter_anchor_models_ranking() -> None:
    _ = configured_provider("openrouter")
    records = await discover_live_catalog("openrouter")
    aa_indices = await fetch_artificial_analysis_indices(get_settings())
    if not aa_indices:
        pytest.fail("openrouter настроен, но Artificial Analysis вернул пустой список")

    free_records = _free_pool_catalog_records(records, "openrouter")
    attached = await attach_live_artificial_analysis(free_records)
    records_by_provider = {"openrouter": attached}
    pool_records = build_scored_free_pool(records_by_provider, providers=("openrouter",))
    scores = {(record.provider, record.id): record.score for record in pool_records}

    if ("openrouter", "tencent/hy3:free") in scores:
        assert scores[("openrouter", "tencent/hy3:free")] > 20.0
    if ("openrouter", "qwen/qwen3-coder:free") in scores:
        assert scores[("openrouter", "qwen/qwen3-coder:free")] > 20.0
    if ("openrouter", OPENROUTER_ROUTER_MODEL_ID) in scores:
        assert scores[("openrouter", OPENROUTER_ROUTER_MODEL_ID)] <= 10.0

    aa_pool = [
        record
        for record in attached
        if record.artificial_analysis is not None
        and (record.provider, record.model_id) in scores
    ]
    if not aa_pool:
        return

    def _aa_intelligence(record: AIModelRecord) -> float:
        aa = record.artificial_analysis
        if aa is None:
            raise ValueError(f"{record.model_id} has no artificial_analysis")
        return aa.intelligence_index

    for record in aa_pool:
        assert scores[(record.provider, record.model_id)] == _aa_intelligence(record)
    aa_by_intelligence = sorted(
        aa_pool,
        key=lambda record: (_aa_intelligence(record), record.model_id),
        reverse=True,
    )
    aa_by_score = sorted(
        aa_pool,
        key=lambda record: (scores[(record.provider, record.model_id)], record.model_id),
        reverse=True,
    )
    assert [record.model_id for record in aa_by_score] == [
        record.model_id for record in aa_by_intelligence
    ]


async def test_live_bothub_free_suffix_in_pool() -> None:
    _ = configured_provider("bothub")
    records = await discover_live_catalog("bothub")
    suffix_free = [record for record in records if record.model_id.endswith(":free")]
    zero_price = [record for record in records if record.is_free is True]
    if not suffix_free and not zero_price:
        pytest.skip("bothub: live catalog не содержит :free и zero-price моделей")
    free_records = _free_pool_catalog_records(records, "bothub")
    if suffix_free:
        assert any(record.model_id.endswith(":free") for record in free_records)
        return
    assert free_records, "bothub: zero-price модели не попали в free-pool"


def _smoke_candidates(
    provider: str,
    pool_records: Sequence[PlatformFreeModelRecord],
) -> list[PlatformFreeModelRecord]:
    smoke_model = configured_smoke_model(provider)
    text_chat = [
        record
        for record in pool_records
        if "text" in record.input_modalities and "text" in record.output_modalities
    ]
    ordered = list(text_chat)
    if smoke_model is not None:
        pinned = [record for record in ordered if record.id == smoke_model]
        rest = [record for record in ordered if record.id != smoke_model]
        ordered = pinned + rest
    return ordered[:_SMOKE_CANDIDATE_LIMIT]


@pytest.mark.parametrize("provider", PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER)
async def test_live_free_pool_top_n_chat_smoke(provider: str) -> None:
    _ = configured_provider(provider)
    records = await discover_live_catalog(provider)

    free_records = _free_pool_catalog_records(records, provider)
    if not free_records:
        pytest.skip(f"{provider}: нет free-pool моделей")

    attached = await attach_live_artificial_analysis(free_records)
    records_by_provider = {provider: attached}
    pool_records = build_scored_free_pool(records_by_provider, providers=(provider,))
    candidates = _smoke_candidates(provider, pool_records)
    if not candidates:
        pytest.skip(f"{provider}: scored pool пуст")

    prompt = live_chat_smoke_prompt(EXPECTED_CHAT_MARKER)
    last_rate_limit: httpx2.HTTPStatusError | None = None
    last_unavailable: httpx2.HTTPStatusError | None = None

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
        except httpx2.HTTPStatusError as status_error:
            error_class = classify_http_status_error(provider, status_error)
            if error_class == AIProviderErrorClass.RATE_LIMITED:
                last_rate_limit = status_error
                continue
            if error_class == AIProviderErrorClass.TRANSIENT:
                last_unavailable = status_error
                continue
            if status_error.response.status_code in (400, 403, 404):
                continue
            skip_provider_content_filter(provider, status_error)
            if error_class == AIProviderErrorClass.PAYMENT_REQUIRED:
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
    pytest.fail(f"{provider}: none of smoke candidates responded successfully")
