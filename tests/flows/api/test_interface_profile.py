"""Auth-матрица interface-profile: session-путь flow и embed_session-путь embed.

Профиль — только control plane: document, values и artifacts приходят исключительно
через A2A bootstrap/stream, поэтому их отсутствие в ответе тоже часть контракта.
"""

import pytest
from httpx import AsyncClient

from core.a2a.extensions import (
    A2UI_EXTENSION_URI,
    A2UI_PLATFORM_CATALOG_ID,
)
from core.context import Context, clear_context, set_context
from core.models.flow_interface import (
    DEFAULT_CHAT_TEMPLATE_ID,
    DEFAULT_CHAT_TEMPLATE_VERSION,
    FlowInterfaceConfig,
    FlowInterfacePolicy,
    FlowUIDocumentTemplate,
    build_default_chat_document,
)
from core.models.identity_models import Company, User
from core.state.flow_ui import FlowUIDocument

PROFILE_KEYS = {
    "flow_id",
    "branch_id",
    "viewer",
    "look",
    "catalog",
    "capabilities",
    "flow_identity",
}


async def _create_embed(
    frontend_client: AsyncClient,
    auth_headers: dict[str, str],
    flow_id: str,
    *,
    assistant_title: str | None = None,
    interface_override: dict[str, object] | None = None,
) -> str:
    body: dict[str, object] = {
        "name": "Embed interface-profile",
        "flow_id": flow_id,
        "allowed_origins": ["https://larashved.ru"],
    }
    if assistant_title is not None:
        body["assistant_title"] = assistant_title
    if interface_override is not None:
        body["interface_override"] = interface_override
    response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json=body,
    )
    assert response.status_code == 200
    return response.json()["embed_id"]


async def _embed_session_token(
    frontend_client: AsyncClient, auth_headers: dict[str, str], embed_id: str
) -> str:
    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    return token_response.json()["token"]


async def _set_interface_policy(
    *, flow_id: str, company_id: str, user_id: str, **policy_fields: object
) -> None:
    from apps.flows.src.container import get_container

    policy = FlowInterfacePolicy.model_validate(policy_fields)
    interface = FlowInterfaceConfig(
        template=FlowUIDocumentTemplate(
            template_id=DEFAULT_CHAT_TEMPLATE_ID,
            version=DEFAULT_CHAT_TEMPLATE_VERSION,
            document=build_default_chat_document(policy=policy),
        ),
        policy=policy,
    )
    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    try:
        container = get_container()
        config = await container.flow_repository.get(flow_id)
        assert config is not None
        config.interface = interface
        await container.flow_repository.set(config)
    finally:
        clear_context()


async def _set_agent_identity_image_url(
    *,
    flow_id: str,
    company_id: str,
    user_id: str,
    image_url: str,
) -> None:
    from apps.flows.src.container import get_container

    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    try:
        container = get_container()
        config = await container.flow_repository.get(flow_id)
        assert config is not None
        payload = config.interface.template.document.model_dump(mode="python")
        identity = payload["surfaces"]["main"]["components"]["agent-identity"]
        properties = dict(identity.get("properties") or {})
        properties["image_url"] = image_url
        identity["properties"] = properties
        document = FlowUIDocument.model_validate(payload)
        config.interface = config.interface.model_copy(
            update={
                "template": config.interface.template.model_copy(update={"document": document})
            }
        )
        await container.flow_repository.set(config)
    finally:
        clear_context()


async def _set_store_card_image_url(
    *,
    flow_id: str,
    company_id: str,
    user_id: str,
    store_card_image_url: str,
) -> None:
    from apps.flows.src.container import get_container

    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    try:
        container = get_container()
        config = await container.flow_repository.get(flow_id)
        assert config is not None
        config.store_card_image_url = store_card_image_url
        await container.flow_repository.set(config)
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_flow_interface_profile_session_auth_defaults(
    flows_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    response = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface-profile", headers=auth_headers
    )
    assert response.status_code == 200
    profile = response.json()
    assert set(profile) == PROFILE_KEYS
    assert profile["flow_id"] == flow_id
    assert profile["branch_id"] == "default"
    assert profile["viewer"] == {
        "can_edit_flow": True,
        "can_interact": True,
        "can_share": True,
        "auth_mode": "platform",
    }
    assert profile["look"] is None
    assert profile["catalog"]["extension_uri"] == A2UI_EXTENSION_URI
    assert profile["catalog"]["platform_catalog_id"] == A2UI_PLATFORM_CATALOG_ID
    assert profile["capabilities"] == {
        "bootstrap": True,
        "autosync": True,
        "cancel": True,
        "files": True,
        "voice": True,
    }
    assert isinstance(profile["flow_identity"]["title"], str)
    assert profile["flow_identity"]["image_url"] is None


