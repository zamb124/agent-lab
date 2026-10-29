from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

import pytest
from httpx2 import AsyncClient

from core.capabilities import (
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from tests.flows.llm_proxy._helpers import (
    FLOWS_HTTP_BASE,
    LLM_CHAT_COMPLETIONS_PATH,
    LLM_MODELS_PATH,
    company_id_from_auth_token,
    user_id_from_auth_token,
)

pytestmark = pytest.mark.asyncio


def _execution_bearer(
    *,
    user_id: str | None,
    company_id: str,
    unique_id: str,
    test_scope: str | None = None,
) -> str:
    claims = CapabilityExecutionTokenClaims(
        company_id=company_id,
        user_id=user_id,
        flow_id=f"flow_guest_llm_{unique_id}",
        branch_id="default",
        session_id=f"sess_guest_llm_{unique_id}",
        task_id=f"task_guest_llm_{unique_id}",
        context_id=f"ctx_guest_llm_{unique_id}",
        channel="guest_llm",
        request_id=f"req_guest_llm_{unique_id}",
        source_node_id=f"code_agent_{unique_id}",
        namespace="default",
        test_scope=test_scope,
        exp=execution_token_exp(120),
    )
    return issue_execution_token(claims)


async def test_llm_proxy_execution_token_lists_models(
    flows_client: AsyncClient,
    auth_token_system: str,
    unique_id: str,
) -> None:
    bearer = _execution_bearer(
        user_id=user_id_from_auth_token(auth_token_system),
        company_id=company_id_from_auth_token(auth_token_system),
        unique_id=unique_id,
    )
    assert len(bearer.split(".")) == 2
    response = await flows_client.get(
        LLM_MODELS_PATH,
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert response.status_code == 200, response.text


async def test_llm_proxy_execution_token_without_user_id_401(
    flows_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    bearer = _execution_bearer(
        user_id=None,
        company_id=company_id_from_auth_token(auth_token),
        unique_id=unique_id,
    )
    response = await flows_client.get(
        LLM_MODELS_PATH,
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert response.status_code == 401


async def test_llm_proxy_invalid_execution_token_401(flows_client: AsyncClient) -> None:
    response = await flows_client.get(
        LLM_MODELS_PATH,
        headers={"Authorization": "Bearer not-a.token"},
    )
    assert response.status_code == 401


async def test_llm_proxy_execution_token_test_scope_without_header(
    flows_service: object,
    auth_token_system: str,
    unique_id: str,
    platform_test_scope: str,
    mock_llm_redis,
) -> None:
    _ = flows_service
    content = f"token-scope-{unique_id}"
    await mock_llm_redis([{"type": "text", "content": content}])
    bearer = _execution_bearer(
        user_id=user_id_from_auth_token(auth_token_system),
        company_id=company_id_from_auth_token(auth_token_system),
        unique_id=unique_id,
        test_scope=platform_test_scope,
    )
    url = f"{FLOWS_HTTP_BASE}{LLM_CHAT_COMPLETIONS_PATH}"
    body = json.dumps(
        {
            "model": "auto",
            "messages": [{"role": "user", "content": f"ping-{unique_id}"}],
            "stream": False,
        }
    ).encode("utf-8")

    def _post() -> tuple[int, bytes]:
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AssertionError(f"llm proxy HTTP {exc.code}: {detail}") from exc

    status, raw = await asyncio.to_thread(_post)
    assert status == 200
    payload = json.loads(raw.decode("utf-8"))
    choices = payload["choices"]
    message = choices[0]["message"]
    assert message["content"] == content
