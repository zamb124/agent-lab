from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

from core.ai.models import AIModelRecord
from core.ai.provider_error import AIProviderErrorClass
from core.ai.providers import PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER, AICapability
from core.clients.llm.candidate_cooldown import cooldown_redis_key, set_candidate_cooldown
from core.clients.llm.platform_pool import llm_call_configs_for_provider_model
from core.clients.redis_client import RedisClient
from core.config import get_settings


@pytest.mark.asyncio
async def test_llm_model_scores_api_is_system_admin_only(
    frontend_client: AsyncClient,
    auth_headers_company2,
    auth_headers_system_user2,
) -> None:
    company_response = await frontend_client.get(
        "/frontend/api/platform/llm-model-scores",
        headers=auth_headers_company2,
    )
    assert company_response.status_code == 403

    probe_response = await frontend_client.post(
        "/frontend/api/platform/llm-model-scores/probe-providers",
        headers=auth_headers_company2,
        json={},
    )
    assert probe_response.status_code == 403

    member_response = await frontend_client.get(
        "/frontend/api/platform/llm-model-scores",
        headers=auth_headers_system_user2,
    )
    assert member_response.status_code == 403


@pytest.mark.asyncio
async def test_llm_model_scores_api_upserts_lists_and_deletes_real_shared_row(
    frontend_client: AsyncClient,
    frontend_container,
    auth_headers_system,
    unique_id: str,
) -> None:
    provider = "openrouter"
    model_id = f"unit/test-score-{unique_id}"
    await frontend_container.ai_model_catalog_repository.set(
        AIModelRecord(
            provider=provider,
            model_id=model_id,
            capabilities=(AICapability.LLM_CHAT,),
            input_modalities=("text",),
            output_modalities=("text",),
            context_length=262144,
            supported_parameters=("tools",),
            is_free=True,
            free_reason="zero_price_catalog",
            raw={"name": "Unit Test 80B"},
        )
    )
    payload = {
        "provider": provider,
        "model_id": model_id,
        "capability": "llm_chat",
        "enabled": True,
        "editorial_prior": 1.5,
        "note": "unit test",
    }

    upsert_response = await frontend_client.put(
        "/frontend/api/platform/llm-model-scores",
        headers=auth_headers_system,
        json=payload,
    )

    assert upsert_response.status_code == 200
    body = upsert_response.json()
    assert body["item"]["provider"] == provider
    assert body["item"]["model_id"] == model_id
    assert body["item"]["capability"] == "llm_chat"
    assert body["item"]["score"] > 0.0
    assert body["item"]["editorial_prior"] == 1.5
    assert body["item"]["note"] == "unit test"
    assert body["item"]["enabled"] is True
    assert body["item"]["has_overlay_row"] is True
    assert body["item"]["score_breakdown"]
    assert "source" not in body["item"]
    assert "score_dimensions" not in body["item"]
    assert "cache_rescore" in body

    row = await frontend_container.llm_model_score_repository.get(
        provider=provider,
        model_id=model_id,
        capability="llm_chat",
    )
    assert row is not None
    assert row.editorial_prior == 1.5
    assert row.enabled is True
    assert row.note == "unit test"

    list_response = await frontend_client.get(
        "/frontend/api/platform/llm-model-scores",
        headers=auth_headers_system,
    )
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert [row["provider"] for row in list_body["providers"]] == list(
        PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
    )
    assert any(
        row["provider"] == provider and row["model_id"] == model_id and row["capability"] == "llm_chat"
        for row in list_body["items"]
    )
    scored = next(
        row
        for row in list_body["items"]
        if row["provider"] == provider and row["model_id"] == model_id
    )
    assert scored["availability"] in {"available", "cooldown", "disabled", "not_configured"}

    delete_response = await frontend_client.delete(
        f"/frontend/api/platform/llm-model-scores/llm_chat/{provider}/{model_id}",
        headers=auth_headers_system,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert await frontend_container.llm_model_score_repository.get(
        provider=provider,
        model_id=model_id,
        capability="llm_chat",
    ) is None


@pytest.mark.asyncio
async def test_llm_model_score_upsert_requires_catalog(
    frontend_client: AsyncClient,
    auth_headers_system,
    unique_id: str,
) -> None:
    response = await frontend_client.put(
        "/frontend/api/platform/llm-model-scores",
        headers=auth_headers_system,
        json={
            "provider": "openrouter",
            "model_id": f"missing/catalog-{unique_id}",
            "capability": "llm_chat",
            "enabled": True,
            "editorial_prior": 0.0,
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_llm_model_score_editorial_prior_outside_cap_is_422(
    frontend_client: AsyncClient,
    auth_headers_system,
    unique_id: str,
) -> None:
    response = await frontend_client.put(
        "/frontend/api/platform/llm-model-scores",
        headers=auth_headers_system,
        json={
            "provider": "openrouter",
            "model_id": f"cap-{unique_id}",
            "capability": "llm_chat",
            "enabled": True,
            "editorial_prior": 6,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_llm_model_score_overlay_upsert_updates_existing_row(
    frontend_container,
    unique_id: str,
) -> None:
    provider = "github"
    model_id = f"unit/overlay-{unique_id}"
    repo = frontend_container.llm_model_score_repository

    created = await repo.upsert_overlay(
        provider=provider,
        model_id=model_id,
        capability="llm_chat",
        enabled=True,
        editorial_prior=1.0,
        note="initial",
    )
    assert created.created is True
    assert created.row.editorial_prior == 1.0
    assert created.row.note == "initial"

    updated = await repo.upsert_overlay(
        provider=provider,
        model_id=model_id,
        capability="llm_chat",
        enabled=False,
        editorial_prior=-1.0,
        note="forced",
    )
    row = await repo.get(provider=provider, model_id=model_id, capability="llm_chat")
    assert updated.created is False
    assert row is not None
    assert row.editorial_prior == -1.0
    assert row.enabled is False
    assert row.note == "forced"

    _ = await repo.delete(provider=provider, model_id=model_id, capability="llm_chat")


@pytest.mark.asyncio
async def test_llm_model_scores_list_reads_redis_cooldown(
    frontend_client: AsyncClient,
    frontend_container,
    auth_headers_system,
    unique_id: str,
) -> None:
    provider = "openrouter"
    model_id = f"unit/test-cooldown-{unique_id}"
    await frontend_container.ai_model_catalog_repository.set(
        AIModelRecord(
            provider=provider,
            model_id=model_id,
            capabilities=(AICapability.LLM_CHAT,),
            input_modalities=("text",),
            output_modalities=("text",),
            context_length=262144,
            supported_parameters=("tools",),
            is_free=True,
            free_reason="zero_price_catalog",
            raw={"name": "Cooldown Unit"},
        )
    )
    upsert_response = await frontend_client.put(
        "/frontend/api/platform/llm-model-scores",
        headers=auth_headers_system,
        json={
            "provider": provider,
            "model_id": model_id,
            "capability": "llm_chat",
            "enabled": True,
            "editorial_prior": 0.0,
        },
    )
    assert upsert_response.status_code == 200

    settings = get_settings()
    configs = llm_call_configs_for_provider_model(
        provider=provider,
        model_id=model_id,
        settings=settings,
    )
    if not configs:
        pytest.fail("openrouter must be configured for free-pool in test settings")
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(429, text="rate limited by provider", request=request)
    http_error = httpx.HTTPStatusError("429", request=request, response=response)
    for candidate in configs:
        await set_candidate_cooldown(candidate, 40, error=http_error)
    redis = RedisClient(settings.database.redis_url)
    try:
        list_response = await frontend_client.get(
            "/frontend/api/platform/llm-model-scores",
            headers=auth_headers_system,
        )
        assert list_response.status_code == 200
        list_body = list_response.json()
        scored = next(
            row
            for row in list_body["items"]
            if row["provider"] == provider and row["model_id"] == model_id
        )
        assert scored["availability"] == "cooldown"
        assert scored["error_class"] == AIProviderErrorClass.RATE_LIMITED.value
        assert scored["http_status"] == 429
        assert "rate limited by provider" in scored["error_text"]
        assert scored["cooldown_seconds"] is not None
        assert scored["cooldown_seconds"] > 0
        provider_chip = next(row for row in list_body["providers"] if row["provider"] == provider)
        assert provider_chip["availability"] in {"available", "cooldown"}
    finally:
        _ = await redis.delete(*(cooldown_redis_key(candidate) for candidate in configs))
        _ = await frontend_container.llm_model_score_repository.delete(
            provider=provider,
            model_id=model_id,
            capability="llm_chat",
        )