@pytest.mark.asyncio
async def test_interface_profile_never_carries_runtime_document(
    flows_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    response = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface-profile", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.text
    for forbidden in ("ui_document", "document_id", "revision", "artifacts", "values"):
        assert forbidden not in body


@pytest.mark.asyncio
async def test_flow_interface_profile_reflects_interface_policy(
    flows_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, company_id, user_id = embed_test_auth
    await _set_interface_policy(
        flow_id=flow_id,
        company_id=company_id,
        user_id=user_id,
        allow_cancel=False,
        show_files_panel=False,
        allow_voice=False,
    )

    response = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface-profile", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["capabilities"] == {
        "bootstrap": True,
        "autosync": True,
        "cancel": False,
        "files": False,
        "voice": False,
    }


@pytest.mark.asyncio
async def test_flow_interface_profile_unknown_flow_403(
    flows_client: AsyncClient, embed_test_auth, unique_id
):
    auth_headers, _, _, _ = embed_test_auth
    response = await flows_client.get(
        f"/flows/api/v1/missing_flow_{unique_id}/interface-profile", headers=auth_headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_flow_interface_profile_unknown_branch_404(
    flows_client: AsyncClient, embed_test_auth, unique_id
):
    from apps.flows.src.container import get_container
    from apps.flows.src.models.flow_config import BranchConfig

    auth_headers, flow_id, company_id, user_id = embed_test_auth
    flows_container = get_container()

    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    try:
        config = await flows_container.flow_repository.get(flow_id)
        assert config is not None
        config.branches = {"support": BranchConfig(name="Support")}
        await flows_container.flow_repository.set(config)
    finally:
        clear_context()

    known_branch = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface-profile",
        headers=auth_headers,
        params={"branch_id": "support"},
    )
    assert known_branch.status_code == 200
    assert known_branch.json()["branch_id"] == "support"

    response = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface-profile",
        headers=auth_headers,
        params={"branch_id": f"missing_branch_{unique_id}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_embed_interface_profile_embed_session_token(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(
        frontend_client, auth_headers, flow_id, assistant_title="Лара"
    )
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface-profile",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
    )
    assert response.status_code == 200
    profile = response.json()
    assert profile["flow_id"] == flow_id
    assert profile["viewer"] == {
        "can_edit_flow": False,
        "can_interact": True,
        "can_share": False,
        "auth_mode": "embed",
    }
    look = profile["look"]
    assert look is not None
    assert look["assistant_title"] == "Лара"
    assert look["theme"] == "dark"
    assert look["show_launcher"] is True
    assert profile["catalog"]["platform_catalog_id"] == A2UI_PLATFORM_CATALOG_ID

    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers
    )


@pytest.mark.asyncio
async def test_embed_interface_profile_applies_interface_override(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, company_id, user_id = embed_test_auth
    await _set_interface_policy(
        flow_id=flow_id,
        company_id=company_id,
        user_id=user_id,
        allow_cancel=True,
        show_files_panel=True,
    )
    embed_id = await _create_embed(
        frontend_client,
        auth_headers,
        flow_id,
        interface_override={
            "policy": {"allow_cancel": False, "show_files_panel": False},
            "initial_content": {"greeting": "Embed greeting"},
        },
    )
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    embed_profile = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface-profile",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
    )
    assert embed_profile.status_code == 200
    embed_capabilities = embed_profile.json()["capabilities"]
    assert embed_capabilities["cancel"] is False
    assert embed_capabilities["files"] is False

    session_profile = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface-profile", headers=auth_headers
    )
    assert session_profile.status_code == 200
    session_capabilities = session_profile.json()["capabilities"]
    assert session_capabilities["cancel"] is True
    assert session_capabilities["files"] is True

    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers
    )


@pytest.mark.asyncio
async def test_embed_interface_profile_rejects_wrong_origin(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface-profile",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://evil.example",
        },
    )
    assert response.status_code == 403

    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers
    )


@pytest.mark.asyncio
async def test_embed_interface_profile_rejects_foreign_embed_token(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    other_embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    other_token = await _embed_session_token(
        frontend_client, auth_headers, other_embed_id
    )

    response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface-profile",
        headers={
            "Authorization": f"Bearer {other_token}",
            "Origin": "https://larashved.ru",
        },
    )
    assert response.status_code == 403

    for eid in (embed_id, other_embed_id):
        await frontend_client.delete(
            f"/frontend/api/embed/configs/{eid}", headers=auth_headers
        )


@pytest.mark.asyncio
async def test_embed_interface_profile_unknown_embed_404(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth, unique_id
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/missing_embed_{unique_id}/interface-profile",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
    )
    assert response.status_code == 404

    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers
    )


def test_embed_config_has_no_interface_behavior_fields():
    """EmbedConfig — identity/security/look; поведение живёт в FlowConfig.interface."""
    from core.models.embed_models import EmbedConfig, EmbedInterfaceLook

    for field_name in (
        "show_reasoning",
        "show_tool_calls",
        "greeting_message",
    ):
        assert field_name not in EmbedConfig.model_fields
        assert field_name not in EmbedInterfaceLook.model_fields
    assert "interface_override" in EmbedConfig.model_fields


@pytest.mark.asyncio
async def test_interface_profile_image_url_from_document_not_store_card(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, company_id, user_id = embed_test_auth
    await _set_store_card_image_url(
        flow_id=flow_id,
        company_id=company_id,
        user_id=user_id,
        store_card_image_url="https://cdn.example/store-card.png",
    )
    store_only = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface-profile", headers=auth_headers
    )
    assert store_only.status_code == 200
    assert store_only.json()["flow_identity"]["image_url"] is None

    image_url = "/flows/api/v1/files/download/agent-identity"
    await _set_agent_identity_image_url(
        flow_id=flow_id,
        company_id=company_id,
        user_id=user_id,
        image_url=image_url,
    )
    session_profile = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface-profile", headers=auth_headers
    )
    assert session_profile.status_code == 200
    assert session_profile.json()["flow_identity"]["image_url"] == image_url

    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)
    embed_profile = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface-profile",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
    )
    assert embed_profile.status_code == 200
    assert embed_profile.json()["flow_identity"]["image_url"] == image_url
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers
    )
