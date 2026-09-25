"""Live checks for configured external OpenAI-compatible LLM providers.

These tests intentionally hit real provider APIs. They are skipped when a
provider key is absent or still a placeholder, and fail loudly for revoked keys,
stale model catalogs, unsupported smoke models, or broken chat completions.
"""

from __future__ import annotations

from typing import cast

import httpx
import pytest

from core.ai.adapters import (
    OpenRouterModelCatalogAdapter,
    create_model_catalog_adapter_registry,
)
from core.ai.provider_error import AIProviderErrorClass
from core.ai.providers import (
    EMBEDDING_PROVIDER_ORDER,
    PROVIDER_LITSERVE,
    AICapability,
)
from core.clients.llm.client import LLMClient
from core.clients.llm.runtime import create_llm_transport_client as create_transport_llm_client
from core.config import get_settings
from core.config.llm_openai_compat import resolve_provider_openai_v1_base_url
from core.http import ProxyStrategy
from core.http.client import request_with_strategy
from core.http.egress_route_preference import (
    egress_prefer_proxy_delete,
    normalized_http_origin,
)
from core.rag.openai_http_contracts import (
    PROVIDER_LITSERVE_PLACEHOLDER_BEARER,
    provider_litserve_rerank_http_url,
)
from core.types import JsonValue, require_json_object
from tests.core.clients.live_llm_provider_helpers import (
    EXPECTED_CHAT_MARKER,
    LIVE_LLM_PROVIDERS,
    SMOKE_MAX_TOKENS,
    catalog_id_candidates_for_runtime_model,
    classify_http_status_error,
    configured_provider,
    disable_testing_mode,
    discover_live_catalog,
    fetch_live_model_ids,
    fetch_live_model_records,
    live_chat_smoke_prompt,
    live_model_service,
    live_smoke_model,
    live_smoke_model_candidates,
    skip_openrouter_post_route_issue,
    skip_provider_content_filter,
    skip_provider_rate_limit,
    skip_provider_transient_unavailable,
    smoke_message,
)

pytestmark = [pytest.mark.network, pytest.mark.timeout(120)]

_LIVE_EMBEDDING_PROVIDERS = EMBEDDING_PROVIDER_ORDER


@pytest.mark.parametrize("provider", LIVE_LLM_PROVIDERS)
async def test_live_provider_model_catalog_returns_configured_smoke_model(provider: str) -> None:
    _ = configured_provider(provider)
    service = await live_model_service()

    models = await fetch_live_model_ids(provider)

    assert isinstance(models, list)
    assert models, f"{provider}: models catalog вернул пустой список"
    assert all(isinstance(model_id, str) and model_id.strip() for model_id in models)

    runtime_model = await live_smoke_model(provider, service)
    catalog_candidates = catalog_id_candidates_for_runtime_model(provider, runtime_model)
    expected_model_id = next((candidate for candidate in catalog_candidates if candidate in models), None)
    if expected_model_id is None:
        pytest.skip(
            f"{provider}: smoke_model={runtime_model!r} отсутствует в live catalog; tried={catalog_candidates!r}"
        )
    assert expected_model_id in models


@pytest.mark.parametrize("provider", LIVE_LLM_PROVIDERS)
async def test_live_provider_catalog_records_normalize_algorithm(provider: str) -> None:
    _ = configured_provider(provider)
    service = await live_model_service()

    records = await discover_live_catalog(provider)

    assert records, f"{provider}: live catalog вернул пустой список"
    assert all(record.provider == provider for record in records)
    assert all(record.model_id.strip() for record in records)
    assert all(record.capabilities for record in records)

    runtime_model = await live_smoke_model(provider, service)
    model_ids = [record.model_id for record in records]
    catalog_candidates = catalog_id_candidates_for_runtime_model(provider, runtime_model)
    smoke_catalog_id = next((candidate for candidate in catalog_candidates if candidate in model_ids), None)
    if smoke_catalog_id is None:
        pytest.skip(
            f"{provider}: smoke_model={runtime_model!r} отсутствует в normalized records; tried={catalog_candidates!r}"
        )
    smoke_records = [record for record in records if record.model_id == smoke_catalog_id]
    assert smoke_records
    assert AICapability.LLM_CHAT in smoke_records[0].capabilities

    for record in records:
        pricing = record.raw.get("pricing")
        if isinstance(pricing, dict):
            values = [
                pricing.get(key)
                for key in ("prompt", "completion", "input", "output", "request", "image")
                if key in pricing
            ]
            comparable_values = [
                value
                for value in values
                if isinstance(value, (str, int, float)) and not isinstance(value, bool)
            ]
            if comparable_values:
                expected_free = all(float(value) == 0.0 for value in comparable_values)
                assert record.is_free is expected_free
        if "tools" in record.supported_parameters:
            assert record.supports_tools is True
        if "structured_outputs" in record.supported_parameters or "json_schema" in record.supported_parameters:
            assert record.supports_structured_output is True


