"""HTTP-тесты публичного каталога демо-агентов лендинга."""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from core.context import clear_context, set_context
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.models.context_models import Context
from core.models.embed_models import EmbedConfig, EmbedMapping, EmbedStatus
from core.models.identity_models import User


@pytest_asyncio.fixture
async def system_landing_embed(frontend_container):
    """Виджет system с landing_visible для публичного API."""
    company = await frontend_container.company_repository.get(SYSTEM_COMPANY_ID)
    assert company is not None
    admin_user = await frontend_container.user_repository.get(
        "user_zambas124_yandex_ru_001",
    )
    user_for_ctx = (
        admin_user
        if admin_user
        else User(
            user_id="test_system_user",
            name="System Test",
            email="sys@test.com",
            companies={SYSTEM_COMPANY_ID: ["admin"]},
            active_company_id=SYSTEM_COMPANY_ID,
        )
    )
    set_context(
        Context(
            user=user_for_ctx,
            active_company=company,
            session_id="test",
            channel="test",
        )
    )
    embed_id = f"embed_landing_{uuid.uuid4().hex[:12]}"
    config = EmbedConfig(
        embed_id=embed_id,
        name="Demo lawyer",
        flow_id="universal_agent",
        branch_id="default",
        allowed_origins=[],
        status=EmbedStatus.ACTIVE,
        landing_visible=True,
        landing_card_image_url="https://example.com/card.png",
        landing_sort_order=10,
        created_by="test",
    )
    await frontend_container.embed_config_repository.set(config)
    await frontend_container.embed_mapping_repository.set(
        EmbedMapping(embed_id=embed_id, company_id=SYSTEM_COMPANY_ID)
    )
    clear_context()
    yield embed_id, config
    set_context(
        Context(
            user=user_for_ctx,
            active_company=company,
            session_id="test",
            channel="test",
        )
    )
    await frontend_container.embed_config_repository.delete(embed_id)
    await frontend_container.embed_mapping_repository.delete_by_embed_id(embed_id)
    clear_context()


@pytest.mark.asyncio
async def test_public_landing_agents_lists_visible_only(
    frontend_client: AsyncClient,
    system_landing_embed,
    unique_id,
):
    _ = unique_id
    embed_id, _config = system_landing_embed
    r = await frontend_client.get("/frontend/api/public/landing-agents")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    ids = [x["embed_id"] for x in body["items"]]
    assert embed_id in ids
    hit = next(x for x in body["items"] if x["embed_id"] == embed_id)
    assert hit["flow_id"] == "universal_agent"
    assert hit["landing_card_image_url"] == "https://example.com/card.png"


@pytest.mark.asyncio
async def test_public_landing_session_mints_token(
    frontend_client: AsyncClient,
    system_landing_embed,
):
    embed_id, _config = system_landing_embed
    r = await frontend_client.post(
        "/frontend/api/public/landing-agents/session",
        json={"embed_id": embed_id, "expires_in_seconds": 120},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "Bearer"
    assert len(data["token"]) > 20
    assert data["flow_id"] == "universal_agent"
    assert data["branch_id"] == "default"


@pytest.mark.asyncio
async def test_public_landing_session_rejects_non_existent(
    frontend_client: AsyncClient,
):
    r = await frontend_client.post(
        "/frontend/api/public/landing-agents/session",
        json={"embed_id": "embed_nonexistent_xxxxx"},
    )
    assert r.status_code == 404
