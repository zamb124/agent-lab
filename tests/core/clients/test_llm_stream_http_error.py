"""Stream HTTP-ошибка LLM-транспорта: тело 400 читается, ResponseNotRead не подменяет статус."""

from __future__ import annotations

import httpx2
import pytest
from a2a.helpers.proto_helpers import new_text_message
from a2a.types import Role

from core.clients.llm.client import LLMClient
from core.clients.llm.transport import stream_once
from tests.core.http_proxy_helpers import install_mock_httpx_client, unread_json_response
from tests.fixtures.billing import make_test_billing_service


@pytest.mark.asyncio
async def test_stream_unread_http_400_raises_http_status_error_with_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HuggingFace-подобный stream 400: HTTPStatusError с телом, не ResponseNotRead."""
    error_body = (
        b'{"error":{"message":"The model nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4 '
        b'is too large to be loaded"}}'
    )

    def handler(request: httpx2.Request) -> httpx2.Response:
        return unread_json_response(request, 400, error_body)

    install_mock_httpx_client(monkeypatch, handler)
    monkeypatch.setattr("core.http.client._platform_proxy_active", lambda: True)

    client = LLMClient(
        billing_service=make_test_billing_service(),
        model="nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4",
        api_key="test-key",
        base_url="https://router.huggingface.co/v1",
        llm_provider="huggingface",
        timeout=5.0,
        first_token_timeout=5.0,
    )

    with pytest.raises(httpx2.HTTPStatusError) as exc_info:
        async for _event in stream_once(
            client,
            [new_text_message("ping", role=Role.ROLE_USER)],
        ):
            raise AssertionError("stream must fail before first event")

    http_error = exc_info.value
    assert http_error.response.status_code == 400
    assert "too large" in http_error.response.text
