"""HTTP-тесты публичного каталога демо-агентов лендинга."""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from apps.flows.src.container import get_container
from apps.flows.src.models.flow_config import FlowConfig
from apps.frontend.services.landing_demo_seed import (
    ensure_system_landing_demo_embeds,
    landing_demo_embed_ids,
)
from core.context import clear_context, set_context
from core.identity.embed_guest_turns import EMBED_GUEST_USER_TURNS_REDIS_PREFIX
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


@pytest_asyncio.fixture
async def system_landing_embed_guest_capped(frontend_container, unique_id):
    """Виджет system с landing_visible и лимитом гостевых сообщений (Redis в flows)."""
    _ = unique_id
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
    flows_container = get_container()
    flow_id = f"landing_guest_cap_{uuid.uuid4().hex[:12]}"
    agent = FlowConfig(
        flow_id=flow_id,
        name="Guest cap agent",
        entry="main",
        nodes={
            "main": {
                "type": "code",
                "code": (
                    "async def run(state):\n"
                    "    state['response'] = 'ok'\n"
                    "    return state\n"
                ),
            }
        },
        edges=[{"from": "main", "to": None}],
    )
    await flows_container.flow_repository.set(agent)
    embed_id = f"embed_landing_cap_{uuid.uuid4().hex[:12]}"
    config = EmbedConfig(
        embed_id=embed_id,
        name="Demo guest cap",
        flow_id=flow_id,
        branch_id="default",
        allowed_origins=[],
        status=EmbedStatus.ACTIVE,
        landing_visible=True,
        landing_card_image_url="https://example.com/card-cap.png",
        landing_sort_order=99,
        guest_max_user_messages=5,
        created_by="test",
    )
    await frontend_container.embed_config_repository.set(config)
    await frontend_container.embed_mapping_repository.set(
        EmbedMapping(embed_id=embed_id, company_id=SYSTEM_COMPANY_ID)
    )
    clear_context()
    yield embed_id
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
    await flows_container.flow_repository.delete(flow_id)
    clear_context()