@pytest.mark.parametrize("provider", LIVE_LLM_PROVIDERS)
async def test_live_provider_chat_completion_smoke(provider: str) -> None:
    _ = configured_provider(provider)
    service = await live_model_service()
    prompt = live_chat_smoke_prompt(EXPECTED_CHAT_MARKER)
    candidate_models = await live_smoke_model_candidates(provider, service)
    last_rate_limit: httpx.HTTPStatusError | None = None
    last_unavailable: httpx.HTTPStatusError | None = None

    for model in candidate_models:
        with disable_testing_mode():
            llm = create_transport_llm_client(
                model_name=model,
                provider=provider,
                temperature=0.0,
                max_tokens=SMOKE_MAX_TOKENS,
            )

        assert isinstance(llm, LLMClient)
        assert llm.llm_provider == provider
        await egress_prefer_proxy_delete(normalized_http_origin(llm.base_url))

        try:
            result = await llm.invoke([smoke_message(prompt)], max_tokens=SMOKE_MAX_TOKENS)
        except httpx.HTTPStatusError as exc:
            error_class = classify_http_status_error(provider, exc)
            if error_class == AIProviderErrorClass.RATE_LIMITED:
                last_rate_limit = exc
                continue
            if error_class == AIProviderErrorClass.TRANSIENT:
                last_unavailable = exc
                continue
            skip_provider_content_filter(provider, exc)
            if error_class == AIProviderErrorClass.PAYMENT_REQUIRED:
                pytest.skip(
                    f"{provider}: catalog доступен, но inference требует положительный баланс"
                )
            raise

        assert isinstance(result, str)
        assert EXPECTED_CHAT_MARKER in result.strip(), (
            f"{provider}: smoke completion must contain {EXPECTED_CHAT_MARKER!r}, got {result!r}"
        )
        return

    if last_unavailable is not None:
        skip_provider_transient_unavailable(provider, last_unavailable)
    if last_rate_limit is not None:
        skip_provider_rate_limit(provider, last_rate_limit)
    pytest.fail(f"{provider}: нет доступной live smoke модели среди {candidate_models!r}")


@pytest.mark.parametrize("provider", _LIVE_EMBEDDING_PROVIDERS)
async def test_live_embedding_provider_probe_dimension_and_storage_policy(provider: str) -> None:
    _ = configured_provider(provider)
    service = await live_model_service()
    records = await fetch_live_model_records(provider)

    embedding_records = [
        record for record in records if AICapability.EMBEDDING in record.capabilities
    ]
    assert embedding_records, f"{provider}: catalog не дал ни одной embedding-модели"

    verified_records = [
        record for record in embedding_records if isinstance(record.native_dimension, int)
    ]
    if provider == "openrouter" and not verified_records:
        probe_response = await request_with_strategy(
            "POST",
            "https://openrouter.ai/api/v1/embeddings",
            headers=_openrouter_catalog_adapter().embedding_probe_headers(),
            json={"model": embedding_records[0].model_id, "input": "dimension probe"},
            timeout=60.0,
            strategy=ProxyStrategy.DIRECT_FIRST,
            direct_attempts=1,
            proxy_attempts=1,
        )
        skip_openrouter_post_route_issue(probe_response)
    if not verified_records:
        pytest.skip(f"{provider}: sync не подтвердил размерность ни одной embedding-модели")

    candidate = verified_records[0]
    if provider != "huggingface":
        embedding_origin = normalized_http_origin(
            resolve_provider_openai_v1_base_url(get_settings().llm, provider)
        )
        await egress_prefer_proxy_delete(embedding_origin)
    dimension = await service.probe_embedding_dimension(provider, candidate.model_id)
    assert dimension == candidate.native_dimension

    storage_dimension = get_settings().rag.embedding.api.dimension
    verified = candidate.model_copy(
        update={
            "native_dimension": dimension,
            "storage_dimension": service.storage_dimension_for_embedding(dimension),
            "metadata_status": "verified",
        }
    )
    if dimension == storage_dimension:
        assert verified.storage_dimension == storage_dimension
    else:
        assert verified.storage_dimension is None


