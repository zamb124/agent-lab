"""
Строгие contract/e2e тесты OpenAI LLM proxy.

Инварианты: только MockLLM; реальный HTTP/DB; без monkeypatch LLMClient/resolve/Lara.
Schema validate против OpenRouter ChatRequest/ChatResult/ChatStreamChunk.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from core.ai.providers import HUMANITEC_LLM_AUTO_MODEL
from core.office.ai_settings import IMAGE_AUTO_MODEL_ID, LARA_DOCUMENTS_MODEL_ID
from core.types import JsonObject, require_json_object
from tests.agent._helpers import (
    AGENT_API_PREFIX,
    LLM_CHAT_COMPLETIONS_PATH,
    LLM_IMAGES_GENERATIONS_PATH,
    LLM_MODELS_PATH,
    LLM_ONLYOFFICE_PROXY_PATH,
    company_id_from_auth_token,
    ensure_company_public_flows,
    pair_and_register_device,
)
from tests.agent.contract.conftest import office_editor_bearer
from tests.agent.contract.openrouter_schemas import validate_against_openrouter_schema

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _seed_public_flows_for_contract_company(auth_token: str, di) -> AsyncIterator[None]:
    """Public flows (lara) в company токена — без чтения/фолбека на system."""
    await ensure_company_public_flows(company_id_from_auth_token(auth_token), di)
    yield


def _openai_error_type(status_code: int) -> str:
    if status_code == 401:
        return "authentication_error"
    if status_code == 403:
        return "permission_error"
    if status_code == 429:
        return "rate_limit_error"
    if status_code >= 500:
        return "api_error"
    return "invalid_request_error"


def _assert_openai_error_envelope(body: object, *, status_code: int, code: str) -> None:
    payload = require_json_object(body, "llm_proxy.error")
    error = require_json_object(payload.get("error"), "llm_proxy.error.error")
    assert isinstance(error.get("message"), str) and error["message"]
    assert error.get("type") == _openai_error_type(status_code)
    assert error.get("code") == code


def _parse_sse_chunks(text: str) -> list[JsonObject]:
    chunks: list[JsonObject] = []
    saw_done = False
    for line in text.splitlines():
        if line == "data: [DONE]":
            saw_done = True
            continue
        if not line.startswith("data: "):
            continue
        chunks.append(
            require_json_object(
                json.loads(line.removeprefix("data: ")),
                "llm_proxy.sse.chunk",
            )
        )
    assert saw_done, "SSE must end with data: [DONE]"
    return chunks


async def test_contract_models_openai_list_shape(
    flows_client_http: AsyncClient,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    flows_service: None,
    frontend_service: None,
) -> None:
    _ = flows_service, frontend_service
    _device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"contract-models-{unique_id}",
    )
    response = await flows_client_http.get(
        LLM_MODELS_PATH,
        headers={"Authorization": f"Bearer {device_token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["object"] == "list"
    assert isinstance(body["data"], list)
    model_ids = {item["id"] for item in body["data"] if isinstance(item, dict)}
    assert HUMANITEC_LLM_AUTO_MODEL in model_ids
    assert IMAGE_AUTO_MODEL_ID in model_ids
    assert LARA_DOCUMENTS_MODEL_ID in model_ids
    for item in body["data"]:
        assert isinstance(item, dict)
        assert item["object"] == "model"
        assert isinstance(item["id"], str) and item["id"]
        assert isinstance(item["created"], int)
        assert isinstance(item["owned_by"], str)


@pytest.mark.real_taskiq
async def test_contract_chat_completions_validates_chat_result(
    flows_client_http: AsyncClient,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    mock_llm_with_queue,
    flows_service: None,
    frontend_service: None,
) -> None:
    _ = flows_service, frontend_service
    await mock_llm_with_queue([{"type": "text", "content": "Contract hello"}])
    _device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"contract-chat-{unique_id}",
    )
    response = await flows_client_http.post(
        LLM_CHAT_COMPLETIONS_PATH,
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hello contract"}],
            "stream": False,
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 128,
            "seed": 42,
            # OR-only routing fields — must be ignored, not 422/500
            "provider": {"order": ["openai"]},
            "plugins": [{"id": "web"}],
            "models": ["ignored"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    validate_against_openrouter_schema("ChatResult", body)
    assert body["system_fingerprint"] is None
    assert body["choices"][0]["message"]["content"] == "Contract hello"


@pytest.mark.real_taskiq
async def test_contract_chat_request_multimodal_and_tools_accepted(
    flows_client_http: AsyncClient,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    mock_llm_with_queue,
    flows_service: None,
    frontend_service: None,
) -> None:
    _ = flows_service, frontend_service
    await mock_llm_with_queue([{"type": "text", "content": "tools ok"}])
    _device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"contract-tools-{unique_id}",
    )
    response = await flows_client_http.post(
        LLM_CHAT_COMPLETIONS_PATH,
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "model": "auto",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,AAAA"},
                        },
                    ],
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Lookup",
                        "parameters": {
                            "type": "object",
                            "properties": {"q": {"type": "string"}},
                        },
                    },
                }
            ],
            "tool_choice": "auto",
            "stream": False,
        },
    )
    assert response.status_code == 200, response.text
    validate_against_openrouter_schema("ChatResult", response.json())


@pytest.mark.real_taskiq
async def test_contract_sse_chunks_validate_chat_stream_chunk(
    flows_client_http: AsyncClient,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    mock_llm_with_queue,
    flows_service: None,
    frontend_service: None,
) -> None:
    _ = flows_service, frontend_service
    await mock_llm_with_queue([{"type": "text", "content": "Streamed contract"}])
    _device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"contract-sse-{unique_id}",
    )
    response = await flows_client_http.post(
        LLM_CHAT_COMPLETIONS_PATH,
        headers={"Authorization": f"Bearer {device_token}"},
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "stream please"}],
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    chunks = _parse_sse_chunks(response.text)
    assert chunks
    for chunk in chunks:
        validate_against_openrouter_schema("ChatStreamChunk", chunk)
        assert chunk["object"] == "chat.completion.chunk"


async def test_contract_auth_matrix_device_oo_invalid_revoked(
    flows_client_http: AsyncClient,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    flows_service: None,
    frontend_service: None,
) -> None:
    _ = flows_service, frontend_service

    invalid = await flows_client_http.get(
        LLM_MODELS_PATH,
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert invalid.status_code == 401
    _assert_openai_error_envelope(
        invalid.json(),
        status_code=401,
        code="llm_proxy_token_invalid",
    )

    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"contract-auth-{unique_id}",
    )
    device_ok = await flows_client_http.get(
        LLM_MODELS_PATH,
        headers={"Authorization": f"Bearer {device_token}"},
    )
    assert device_ok.status_code == 200

    oo_bearer = office_editor_bearer(auth_token=auth_token)
    oo_ok = await flows_client_http.get(
        LLM_MODELS_PATH,
        headers={"Authorization": f"Bearer {oo_bearer}"},
    )
    assert oo_ok.status_code == 200

    revoke = await agent_frontend_http_client.delete(f"{AGENT_API_PREFIX}/devices/{device_id}")
    assert revoke.status_code == 200
    assert revoke.json() == {"device_id": device_id, "revoked": True}
    revoked = await flows_client_http.get(
        LLM_MODELS_PATH,
        headers={"Authorization": f"Bearer {device_token}"},
    )
    assert revoked.status_code == 401
    _assert_openai_error_envelope(
        revoked.json(),
        status_code=401,
        code="device_token_revoked",
    )


async def test_contract_routing_unknown_lara_and_image_auto_on_chat(
    flows_client_http: AsyncClient,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    flows_service: None,
    frontend_service: None,
) -> None:
    _ = flows_service, frontend_service
    _device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"contract-route-{unique_id}",
    )
    headers = {"Authorization": f"Bearer {device_token}"}

    unknown_lara = await flows_client_http.post(
        LLM_CHAT_COMPLETIONS_PATH,
        headers=headers,
        json={
            "model": "lara:does_not_exist_branch",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert unknown_lara.status_code == 400
    _assert_openai_error_envelope(
        unknown_lara.json(),
        status_code=400,
        code="agent_llm_model_not_allowed",
    )

    image_on_chat = await flows_client_http.post(
        LLM_CHAT_COMPLETIONS_PATH,
        headers=headers,
        json={
            "model": IMAGE_AUTO_MODEL_ID,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert image_on_chat.status_code == 400
    _assert_openai_error_envelope(
        image_on_chat.json(),
        status_code=400,
        code="image_auto_wrong_endpoint",
    )

    images_wrong_model = await flows_client_http.post(
        LLM_IMAGES_GENERATIONS_PATH,
        headers=headers,
        json={"model": "auto", "prompt": "a cat"},
    )
    assert images_wrong_model.status_code == 400
    _assert_openai_error_envelope(
        images_wrong_model.json(),
        status_code=400,
        code="image_gen_model_invalid",
    )


async def test_contract_onlyoffice_proxy_unwrap_models(
    flows_client_http: AsyncClient,
    auth_token: str,
    flows_service: None,
    frontend_service: None,
) -> None:
    _ = flows_service, frontend_service
    oo_bearer = office_editor_bearer(auth_token=auth_token)
    response = await flows_client_http.post(
        LLM_ONLYOFFICE_PROXY_PATH,
        headers={"Authorization": f"Bearer {oo_bearer}"},
        json={
            "target": "http://localhost/flows/api/v1/agent/llm/v1/models",
            "method": "GET",
            "headers": {},
            "data": None,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["object"] == "list"
    model_ids = {item["id"] for item in body["data"] if isinstance(item, dict)}
    assert LARA_DOCUMENTS_MODEL_ID in model_ids
    assert HUMANITEC_LLM_AUTO_MODEL in model_ids


@pytest.mark.real_taskiq
async def test_contract_office_jwt_chat_completions(
    flows_client_http: AsyncClient,
    auth_token: str,
    unique_id: str,
    mock_llm_with_queue,
    flows_service: None,
    frontend_service: None,
) -> None:
    _ = flows_service, frontend_service, unique_id
    await mock_llm_with_queue([{"type": "text", "content": "OO chat ok"}])
    oo_bearer = office_editor_bearer(auth_token=auth_token)
    response = await flows_client_http.post(
        LLM_CHAT_COMPLETIONS_PATH,
        headers={"Authorization": f"Bearer {oo_bearer}"},
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hello from office"}],
            "stream": False,
        },
    )
    assert response.status_code == 200, response.text
    validate_against_openrouter_schema("ChatResult", response.json())