@pytest.mark.asyncio
async def test_public_landing_agents_exposes_voice_flags(
    frontend_client: AsyncClient,
    frontend_container,
    unique_id,
):
    company = await frontend_container.company_repository.get(SYSTEM_COMPANY_ID)
    assert company is not None
    admin_user = await frontend_container.user_repository.get(
        "user_zambas124_yandex_ru_001",
    )
    user_for_ctx = (
        admin_user
        if admin_user
        else User(
            user_id="test_voice_flags_user",
            name="System Test",
            email="voice@test.com",
            companies={SYSTEM_COMPANY_ID: ["admin"]},
            active_company_id=SYSTEM_COMPANY_ID,
        )
    )
    set_context(
        Context(
            user=user_for_ctx,
            active_company=company,
            session_id="test_voice_flags",
            channel="test",
        )
    )
    embed_id = f"embed_landing_voice_{unique_id}"
    config = EmbedConfig(
        embed_id=embed_id,
        name="Voice demo",
        flow_id="lawyer",
        branch_id="default",
        allowed_origins=[],
        status=EmbedStatus.ACTIVE,
        landing_visible=True,
        landing_card_image_url="https://example.com/v.png",
        landing_sort_order=1,
        created_by="test",
        voice_enabled=True,
        voice_default_on=True,
    )
    await frontend_container.embed_config_repository.set(config)
    await frontend_container.embed_mapping_repository.set(
        EmbedMapping(embed_id=embed_id, company_id=SYSTEM_COMPANY_ID)
    )
    clear_context()

    r = await frontend_client.get("/frontend/api/public/landing-agents")
    assert r.status_code == 200
    hit = next((x for x in r.json()["items"] if x["embed_id"] == embed_id), None)
    assert hit is not None
    assert hit["voice_enabled"] is True
    assert hit["voice_default_on"] is True

    set_context(
        Context(
            user=user_for_ctx,
            active_company=company,
            session_id="test_voice_flags",
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
    assert hit["voice_enabled"] is False
    assert hit["voice_default_on"] is False


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


@pytest.mark.asyncio
async def test_public_landing_agents_seeds_demo_when_catalog_empty(
    frontend_client: AsyncClient,
    frontend_container,
):
    company = await frontend_container.company_repository.get(SYSTEM_COMPANY_ID)
    assert company is not None
    admin_user = await frontend_container.user_repository.get(
        "user_zambas124_yandex_ru_001",
    )
    user_for_ctx = (
        admin_user
        if admin_user
        else User(
            user_id="test_system_user_seed_demo",
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
            session_id="test_seed_demo",
            channel="test",
        )
    )
    try:
        for eid in landing_demo_embed_ids():
            await frontend_container.embed_config_repository.delete(eid)
            await frontend_container.embed_mapping_repository.delete_by_embed_id(eid)
    finally:
        clear_context()

    r = await frontend_client.get("/frontend/api/public/landing-agents")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) >= 5
    flow_ids = {x["flow_id"] for x in body["items"]}
    assert "lawyer" in flow_ids

    await ensure_system_landing_demo_embeds(frontend_container)


@pytest.mark.asyncio
async def test_public_landing_agents_resolves_card_from_flow_store_url(
    frontend_client: AsyncClient,
    frontend_container,
    app,
    unique_id,
):
    _ = app
    company = await frontend_container.company_repository.get(SYSTEM_COMPANY_ID)
    assert company is not None
    admin_user = await frontend_container.user_repository.get(
        "user_zambas124_yandex_ru_001",
    )
    user_for_ctx = (
        admin_user
        if admin_user
        else User(
            user_id="test_system_user_flow_card",
            name="System Test",
            email="sys2@test.com",
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
    embed_id = f"embed_landing_flow_card_{unique_id}"
    config = EmbedConfig(
        embed_id=embed_id,
        name="Card from flow",
        flow_id="lawyer",
        branch_id="default",
        allowed_origins=[],
        status=EmbedStatus.ACTIVE,
        landing_visible=True,
        landing_card_image_url=None,
        landing_sort_order=5,
        created_by="test",
    )
    await frontend_container.embed_config_repository.set(config)
    await frontend_container.embed_mapping_repository.set(
        EmbedMapping(embed_id=embed_id, company_id=SYSTEM_COMPANY_ID)
    )
    clear_context()

    r = await frontend_client.get("/frontend/api/public/landing-agents")
    assert r.status_code == 200
    hit = next((x for x in r.json()["items"] if x["embed_id"] == embed_id), None)
    assert hit is not None
    assert "/flows/api/v1/files/download/" in hit["landing_card_image_url"]

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
async def test_embed_guest_limit_on_public_landing_session(
    frontend_client: AsyncClient,
    flows_client: AsyncClient,
    container,
    system_landing_embed_guest_capped,
    unique_id,
):
    embed_id = system_landing_embed_guest_capped
    ctx_id = f"ctx-{unique_id}"
    key = f"{EMBED_GUEST_USER_TURNS_REDIS_PREFIX}:{embed_id}:{ctx_id}"
    try:
        sess = await frontend_client.post(
            "/frontend/api/public/landing-agents/session",
            json={"embed_id": embed_id, "expires_in_seconds": 300},
        )
        assert sess.status_code == 200
        token = sess.json()["token"]
        for i in range(5):
            r = await flows_client.post(
                f"/flows/api/v1/embed/{embed_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "jsonrpc": "2.0",
                    "id": f"rpc-{i}",
                    "method": "message/send",
                    "params": {
                        "message": {
                            "messageId": str(uuid.uuid4()),
                            "role": "user",
                            "parts": [{"kind": "text", "text": f"m{i}"}],
                            "contextId": ctx_id,
                        }
                    },
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert "error" not in body, body
            assert "result" in body
        r6 = await flows_client.post(
            f"/flows/api/v1/embed/{embed_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "jsonrpc": "2.0",
                "id": "rpc-6",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"kind": "text", "text": "over"}],
                        "contextId": ctx_id,
                    }
                },
            },
        )
        assert r6.status_code == 200, r6.text
        err_body = r6.json()
        assert err_body.get("error") is not None
        assert err_body["error"]["code"] == -32000
        assert "лимит" in err_body["error"]["message"].lower()
    finally:
        await container.redis_client.delete(key)
