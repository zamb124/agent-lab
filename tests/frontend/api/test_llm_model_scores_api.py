from __future__ import annotations

import pytest
from httpx import AsyncClient


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
    payload = {
        "provider": provider,
        "model_id": model_id,
        "capability": "llm_chat",
        "score": 77.5,
        "enabled": True,
        "score_dimensions": {"quality": 77.5},
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
    assert body["item"]["score"] == 77.5
    assert body["item"]["source"] == "manual"
    assert body["item"]["score_dimensions"] == {"quality": 77.5}
    assert "cache_rescore" in body

    score_map = await frontend_container.llm_model_score_repository.list_enabled_score_map("llm_chat")
    assert score_map[(provider, model_id)] == 77.5

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
                "score": 10,
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
                "score": 99,
                "enabled": True,
                "note": "should not overwrite",
            }
        ],
        force_refresh=False,
    )
    row = await repo.get(provider=provider, model_id=model_id, capability="llm_chat")
    assert skipped == {"created": 0, "updated": 0, "skipped": 1}
    assert row is not None
    assert row.score == 10

    forced = await repo.seed_many(
        [
            {
                "provider": provider,
                "model_id": model_id,
                "capability": "llm_chat",
                "score": 99,
                "enabled": False,
                "note": "forced",
            }
        ],
        force_refresh=True,
    )
    row = await repo.get(provider=provider, model_id=model_id, capability="llm_chat")
    assert forced == {"created": 0, "updated": 1, "skipped": 0}
    assert row is not None
    assert row.score == 99
    assert row.enabled is False

    _ = await repo.delete(provider=provider, model_id=model_id, capability="llm_chat")
