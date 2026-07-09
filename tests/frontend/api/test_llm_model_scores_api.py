from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.ai.scoring import split_score_dimensions


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
        "score_dimensions": {"coding": 77.5, "general_chat": 70.0},
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
    assert body["item"]["source"] == "manual"
    assert body["item"]["editorial_prior"] == 1.5
    assert body["item"]["score_dimensions"] == {"coding": 77.5, "general_chat": 70.0}
    assert body["item"]["score_breakdown"]
    assert "cache_rescore" in body

    row = await frontend_container.llm_model_score_repository.get(
        provider=provider,
        model_id=model_id,
        capability="llm_chat",
    )
    assert row is not None
    assert row.score > 0.0
    editorial_prior, hint_dimensions = split_score_dimensions(row.score_dimensions)
    assert editorial_prior == 1.5
    assert hint_dimensions == {"coding": 77.5, "general_chat": 70.0}

    list_response = await frontend_client.get(
        "/frontend/api/platform/llm-model-scores",
        headers=auth_headers_system,
    )
    assert list_response.status_code == 200
    assert any(
        row["provider"] == provider and row["model_id"] == model_id and row["capability"] == "llm_chat"
        for row in list_response.json()["items"]
    )

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
async def test_llm_model_score_seed_is_create_once_unless_forced(
    frontend_container,
    unique_id: str,
) -> None:
    provider = "github"
    model_id = f"unit/seed-score-{unique_id}"
    repo = frontend_container.llm_model_score_repository

    created = await repo.seed_many(
        [
            {
                "provider": provider,
                "model_id": model_id,
                "capability": "llm_chat",
                "score_dimensions": {"general_chat": 10.0},
                "enabled": True,
                "note": "initial",
            }
        ],
        force_refresh=False,
    )
    assert created == {"created": 1, "updated": 0, "skipped": 0}

    skipped = await repo.seed_many(
        [
            {
                "provider": provider,
                "model_id": model_id,
                "capability": "llm_chat",
                "score_dimensions": {"general_chat": 99.0},
                "enabled": True,
                "note": "should not overwrite",
            }
        ],
        force_refresh=False,
    )
    row = await repo.get(provider=provider, model_id=model_id, capability="llm_chat")
    assert skipped == {"created": 0, "updated": 0, "skipped": 1}
    assert row is not None
    _, hint_dimensions = split_score_dimensions(row.score_dimensions)
    assert hint_dimensions == {"general_chat": 10.0}
    assert row.note == "initial"

    forced = await repo.seed_many(
        [
            {
                "provider": provider,
                "model_id": model_id,
                "capability": "llm_chat",
                "score_dimensions": {"general_chat": 99.0},
                "editorial_prior": -1.0,
                "enabled": False,
                "note": "forced",
            }
        ],
        force_refresh=True,
    )
    row = await repo.get(provider=provider, model_id=model_id, capability="llm_chat")
    assert forced == {"created": 0, "updated": 1, "skipped": 0}
    assert row is not None
    editorial_prior, hint_dimensions = split_score_dimensions(row.score_dimensions)
    assert hint_dimensions == {"general_chat": 99.0}
    assert editorial_prior == -1.0
    assert row.enabled is False
    assert row.note == "forced"

    _ = await repo.delete(provider=provider, model_id=model_id, capability="llm_chat")