async def test_live_openrouter_rerank_catalog_and_request_work() -> None:
    cfg = configured_provider("openrouter")
    service = await live_model_service()

    try:
        records = await service.discover_model_records_by_provider("openrouter")
    except httpx.HTTPStatusError as exc:
        skip_provider_rate_limit("openrouter", exc)
        raise

    rerank_records = [
        record for record in records if AICapability.RERANK in record.capabilities
    ]
    assert rerank_records, "openrouter: catalog не дал ни одной rerank-модели"

    last_status: int | None = None
    _ = cfg
    headers = _openrouter_catalog_adapter().provider_model_list_headers()
    for record in rerank_records:
        response = await request_with_strategy(
            "POST",
            "https://openrouter.ai/api/v1/rerank",
            headers=headers,
            json={
                "model": record.model_id,
                "query": "capital of France",
                "documents": [
                    "Paris is the capital of France.",
                    "Berlin is the capital of Germany.",
                ],
                "top_n": 2,
            },
            timeout=60.0,
            strategy=ProxyStrategy.DIRECT_FIRST,
            direct_attempts=1,
            proxy_attempts=1,
        )
        last_status = response.status_code
        skip_openrouter_post_route_issue(response)
        if response.status_code != 200:
            continue
        response_payload = cast(JsonValue, response.json())
        body = require_json_object(response_payload, "openrouter.rerank.response")
        results = body.get("results")
        assert isinstance(results, list) and results
        first = require_json_object(results[0], "openrouter.rerank.response.results[0]")
        score = first.get("relevance_score")
        assert isinstance(score, (int, float)) and not isinstance(score, bool)
        return

    pytest.fail(f"openrouter: ни одна catalog rerank-модель не выполнила запрос; last_status={last_status}")


@pytest.mark.timeout(180)
async def test_live_provider_litserve_catalog_embeddings_and_rerank_work(
    provider_litserve_service: object,
) -> None:
    _ = provider_litserve_service
    _ = _provider_litserve_base_url()
    service = await live_model_service()

    records = await service.fetch_model_records_by_provider(PROVIDER_LITSERVE)
    assert records, "provider_litserve: /v1/models вернул пустой каталог"

    embedding_records = [
        record for record in records if AICapability.EMBEDDING in record.capabilities
    ]
    rerank_records = [
        record for record in records if AICapability.RERANK in record.capabilities
    ]
    assert embedding_records, "provider_litserve: в каталоге нет embedding моделей"
    assert rerank_records, "provider_litserve: в каталоге нет rerank моделей"

    storage_dimension = get_settings().rag.embedding.api.dimension
    compatible_embeddings = [
        record for record in embedding_records if record.storage_dimension == storage_dimension
    ]
    assert compatible_embeddings, (
        f"provider_litserve: нет embedding модели под storage dimension={storage_dimension}"
    )
    embedding_model = compatible_embeddings[0]
    assert embedding_model.native_dimension == storage_dimension
    assert embedding_model.metadata_status == "verified"

    probed_dimension = await service.probe_embedding_dimension(
        PROVIDER_LITSERVE,
        embedding_model.model_id,
    )
    assert probed_dimension == embedding_model.native_dimension

    base_url = _provider_litserve_base_url()
    rerank_url = provider_litserve_rerank_http_url(base_url)
    rerank_response = await request_with_strategy(
        "POST",
        rerank_url,
        headers={
            "Authorization": f"Bearer {PROVIDER_LITSERVE_PLACEHOLDER_BEARER}",
            "Content-Type": "application/json",
        },
        json={
            "model": rerank_records[0].model_id,
            "query": "alpha",
            "passages": ["alpha beta", "gamma delta"],
        },
        timeout=60.0,
        strategy=ProxyStrategy.DIRECT_FIRST,
        direct_attempts=1,
        proxy_attempts=1,
    )
    assert rerank_response.status_code == 200
    rerank_payload = cast(JsonValue, rerank_response.json())
    body = require_json_object(rerank_payload, "provider_litserve.rerank.response")
    scores = body.get("scores")
    assert isinstance(scores, list) and len(scores) == 2
    assert all(isinstance(score, (int, float)) and not isinstance(score, bool) for score in scores)


def _provider_litserve_base_url() -> str:
    try:
        return get_settings().provider_litserve.resolve_openai_v1_base_url()
    except ValueError as exc:
        pytest.skip(f"provider_litserve.api.base_url не настроен: {exc}")


def _openrouter_catalog_adapter() -> OpenRouterModelCatalogAdapter:
    adapter = create_model_catalog_adapter_registry(get_settings()).get("openrouter")
    if not isinstance(adapter, OpenRouterModelCatalogAdapter):
        pytest.fail("openrouter catalog adapter has unexpected type")
    return adapter
