import pytest
import pytest_asyncio
from httpx import AsyncClient

from core.context import Context, clear_context, set_context
from core.docs.assistant import (
    DOCS_ASSISTANT_BRANCH_ID,
    DOCS_ASSISTANT_EMBED_ID,
    DOCS_ASSISTANT_FLOW_ID,
    DOCS_ASSISTANT_SESSION_ISSUER,
)
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.models.embed_models import EmbedConfig, EmbedMapping, EmbedStatus
from core.models.identity_models import User
from core.utils.tokens import get_token_service


@pytest_asyncio.fixture
async def system_docs_embed(frontend_container):
    company = await frontend_container.company_repository.get(SYSTEM_COMPANY_ID)
    assert company is not None
    user = User(
        user_id="test_docs_assistant_system",
        name="System Test",
        groups=["admin"],
        companies={SYSTEM_COMPANY_ID: ["admin"]},
        active_company_id=SYSTEM_COMPANY_ID,
    )
    set_context(
        Context(
            user=user,
            active_company=company,
            session_id="test_docs_assistant",
            channel="test",
        )
    )
    config = EmbedConfig(
        embed_id=DOCS_ASSISTANT_EMBED_ID,
        name="Documentation Assistant",
        flow_id=DOCS_ASSISTANT_FLOW_ID,
        branch_id=DOCS_ASSISTANT_BRANCH_ID,
        allowed_origins=[],
        status=EmbedStatus.ACTIVE,
        show_launcher=False,
        created_by="test",
    )
    await frontend_container.embed_config_repository.set(config)
    await frontend_container.embed_mapping_repository.set(
        EmbedMapping(embed_id=DOCS_ASSISTANT_EMBED_ID, company_id=SYSTEM_COMPANY_ID)
    )
    clear_context()
    yield config
    set_context(
        Context(
            user=user,
            active_company=company,
            session_id="test_docs_assistant_cleanup",
            channel="test",
        )
    )
    await frontend_container.embed_config_repository.delete(DOCS_ASSISTANT_EMBED_ID)
    await frontend_container.embed_mapping_repository.delete_by_embed_id(DOCS_ASSISTANT_EMBED_ID)
    clear_context()


@pytest.mark.asyncio
async def test_public_docs_assistant_session_mints_token(
    frontend_client: AsyncClient,
    frontend_container,
    system_docs_embed,
):
    _ = system_docs_embed
    response = await frontend_client.post(
        "/frontend/api/public/docs-assistant/session",
        headers={
            "origin": "http://testserver",
            "referer": "http://testserver/documentation/quickstart/",
        },
        json={
            "embed_id": DOCS_ASSISTANT_EMBED_ID,
            "origin": "http://testserver",
            "expires_in_seconds": 120,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "Bearer"
    assert data["flow_id"] == DOCS_ASSISTANT_FLOW_ID
    assert data["branch_id"] == DOCS_ASSISTANT_BRANCH_ID

    token_data = get_token_service().validate_token(data["token"])
    assert token_data is not None
    assert token_data.company_id == SYSTEM_COMPANY_ID
    assert token_data.roles == ["guest"]
    assert token_data.metadata["embed_id"] == DOCS_ASSISTANT_EMBED_ID
    assert token_data.metadata["embed_flow_id"] == DOCS_ASSISTANT_FLOW_ID
    assert token_data.metadata["embed_branch_id"] == DOCS_ASSISTANT_BRANCH_ID
    assert token_data.metadata["allowed_origin"] == "http://testserver"
    assert token_data.metadata["issued_by"] == DOCS_ASSISTANT_SESSION_ISSUER

    guest = await frontend_container.user_repository.get(token_data.user_id)
    assert guest is not None
    assert guest.active_company_id == SYSTEM_COMPANY_ID
    assert guest.companies[SYSTEM_COMPANY_ID] == ["guest"]
    assert "guest" in guest.groups
    assert guest.attributes["runtime_identity"] is True
    assert guest.attributes["kind"] == "embed_session_guest"
    assert guest.attributes["embed_id"] == DOCS_ASSISTANT_EMBED_ID


@pytest.mark.asyncio
async def test_public_docs_assistant_session_rejects_non_docs_referer(
    frontend_client: AsyncClient,
    system_docs_embed,
):
    _ = system_docs_embed
    response = await frontend_client.post(
        "/frontend/api/public/docs-assistant/session",
        headers={
            "origin": "http://testserver",
            "referer": "http://testserver/dashboard",
        },
        json={
            "embed_id": DOCS_ASSISTANT_EMBED_ID,
            "origin": "http://testserver",
        },
    )

    assert response.status_code == 403
