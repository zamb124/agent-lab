"""E2E OpenAI LLM proxy через flows HTTP (editor JWT OnlyOffice)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx2 import AsyncClient

from core.ai.providers import HUMANITEC_LLM_AUTO_MODEL
from core.types import JsonObject, require_json_object
from tests.flows.llm_proxy._helpers import (
    LLM_CHAT_COMPLETIONS_PATH,
    LLM_MODELS_PATH,
    company_id_from_auth_token,
    ensure_company_public_flows,
)
from tests.flows.llm_proxy.contract.conftest import office_editor_bearer

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _seed_public_flows_for_llm_proxy_e2e(auth_token: str, di) -> AsyncIterator[None]:
    await ensure_company_public_flows(company_id_from_auth_token(auth_token), di)
    yield


async def test_e2e_llm_proxy_models_list_auto(
    flows_client_http: AsyncClient,
    auth_token: str,
    flows_service: None,
) -> None:
    _ = flows_service
    bearer = office_editor_bearer(auth_token=auth_token)
    response = await flows_client_http.get(
        LLM_MODELS_PATH,
        headers={"Authorization": f"Bearer {bearer}"},
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
    auth_token: str,
    mock_llm_redis,
    flows_service: None,
) -> None:
    _ = flows_service
    await mock_llm_redis([{"type": "text", "content": "Hello from MockLLM"}])
    bearer = office_editor_bearer(auth_token=auth_token)
    response = await flows_client_http.post(
        LLM_CHAT_COMPLETIONS_PATH,
        headers={"Authorization": f"Bearer {bearer}"},
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
    usage = body["usage"]
    assert isinstance(usage, dict)
    assert set(usage) >= {"prompt_tokens", "completion_tokens", "total_tokens"}
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    assert usage["cost"] == 0.0


@pytest.mark.real_taskiq
async def test_e2e_llm_proxy_chat_completions_stream(
    flows_client_http: AsyncClient,
    auth_token: str,
    mock_llm_redis,
    flows_service: None,
) -> None:
    _ = flows_service
    await mock_llm_redis([{"type": "text", "content": "Streamed hello"}])
    bearer = office_editor_bearer(auth_token=auth_token)
    response = await flows_client_http.post(
        LLM_CHAT_COMPLETIONS_PATH,
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "Hello from agent llm stream"}],
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    streamed_content = ""
    for line in text.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        chunk = require_json_object(json.loads(line.removeprefix("data: ")), "llm_proxy.sse.chunk")
        choices_raw = chunk.get("choices")
        if not isinstance(choices_raw, list):
            continue
        for choice_item in choices_raw:
            if not isinstance(choice_item, dict):
                continue
            choice = require_json_object(choice_item, "llm_proxy.sse.choice")
            delta_raw = choice.get("delta")
            if not isinstance(delta_raw, dict):
                continue
            delta: JsonObject = require_json_object(delta_raw, "llm_proxy.sse.delta")
            content = delta.get("content")
            if isinstance(content, str):
                streamed_content += content
    assert streamed_content == "Streamed hello"
    assert '"usage"' in text
    assert text.rstrip().endswith("data: [DONE]")


async def test_e2e_llm_proxy_requires_bearer(
    flows_client_http: AsyncClient,
    flows_service: None,
) -> None:
    _ = flows_service
    response = await flows_client_http.get(LLM_MODELS_PATH)
    assert response.status_code == 401

