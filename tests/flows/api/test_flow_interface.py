"""GET .../interface: design-time документ + viewer/capabilities для session и embed путей."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.flows.src.models import FlowConfig
from core.context import Context, clear_context, set_context
from core.flow_ui.document import (
    FlowUIAgentIdentity,
    FlowUIConversation,
    FlowUIDocument,
)
from core.flow_ui.schema import flow_ui_schema
from core.flow_ui.templates import default_chat_document
from core.models.identity_models import Company, User
from core.state.mutation_policy import FROZEN_STATE_FIELDS
from core.types import JsonObject

INTERFACE_KEYS = {
    "flow_id",
    "branch_id",
    "document",
    "viewer",
    "look",
    "capabilities",
    "flow_identity",
}


async def _create_embed(
    frontend_client: AsyncClient,
    auth_headers: dict[str, str],
    flow_id: str,
    *,
    assistant_title: str | None = None,
    conversation: JsonObject | None = None,
    start_page_id: str | None = None,
) -> str:
    body: JsonObject = {
        "name": "Embed interface",
        "flow_id": flow_id,
        "allowed_origins": ["https://larashved.ru"],
    }
    if assistant_title is not None:
        body["assistant_title"] = assistant_title
    if conversation is not None:
        body["conversation"] = conversation
    if start_page_id is not None:
        body["start_page_id"] = start_page_id
    response = await frontend_client.post(
        "/frontend/api/embed/configs", headers=auth_headers, json=body
    )
    assert response.status_code == 200, response.text
    return response.json()["embed_id"]


async def _embed_session_token(
    frontend_client: AsyncClient, auth_headers: dict[str, str], embed_id: str
) -> str:
    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200, token_response.text
    return token_response.json()["token"]


def _embed_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Origin": "https://larashved.ru"}


async def _set_interface(
    *, flow_id: str, company_id: str, user_id: str, document: FlowUIDocument,
    di,
) -> None:

    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    try:
        config = await FlowConfig.current_for_flow(flow_id)
        assert config is not None
        config.interface = document
        await FlowConfig.create_version(config)
    finally:
        clear_context()


def _chat_document(
    *, greeting: str = "", allow_cancel: bool = True, image_url: str = ""
) -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {
            "pages": [
                {
                    "page_id": "main",
                    "title": "Conversation",
                    "blocks": [
                        {
                            "type": "agent_identity",
                            "block_id": "agent-identity",
                            "image_url": image_url,
                        },
                        {
                            "type": "conversation",
                            "block_id": "conversation",
                            "settings": {
                                "greeting": greeting,
                                "allow_cancel": allow_cancel,
                                "show_files_panel": allow_cancel,
                                "allow_voice": allow_cancel,
                            },
                        },
                    ],
                }
            ],
            "start_page_id": "main",
        }
    )


def _conversation(document: FlowUIDocument) -> FlowUIConversation:
    for block in document.blocks():
        if isinstance(block, FlowUIConversation):
            return block
    raise AssertionError("conversation block missing")


@pytest.mark.asyncio
async def test_flow_interface_session_auth_defaults(flows_client: AsyncClient, embed_test_auth):
    auth_headers, flow_id, _, _ = embed_test_auth
    response = await flows_client.get(f"/flows/api/v1/{flow_id}/interface", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == INTERFACE_KEYS
    assert payload["flow_id"] == flow_id
    assert payload["branch_id"] == "default"
    assert payload["viewer"] == {
        "can_edit_flow": True,
        "can_interact": True,
        "can_share": True,
        "auth_mode": "platform",
    }
    assert payload["look"] is None
    assert payload["capabilities"] == {"cancel": True, "files": True, "voice": True}
    assert isinstance(payload["flow_identity"]["title"], str)
    assert payload["flow_identity"]["image_url"] is None
    document = FlowUIDocument.model_validate(payload["document"])
    assert document == default_chat_document()


@pytest.mark.asyncio
async def test_flow_interface_capabilities_follow_conversation_settings(
    flows_client: AsyncClient, embed_test_auth, di
):
    auth_headers, flow_id, company_id, user_id = embed_test_auth
    await _set_interface(
        flow_id=flow_id,
        company_id=company_id,
        user_id=user_id,
        document=_chat_document(greeting="Привет", allow_cancel=False),
    di=di)
    response = await flows_client.get(f"/flows/api/v1/{flow_id}/interface", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["capabilities"] == {"cancel": False, "files": False, "voice": False}
    document = FlowUIDocument.model_validate(payload["document"])
    assert _conversation(document).settings.greeting == "Привет"


@pytest.mark.asyncio
async def test_flow_interface_unknown_flow_403(
    flows_client: AsyncClient, embed_test_auth, unique_id
):
    auth_headers, _, _, _ = embed_test_auth
    response = await flows_client.get(
        f"/flows/api/v1/missing_flow_{unique_id}/interface", headers=auth_headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_flow_interface_branch_document_and_unknown_branch_404(
    flows_client: AsyncClient, embed_test_auth, unique_id,
    di,
):
    from apps.flows.src.models.flow_config import BranchConfig

    auth_headers, flow_id, company_id, user_id = embed_test_auth
    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    try:
        config = await FlowConfig.current_for_flow(flow_id)
        assert config is not None
        config.branches = {
            "support": BranchConfig(name="Support", interface=_chat_document(greeting="Support")),
            "sales": BranchConfig(name="Sales"),
        }
        await FlowConfig.create_version(config)
    finally:
        clear_context()

    own_document = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface", headers=auth_headers, params={"branch_id": "support"}
    )
    assert own_document.status_code == 200, own_document.text
    assert own_document.json()["branch_id"] == "support"
    support = FlowUIDocument.model_validate(own_document.json()["document"])
    assert _conversation(support).settings.greeting == "Support"

    inherited = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface", headers=auth_headers, params={"branch_id": "sales"}
    )
    assert inherited.status_code == 200, inherited.text
    assert FlowUIDocument.model_validate(inherited.json()["document"]) == default_chat_document()

    missing = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface",
        headers=auth_headers,
        params={"branch_id": f"missing_branch_{unique_id}"},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_embed_interface_with_embed_session_token(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id, assistant_title="Лара")
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface", headers=_embed_headers(embed_token)
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == INTERFACE_KEYS
    assert payload["flow_id"] == flow_id
    assert payload["viewer"] == {
        "can_edit_flow": False,
        "can_interact": True,
        "can_share": False,
        "auth_mode": "embed",
    }
    look = payload["look"]
    assert look is not None
    assert look["assistant_title"] == "Лара"
    assert look["theme"] == "dark"
    assert look["show_launcher"] is True
    assert FlowUIDocument.model_validate(payload["document"]) == default_chat_document()

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_interface_applies_conversation_override(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth, di
):
    auth_headers, flow_id, company_id, user_id = embed_test_auth
    await _set_interface(
        flow_id=flow_id,
        company_id=company_id,
        user_id=user_id,
        document=_chat_document(greeting="Flow greeting", allow_cancel=True),
    di=di)
    embed_id = await _create_embed(
        frontend_client,
        auth_headers,
        flow_id,
        conversation={
            "greeting": "Embed greeting",
            "allow_cancel": False,
            "show_files_panel": False,
        },
    )
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    embed_interface = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface", headers=_embed_headers(embed_token)
    )
    assert embed_interface.status_code == 200, embed_interface.text
    # voice для embed дополнительно ограничен look.voice_enabled (по умолчанию выключен).
    assert embed_interface.json()["capabilities"] == {
        "cancel": False,
        "files": False,
        "voice": False,
    }
    embed_document = FlowUIDocument.model_validate(embed_interface.json()["document"])
    assert _conversation(embed_document).settings.greeting == "Embed greeting"

    session_interface = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface", headers=auth_headers
    )
    assert session_interface.status_code == 200, session_interface.text
    assert session_interface.json()["capabilities"] == {
        "cancel": True,
        "files": True,
        "voice": True,
    }
    session_document = FlowUIDocument.model_validate(session_interface.json()["document"])
    assert _conversation(session_document).settings.greeting == "Flow greeting"

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_interface_rejects_wrong_origin(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface",
        headers={"Authorization": f"Bearer {embed_token}", "Origin": "https://evil.example"},
    )
    assert response.status_code == 403

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_interface_same_origin_get_without_origin_header(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    """Same-origin GET браузер шлёт без Origin: origin запроса — сам сервис (Host)."""
    auth_headers, flow_id, _, _ = embed_test_auth
    response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={"name": "Same-origin embed", "flow_id": flow_id, "allowed_origins": []},
    )
    assert response.status_code == 200, response.text
    embed_id = response.json()["embed_id"]
    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "http://humanitec.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200, token_response.text
    embed_token = token_response.json()["token"]

    same_origin = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface",
        headers={"Authorization": f"Bearer {embed_token}"},
    )
    assert same_origin.status_code == 200, same_origin.text
    foreign = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface",
        headers={"Authorization": f"Bearer {embed_token}", "Origin": "https://evil.example"},
    )
    assert foreign.status_code == 403

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_interface_rejects_foreign_embed_token(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    other_embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    other_token = await _embed_session_token(frontend_client, auth_headers, other_embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface", headers=_embed_headers(other_token)
    )
    assert response.status_code == 403

    for eid in (embed_id, other_embed_id):
        await frontend_client.delete(f"/frontend/api/embed/configs/{eid}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_interface_unknown_embed_404(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth, unique_id
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/missing_embed_{unique_id}/interface",
        headers=_embed_headers(embed_token),
    )
    assert response.status_code == 404

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


def test_embed_config_has_no_interface_behavior_fields():
    """EmbedConfig — identity/security/look плюс override беседы; поведение живёт в FlowConfig.interface."""
    from core.models.embed_models import EmbedConfig, EmbedInterfaceLook

    for field_name in ("show_reasoning", "show_tool_calls", "greeting_message"):
        assert field_name not in EmbedConfig.model_fields
        assert field_name not in EmbedInterfaceLook.model_fields
    assert {"conversation", "start_page_id"} <= set(EmbedConfig.model_fields)


@pytest.mark.asyncio
async def test_flow_identity_image_url_comes_from_agent_identity_block(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth,
    di,
):

    auth_headers, flow_id, company_id, user_id = embed_test_auth
    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    try:
        config = await FlowConfig.current_for_flow(flow_id)
        assert config is not None
        config.store_card_image_url = "https://cdn.example/store-card.png"
        await FlowConfig.create_version(config)
    finally:
        clear_context()
    store_only = await flows_client.get(f"/flows/api/v1/{flow_id}/interface", headers=auth_headers)
    assert store_only.status_code == 200, store_only.text
    assert store_only.json()["flow_identity"]["image_url"] is None

    image_url = "/flows/api/v1/files/download/agent-identity"
    await _set_interface(
        flow_id=flow_id,
        company_id=company_id,
        user_id=user_id,
        document=_chat_document(image_url=image_url),
    di=di)
    session_interface = await flows_client.get(
        f"/flows/api/v1/{flow_id}/interface", headers=auth_headers
    )
    assert session_interface.status_code == 200, session_interface.text
    assert session_interface.json()["flow_identity"]["image_url"] == image_url
    identity = next(
        block
        for block in FlowUIDocument.model_validate(session_interface.json()["document"]).blocks()
        if isinstance(block, FlowUIAgentIdentity)
    )
    assert identity.image_url == image_url

    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)
    embed_interface = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/interface", headers=_embed_headers(embed_token)
    )
    assert embed_interface.status_code == 200, embed_interface.text
    assert embed_interface.json()["flow_identity"]["image_url"] == image_url
    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_flow_ui_schema_and_templates(flows_client: AsyncClient, embed_test_auth):
    auth_headers, _, _, _ = embed_test_auth
    schema = await flows_client.get("/flows/api/v1/flow-ui/schema", headers=auth_headers)
    assert schema.status_code == 200, schema.text
    assert schema.json() == flow_ui_schema()
    assert schema.json()["x-flow-ui-frozen-state-fields"] == sorted(FROZEN_STATE_FIELDS)

    templates = await flows_client.get("/flows/api/v1/flow-ui/templates", headers=auth_headers)
    assert templates.status_code == 200, templates.text
    page = templates.json()
    assert set(page) == {"items", "total", "limit", "offset"}
    assert page["total"] == len(page["items"]) >= 1
    template_ids = [item["template_id"] for item in page["items"]]
    assert len(template_ids) == len(set(template_ids))
    for item in page["items"]:
        _ = FlowUIDocument.model_validate(item["document"])
