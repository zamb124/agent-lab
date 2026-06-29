"""E2E LLM proxy HumanitecAgent через flows HTTP."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.ai.providers import HUMANITEC_LLM_AUTO_MODEL
from tests.agent._helpers import (
    AGENT_API_PREFIX,
    LLM_CHAT_COMPLETIONS_PATH,
    LLM_MODELS_PATH,
    pair_and_register_device,
)

pytestmark = pytest.mark.asyncio


async def test_e2e_llm_proxy_models_list_auto(
    flows_client_http: AsyncClient,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    flows_service: None,
) -> None:
    _ = flows_service
    _device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    response = await flows_client_http.get(
        LLM_MODELS_PATH,
        headers={"Authorization": f"Bearer {device_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    model_ids = {item["id"] for item in body["data"] if isinstance(item, dict)}
    assert HUMANITEC_LLM_AUTO_MODEL in model_ids
    assert all(isinstance(model_id, str) and model_id for model_id in model_ids)


@pytest.mark.real_taskiq
async def test_e2e_llm_proxy_chat_completions(
    flows_client_http: AsyncClient,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    mock_llm_with_queue,
    flows_service: None,
) -> None:
    _ = flows_service
    await mock_llm_with_queue([{"type": "text", "content": "Hello from MockLLM"}])
    _device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"llm-chat-{unique_id}",
    )
    response = await flows_client_http.post(
        LLM_CHAT_COMPLETIONS_PATH,
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "Hello from agent llm proxy"}],
            "stream": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    choices = body["choices"]
    assert isinstance(choices, list) and choices
    message = choices[0]["message"]
    assert isinstance(message, dict)
    assert isinstance(message.get("content"), str)
    assert message["content"].strip()


async def test_e2e_llm_proxy_requires_device_bearer(
    flows_client_http: AsyncClient,
    flows_service: None,
) -> None:
    _ = flows_service
    response = await flows_client_http.get(LLM_MODELS_PATH)
    assert response.status_code == 401


async def test_e2e_llm_proxy_revoked_device_returns_401(
    flows_client_http: AsyncClient,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    flows_service: None,
) -> None:
    _ = flows_service
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"llm-revoke-{unique_id}",
    )
    revoke_response = await agent_frontend_http_client.delete(
        f"{AGENT_API_PREFIX}/devices/{device_id}",
    )
    assert revoke_response.status_code == 204
    response = await flows_client_http.get(
        LLM_MODELS_PATH,
        headers={"Authorization": f"Bearer {device_token}"},
    )
    assert response.status_code == 401
