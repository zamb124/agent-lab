"""Контракт ``ChatLitAPI.decode_request`` с телом от LitServe."""

import pytest
from fastapi import Request

from apps.provider_litserve.llm.api import ChatLitAPI
from apps.provider_litserve.openai_server_contracts import OpenAIChatCompletionsRequest
from core.config.models import ProviderLitserveInfraConfig

pytestmark = pytest.mark.timeout(15)


def test_chat_lit_api_decode_request_accepts_litserve_prepared_dict() -> None:
    api = ChatLitAPI(ProviderLitserveInfraConfig())
    body = {
        "model": "qwen/qwen2.5-1.5b-instruct-crawl",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.0,
        "max_tokens": 32,
    }
    parsed = api.decode_request(body)  # type: ignore[arg-type]
    assert isinstance(parsed, OpenAIChatCompletionsRequest)
    assert parsed.model == "qwen/qwen2.5-1.5b-instruct-crawl"
    assert parsed.messages[0].content == "hello"


def test_chat_lit_api_decode_request_rejects_raw_fastapi_request() -> None:
    api = ChatLitAPI(ProviderLitserveInfraConfig())
    with pytest.raises(Exception, match="LitServe должен передать подготовленное тело"):
        _ = api.decode_request(Request(scope={"type": "http"}))
