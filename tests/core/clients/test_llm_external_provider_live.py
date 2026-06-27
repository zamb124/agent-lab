"""Live checks for configured external OpenAI-compatible LLM providers.

These tests intentionally hit real provider APIs. They are skipped when a
provider key is absent or still a placeholder, and fail loudly for revoked keys,
stale model catalogs, unsupported smoke models, or broken chat completions.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import cast

import httpx
import pytest
from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.services.llm_models_service import LLMModelsService
from core.ai.adapters import (
    OpenRouterModelCatalogAdapter,
    create_model_catalog_adapter_registry,
)
from core.ai.model_catalog_repository import AIModelCatalogRepository
from core.ai.providers import (
    EMBEDDING_PROVIDER_ORDER,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    PROVIDER_LITSERVE,
    AICapability,
)
from core.clients.llm.client import LLMClient
from core.clients.llm.runtime import create_llm_transport_client as create_transport_llm_client
from core.clients.redis_client import RedisClient
from core.clients.scheduler_client import SchedulerClient
from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.config.llm_openai_compat import resolve_provider_openai_v1_base_url
from core.db.storage import Storage
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

pytestmark = [pytest.mark.network, pytest.mark.timeout(120)]

_LIVE_LLM_PROVIDERS = OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
_LIVE_EMBEDDING_PROVIDERS = EMBEDDING_PROVIDER_ORDER
_PLACEHOLDER_PREFIXES = ("YOUR_",)
_PLACEHOLDER_KEYS = {"sk-test-key", "test-key", "placeholder"}
_EXPECTED_MARKER = "PONG42"
_OPENROUTER_ROUTER_MODEL_ID = "openrouter/free"
_SMOKE_MAX_TOKENS = 32


def _is_provider_rate_limit(provider: str, exc: httpx.HTTPStatusError) -> bool:
    if exc.response.status_code == 429:
        return True
    if (
        provider == "openrouter"
        and exc.response.status_code == 401
        and "Missing Authentication header" in exc.response.text
    ):
        # OpenRouter free-model rate limits are retried through SMART egress proxy in
        # this environment; that proxy response can surface as a 401 without the
        # original rate-limit body. Treat it as a retryable external limit in live tests.
        return True
    return False


def _skip_provider_rate_limit(provider: str, exc: httpx.HTTPStatusError) -> None:
    if not _is_provider_rate_limit(provider, exc):
        return
    retry_after = cast(str | None, exc.response.headers.get("retry-after"))
    suffix = f"; retry-after={retry_after}" if retry_after else ""
    pytest.skip(f"{provider}: provider rate limit{suffix}")


def _skip_provider_auth_error(provider: str, exc: httpx.HTTPStatusError) -> None:
    if exc.response.status_code not in (401, 403):
        return
    pytest.skip(f"{provider}: catalog API rejected credentials ({exc.response.status_code})")


def _is_provider_transient_unavailable(exc: httpx.HTTPStatusError) -> bool:
    return exc.response.status_code in (502, 503, 504)


def _skip_provider_transient_unavailable(provider: str, exc: httpx.HTTPStatusError) -> None:
    if not _is_provider_transient_unavailable(exc):
        return
    pytest.skip(f"{provider}: provider temporarily unavailable ({exc.response.status_code})")


def _skip_provider_content_filter(provider: str, exc: httpx.HTTPStatusError) -> None:
    if exc.response.status_code != 400:
        return
    response_text = exc.response.text
    if (
        "content_filter" in response_text
        or "ResponsibleAIPolicyViolation" in response_text
    ):
        pytest.skip(f"{provider}: smoke prompt rejected by provider content policy")


def _live_chat_smoke_prompt(marker: str) -> str:
    """Формулировка без jailbreak-триггеров («exactly … and no other text») у Azure/GitHub Models."""
    return (
        f"Platform API connectivity check. "
        f"Write one short sentence that includes the token {marker}."
    )


def _skip_openrouter_post_route_issue(response: httpx.Response) -> None:
    if response.status_code == 429:
        pytest.skip("openrouter: provider rate limit")
    if (
        response.status_code == 401
        and "Missing Authentication header" in response.text
    ):
        pytest.skip("openrouter: POST route returned Missing Authentication header")


@contextmanager
def _disable_testing_mode() -> Generator[None]:
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


def _message(text: str) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=text))],
    )


def _configured_provider(provider: str) -> object:
    cfg = getattr(get_settings().llm, provider, None)
    api_key = getattr(cfg, "api_key", None)
    if cfg is None or not isinstance(api_key, str) or not api_key.strip():
        pytest.skip(f"{provider}: api_key не настроен")
    stripped_api_key = api_key.strip()
    if stripped_api_key in _PLACEHOLDER_KEYS or stripped_api_key.startswith(_PLACEHOLDER_PREFIXES):
        pytest.skip(f"{provider}: api_key остался placeholder")
    return cast(object, cfg)


def _live_model_service() -> LLMModelsService:
    settings = get_settings()
    db_url = settings.database.shared_url
    if not db_url:
        pytest.skip("database.shared_url не настроен для real AIModelCatalogRepository")
    repository = AIModelCatalogRepository(Storage(db_url=db_url))
    scheduler_client = SchedulerClient(ServiceClient())
    redis_client = RedisClient(settings.database.redis_url)
    return LLMModelsService(repository, scheduler_client, redis_client)


def _configured_smoke_model(provider: str) -> str | None:
    cfg = _configured_provider(provider)
    smoke_model = getattr(cfg, "smoke_model", None)
    if isinstance(smoke_model, str) and smoke_model.strip():
        return smoke_model.strip()
    return None


async def _live_smoke_model(provider: str, service: LLMModelsService) -> str:
    configured = _configured_smoke_model(provider)
    if provider == "openrouter" and configured == _OPENROUTER_ROUTER_MODEL_ID:
        return (await _live_smoke_model_candidates(provider, service))[0]
    if configured is not None:
        return configured
    if provider != "yandex":
        pytest.fail(f"{provider}: llm.{provider}.smoke_model должен быть непустой строкой")
    records = await service.discover_model_records_by_provider(provider)
    for record in records:
        if AICapability.LLM_CHAT in record.capabilities:
            return record.model_id
    pytest.fail("yandex: live catalog не содержит LLM_CHAT модели")


async def _openrouter_live_free_smoke_models() -> tuple[str, ...]:
    service = _live_model_service()
    records = await service.discover_model_records_by_provider("openrouter")
    text_records = [
        record
        for record in records
        if record.model_id != _OPENROUTER_ROUTER_MODEL_ID
        and AICapability.LLM_CHAT in record.capabilities
        and record.is_free is True
        and "text" in record.input_modalities
        and "text" in record.output_modalities
    ]
    if not text_records:
        pytest.fail("openrouter: live free-pool catalog не содержит конкретной text модели")
    return tuple(record.model_id for record in text_records[:8])


async def _live_smoke_model_candidates(provider: str, service: LLMModelsService) -> tuple[str, ...]:
    configured = _configured_smoke_model(provider)
    if provider == "openrouter" and configured == _OPENROUTER_ROUTER_MODEL_ID:
        return await _openrouter_live_free_smoke_models()
    return (await _live_smoke_model(provider, service),)


def _catalog_id_candidates_for_runtime_model(provider: str, runtime_model: str) -> tuple[str, ...]:
    """Catalog ids that may correspond to a runtime model string.

    Model ids may legally contain ``:`` themselves, for example OpenRouter
    ``*:free`` ids and Yandex ``gpt://...`` URIs.  Only HuggingFace Router
    uses a trailing ``:<provider-strategy>`` suffix in our smoke config that is
    not part of the public models catalog id.
    """
    candidates = [runtime_model]
    if provider == "huggingface":
        model_without_router_suffix, separator, router_suffix = runtime_model.rpartition(":")
        if separator and router_suffix in {"fastest", "auto"} and model_without_router_suffix:
            candidates.append(model_without_router_suffix)
    return tuple(dict.fromkeys(candidates))


def _catalog_id_for_runtime_model(
    provider: str,
    runtime_model: str,
    catalog_model_ids: list[str],
) -> str:
    for candidate in _catalog_id_candidates_for_runtime_model(provider, runtime_model):
        if candidate in catalog_model_ids:
            return candidate
    tried = _catalog_id_candidates_for_runtime_model(provider, runtime_model)
    pytest.fail(
        f"{provider}: smoke_model={runtime_model!r} отсутствует в live catalog; tried={tried!r}"
    )


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


@pytest.mark.parametrize("provider", _LIVE_LLM_PROVIDERS)
async def test_live_provider_model_catalog_returns_configured_smoke_model(provider: str) -> None:
    _ = _configured_provider(provider)
    service = _live_model_service()

    try:
        models = await service.fetch_models_by_provider(provider)
    except httpx.HTTPStatusError as exc:
        _skip_provider_rate_limit(provider, exc)
        _skip_provider_auth_error(provider, exc)
        raise

    assert isinstance(models, list)
    assert models, f"{provider}: models catalog вернул пустой список"
    assert all(isinstance(model_id, str) and model_id.strip() for model_id in models)

    runtime_model = await _live_smoke_model(provider, service)
    catalog_candidates = _catalog_id_candidates_for_runtime_model(provider, runtime_model)
    expected_model_id = next((candidate for candidate in catalog_candidates if candidate in models), None)
    if expected_model_id is None:
        pytest.skip(
            f"{provider}: smoke_model={runtime_model!r} отсутствует в live catalog; "
            f"tried={catalog_candidates!r}"
        )
    assert expected_model_id in models


@pytest.mark.parametrize("provider", _LIVE_LLM_PROVIDERS)
async def test_live_provider_catalog_records_normalize_algorithm(provider: str) -> None:
    _ = _configured_provider(provider)
    service = _live_model_service()

    try:
        records = await service.discover_model_records_by_provider(provider)
    except httpx.HTTPStatusError as exc:
        _skip_provider_rate_limit(provider, exc)
        _skip_provider_auth_error(provider, exc)
        raise

    assert records, f"{provider}: live catalog вернул пустой список"
    assert all(record.provider == provider for record in records)
    assert all(record.model_id.strip() for record in records)
    assert all(record.capabilities for record in records)

    runtime_model = await _live_smoke_model(provider, service)
    model_ids = [record.model_id for record in records]
    catalog_candidates = _catalog_id_candidates_for_runtime_model(provider, runtime_model)
    smoke_catalog_id = next((candidate for candidate in catalog_candidates if candidate in model_ids), None)
    if smoke_catalog_id is None:
        pytest.skip(
            f"{provider}: smoke_model={runtime_model!r} отсутствует в normalized records; "
            f"tried={catalog_candidates!r}"
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
        if "response_format" in record.supported_parameters or "structured_outputs" in record.supported_parameters:
            assert record.supports_structured_output is True


@pytest.mark.parametrize("provider", _LIVE_LLM_PROVIDERS)
async def test_live_provider_chat_completion_smoke(provider: str) -> None:
    _ = _configured_provider(provider)
    service = _live_model_service()
    prompt = _live_chat_smoke_prompt(_EXPECTED_MARKER)
    candidate_models = await _live_smoke_model_candidates(provider, service)
    last_rate_limit: httpx.HTTPStatusError | None = None
    last_unavailable: httpx.HTTPStatusError | None = None

    for model in candidate_models:
        with _disable_testing_mode():
            llm = create_transport_llm_client(
                model_name=model,
                provider=provider,
                temperature=0.0,
                max_tokens=_SMOKE_MAX_TOKENS,
            )

        assert isinstance(llm, LLMClient)
        assert llm.llm_provider == provider
        await egress_prefer_proxy_delete(normalized_http_origin(llm.base_url))

        try:
            result = await llm.invoke([_message(prompt)], max_tokens=_SMOKE_MAX_TOKENS)
        except httpx.HTTPStatusError as exc:
            if _is_provider_rate_limit(provider, exc):
                last_rate_limit = exc
                continue
            if _is_provider_transient_unavailable(exc):
                last_unavailable = exc
                continue
            _skip_provider_content_filter(provider, exc)
            if exc.response.status_code == 402:
                pytest.skip(
                    f"{provider}: catalog доступен, но inference требует положительный баланс"
                )
            raise

        assert isinstance(result, str)
        assert _EXPECTED_MARKER in result.strip(), (
            f"{provider}: smoke completion must contain {_EXPECTED_MARKER!r}, got {result!r}"
        )
        return

    if last_unavailable is not None:
        _skip_provider_transient_unavailable(provider, last_unavailable)
    if last_rate_limit is not None:
        _skip_provider_rate_limit(provider, last_rate_limit)
    pytest.fail(f"{provider}: нет доступной live smoke модели среди {candidate_models!r}")


@pytest.mark.parametrize("provider", _LIVE_EMBEDDING_PROVIDERS)
async def test_live_embedding_provider_probe_dimension_and_storage_policy(provider: str) -> None:
    _ = _configured_provider(provider)
    service = _live_model_service()

    try:
        records = await service.fetch_model_records_by_provider(provider)
    except httpx.HTTPStatusError as exc:
        _skip_provider_rate_limit(provider, exc)
        _skip_provider_auth_error(provider, exc)
        raise

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
        _skip_openrouter_post_route_issue(probe_response)
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
    cfg = _configured_provider("openrouter")
    service = _live_model_service()

    try:
        records = await service.discover_model_records_by_provider("openrouter")
    except httpx.HTTPStatusError as exc:
        _skip_provider_rate_limit("openrouter", exc)
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
        _skip_openrouter_post_route_issue(response)
        if response.status_code != 200:
            continue
        body = require_json_object(
            cast(JsonValue, response.json()),
            "openrouter.rerank.response",
        )
        results = body.get("results")
        assert isinstance(results, list) and results
        first = require_json_object(
            cast(JsonValue, results[0]),
            "openrouter.rerank.response.results[0]",
        )
        score = first.get("relevance_score")
        assert isinstance(score, (int, float)) and not isinstance(score, bool)
        return

    pytest.fail(f"openrouter: ни одна catalog rerank-модель не выполнила запрос; last_status={last_status}")


@pytest.mark.timeout(180)
async def test_live_provider_litserve_catalog_embeddings_and_rerank_work(
    provider_litserve_service,
) -> None:
    _ = provider_litserve_service
    _ = _provider_litserve_base_url()
    service = _live_model_service()

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
    body = require_json_object(
        cast(JsonValue, rerank_response.json()),
        "provider_litserve.rerank.response",
    )
    scores = body.get("scores")
    assert isinstance(scores, list) and len(scores) == 2
    assert all(isinstance(score, (int, float)) and not isinstance(score, bool) for score in scores)
