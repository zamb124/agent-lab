"""Auth-матрица chat-profile: session-путь flow и embed_session-путь embed."""

import pytest
from httpx import AsyncClient

from core.context import Context, clear_context, set_context
from core.models.identity_models import Company, User


async def _create_embed(
    frontend_client: AsyncClient,
    auth_headers: dict[str, str],
    flow_id: str,
    *,
    assistant_title: str | None = None,
    chat_override: dict[str, object] | None = None,
) -> str:
    body: dict[str, object] = {
        "name": "Embed chat-profile",
        "flow_id": flow_id,
        "allowed_origins": ["https://larashved.ru"],
    }
    if assistant_title is not None:
        body["assistant_title"] = assistant_title
    if chat_override is not None:
        body["chat_override"] = chat_override
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


@pytest.mark.asyncio
async def test_flow_chat_profile_session_auth_defaults(flows_client: AsyncClient, embed_test_auth):
    auth_headers, flow_id, _, _ = embed_test_auth
    response = await flows_client.get(
        f"/flows/api/v1/{flow_id}/chat-profile", headers=auth_headers
    )
    assert response.status_code == 200
    profile = response.json()
    assert profile["flow_id"] == flow_id
    assert profile["branch_id"] == "default"
    assert profile["viewer"] == {"can_edit_flow": True}
    assert profile["look"] is None
    chat = profile["chat"]
    assert chat["show_reasoning"] is False
    assert chat["tool_calls_display"] == "compact"
    assert chat["errors_display"] == "generic"
    assert chat["show_run_trace"] is False
    assert chat["show_files_panel"] is True
    assert chat["allow_cancel"] is True
    assert chat["greeting_message"] is None
    assert chat["suggested_prompts"] == []


@pytest.mark.asyncio
async def test_flow_chat_profile_reflects_flow_chat_settings(
    flows_client: AsyncClient, embed_test_auth
):
    from apps.flows.src.container import get_container
    from apps.flows.src.models.flow_chat_settings import FlowChatSettings

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
        config.chat = FlowChatSettings(
            show_reasoning=True,
            tool_calls_display="detailed",
            errors_display="detailed",
            greeting_message="Привет из настроек",
            suggested_prompts=["Что ты умеешь?"],
        )
        await flows_container.flow_repository.set(config)
    finally:
        clear_context()

    response = await flows_client.get(
        f"/flows/api/v1/{flow_id}/chat-profile", headers=auth_headers
    )
    assert response.status_code == 200
    chat = response.json()["chat"]
    assert chat["show_reasoning"] is True
    assert chat["tool_calls_display"] == "detailed"
    assert chat["errors_display"] == "detailed"
    assert chat["greeting_message"] == "Привет из настроек"
    assert chat["suggested_prompts"] == ["Что ты умеешь?"]


@pytest.mark.asyncio
async def test_flow_chat_profile_unknown_flow_404(flows_client: AsyncClient, embed_test_auth, unique_id):
    auth_headers, _, _, _ = embed_test_auth
    response = await flows_client.get(
        f"/flows/api/v1/missing_flow_{unique_id}/chat-profile", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_flow_chat_profile_unknown_branch_404(flows_client: AsyncClient, embed_test_auth, unique_id):
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
        f"/flows/api/v1/{flow_id}/chat-profile",
        headers=auth_headers,
        params={"branch_id": "support"},
    )
    assert known_branch.status_code == 200
    assert known_branch.json()["branch_id"] == "support"

    response = await flows_client.get(
        f"/flows/api/v1/{flow_id}/chat-profile",
        headers=auth_headers,
        params={"branch_id": f"missing_branch_{unique_id}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_embed_chat_profile_embed_session_token(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(
        frontend_client, auth_headers, flow_id, assistant_title="Лара"
    )
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/chat-profile",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
    )
    assert response.status_code == 200
    profile = response.json()
    assert profile["flow_id"] == flow_id
    assert profile["viewer"] == {"can_edit_flow": False}
    look = profile["look"]
    assert look is not None
    assert look["assistant_title"] == "Лара"
    assert look["theme"] == "dark"
    assert look["show_launcher"] is True
    assert "chat" in profile

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_chat_profile_applies_chat_override(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    from apps.flows.src.container import get_container
    from apps.flows.src.models.flow_chat_settings import FlowChatSettings

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
        config.chat = FlowChatSettings(
            show_reasoning=False,
            tool_calls_display="compact",
            errors_display="generic",
            show_files_panel=True,
            greeting_message="Flow greeting",
        )
        await flows_container.flow_repository.set(config)
    finally:
        clear_context()

    embed_id = await _create_embed(
        frontend_client,
        auth_headers,
        flow_id,
        chat_override={"show_reasoning": True, "tool_calls_display": "hidden"},
    )
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/chat-profile",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
    )
    assert response.status_code == 200
    chat = response.json()["chat"]
    assert chat["show_reasoning"] is True
    assert chat["tool_calls_display"] == "hidden"
    assert chat["errors_display"] == "generic"
    assert chat["show_files_panel"] is True
    assert chat["greeting_message"] == "Flow greeting"

    session_response = await flows_client.get(
        f"/flows/api/v1/{flow_id}/chat-profile", headers=auth_headers
    )
    assert session_response.status_code == 200
    session_chat = session_response.json()["chat"]
    assert session_chat["show_reasoning"] is False
    assert session_chat["tool_calls_display"] == "compact"

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_chat_profile_rejects_wrong_origin(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/chat-profile",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://evil.example",
        },
    )
    assert response.status_code == 403

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_chat_profile_rejects_foreign_embed_token(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    other_embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    other_token = await _embed_session_token(frontend_client, auth_headers, other_embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/{embed_id}/chat-profile",
        headers={
            "Authorization": f"Bearer {other_token}",
            "Origin": "https://larashved.ru",
        },
    )
    assert response.status_code == 403

    for eid in (embed_id, other_embed_id):
        await frontend_client.delete(f"/frontend/api/embed/configs/{eid}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_chat_profile_unknown_embed_404(
    flows_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth, unique_id
):
    auth_headers, flow_id, _, _ = embed_test_auth
    embed_id = await _create_embed(frontend_client, auth_headers, flow_id)
    embed_token = await _embed_session_token(frontend_client, auth_headers, embed_id)

    response = await flows_client.get(
        f"/flows/api/v1/embed/missing_embed_{unique_id}/chat-profile",
        headers={
            "Authorization": f"Bearer {embed_token}",
            "Origin": "https://larashved.ru",
        },
    )
    assert response.status_code == 404

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


def test_embed_config_has_no_chat_behavior_fields():
    """EmbedConfig — идентичность/безопасность/look&feel; политика поведения — FlowConfig.chat."""
    from core.models.embed_models import EmbedChatLook, EmbedConfig

    for field_name in ("show_reasoning", "show_tool_calls", "greeting_message"):
        assert field_name not in EmbedConfig.model_fields
        assert field_name not in EmbedChatLook.model_fields
