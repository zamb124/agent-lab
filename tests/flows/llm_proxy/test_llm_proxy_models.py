"""Каталог моделей LLM proxy."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from a2a.types import (
    Artifact,
    Message,
    Part,
    TaskArtifactUpdateEvent,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.types.a2a_pb2 import ROLE_AGENT, TASK_STATE_COMPLETED

from apps.flows.config import get_settings
from apps.flows.di import FlowsDi
from apps.flows.src.llm_proxy.proxy import (
    OpenAIChatCompletionsRequest,
    OpenAIChatMessage,
    _build_usage_payload,
    _is_rate_limit_error,
    _llm_proxy_error_message,
    _llm_proxy_option_value,
    _resolve_llm_proxy_auto_mock_bridge,
    _resolve_llm_proxy_model,
    _stream_llm_proxy_sse,
    _validate_requested_llm_proxy_model,
    read_llm_proxy_model_ids,
)
from core.a2a import struct_from_mapping
from core.ai.models import AIModelRecord, ResolvedAIModel
from core.ai.providers import (
    LINNEX_LLM_AUTO_MODEL,
    LINNEX_LLM_PROVIDER,
    AICapability,
)
from core.websocket import WsCommandError
from tests.flows.llm_proxy._helpers import company_id_from_auth_token, ensure_company_public_flows


def test_llm_proxy_option_value_reads_string_and_json_object() -> None:
    assert _llm_proxy_option_value("auto") == LINNEX_LLM_AUTO_MODEL
    assert _llm_proxy_option_value({"value": "openrouter:qwen/qwen3-coder:free"}) == (
        "openrouter:qwen/qwen3-coder:free"
    )
    assert _llm_proxy_option_value({"label": "auto"}) is None


def test_validate_requested_agent_model_rejects_unknown_model() -> None:
    allowed = {LINNEX_LLM_AUTO_MODEL, "openrouter:qwen/qwen3-coder:free"}
    with pytest.raises(WsCommandError) as exc_info:
        _validate_requested_llm_proxy_model("anthropic:claude-3.5-sonnet", allowed)
    assert exc_info.value.code == "ws_invalid_payload"
    assert exc_info.value.error_code == "llm_proxy_model_not_allowed"


def test_validate_requested_agent_model_accepts_auto() -> None:
    allowed = {LINNEX_LLM_AUTO_MODEL}
    assert _validate_requested_llm_proxy_model("auto", allowed) == LINNEX_LLM_AUTO_MODEL


@pytest.mark.asyncio
async def test_read_llm_proxy_model_ids_uses_catalog_and_llm_models_service(
    di: FlowsDi,
    auth_token: str,
    unique_id: str,
) -> None:
    await ensure_company_public_flows(company_id_from_auth_token(auth_token), di)
    model_id = f"qwen-{unique_id}:free"
    catalog_record = AIModelRecord(
        provider="openrouter",
        model_id=model_id,
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
    )
    _ = await AIModelRecord.set(catalog_record)

    try:
        model_ids = await read_llm_proxy_model_ids(di.llm_models_service)
    finally:
        stored = await AIModelRecord.by_provider_and_model_id("openrouter", model_id)
        if stored is not None:
            _ = await stored.delete()

    assert model_ids[0] == LINNEX_LLM_AUTO_MODEL
    assert "image-auto" in model_ids
    assert "lara:documents" in model_ids
    assert f"openrouter:{model_id}" in model_ids


@pytest.mark.asyncio
async def test_read_llm_proxy_model_ids_falls_back_to_linnex_llm_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_models_service = MagicMock()
    llm_models_service.get_configured_providers_by_capability.return_value = [
        LINNEX_LLM_PROVIDER,
    ]
    llm_models_service.get_model_ids_by_provider_capability = AsyncMock(
        return_value=[
            {"value": LINNEX_LLM_AUTO_MODEL, "label": LINNEX_LLM_AUTO_MODEL},
            {"value": "groq:llama-3.1-8b-instant", "label": "groq / llama-3.1-8b-instant"},
        ],
    )
    monkeypatch.setattr(
        "apps.flows.src.llm_proxy.proxy.load_lara_branch_ids",
        AsyncMock(return_value=["documents"]),
    )

    model_ids = await read_llm_proxy_model_ids(llm_models_service)

    assert model_ids[0] == LINNEX_LLM_AUTO_MODEL
    assert "image-auto" in model_ids
    assert "lara:documents" in model_ids
    assert "groq:llama-3.1-8b-instant" in model_ids


def test_resolve_llm_proxy_model_auto_uses_linnex_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = ResolvedAIModel(
        capability=AICapability.LLM_CHAT,
        provider=LINNEX_LLM_PROVIDER,
        model=LINNEX_LLM_AUTO_MODEL,
        cost_origin="platform",
    )

    def fake_resolve_ai_model(
        capability: AICapability,
        selection: object | None = None,
        requirements: object | None = None,
        *,
        include_platform_default: bool = True,
    ) -> ResolvedAIModel | None:
        _ = capability, requirements, include_platform_default
        assert selection is not None
        assert getattr(selection, "provider") == LINNEX_LLM_PROVIDER
        assert getattr(selection, "model") == LINNEX_LLM_AUTO_MODEL
        return expected

    monkeypatch.setattr("apps.flows.src.llm_proxy.proxy.resolve_ai_model", fake_resolve_ai_model)
    resolved = _resolve_llm_proxy_model(LINNEX_LLM_AUTO_MODEL)
    assert resolved == expected


def test_resolve_llm_proxy_auto_mock_bridge_uses_mock_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = ResolvedAIModel(
        capability=AICapability.LLM_CHAT,
        provider="mock",
        model="mock-gpt-4",
        cost_origin="platform",
    )

    def fake_resolve_ai_model(
        capability: AICapability,
        selection: object | None = None,
        requirements: object | None = None,
        *,
        include_platform_default: bool = True,
    ) -> ResolvedAIModel | None:
        _ = capability, requirements, include_platform_default
        assert selection is not None
        assert getattr(selection, "provider") == "mock"
        assert getattr(selection, "model") == "mock-gpt-4"
        return expected

    monkeypatch.setattr("apps.flows.src.llm_proxy.proxy.resolve_ai_model", fake_resolve_ai_model)
    settings = get_settings()
    previous = settings.llm_proxy_use_mock_auto
    settings.llm_proxy_use_mock_auto = True
    try:
        bridged = _resolve_llm_proxy_auto_mock_bridge(LINNEX_LLM_AUTO_MODEL)
        assert bridged == expected
        resolved = _resolve_llm_proxy_model(LINNEX_LLM_AUTO_MODEL)
        assert resolved == expected
    finally:
        settings.llm_proxy_use_mock_auto = previous


def test_resolve_llm_proxy_model_provider_prefixed_uses_direct_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = ResolvedAIModel(
        capability=AICapability.LLM_CHAT,
        provider="openrouter",
        model="qwen/qwen3-coder:free",
        cost_origin="platform",
    )

    def fake_resolve_ai_model(
        capability: AICapability,
        selection: object | None = None,
        requirements: object | None = None,
        *,
        include_platform_default: bool = True,
    ) -> ResolvedAIModel | None:
        _ = capability, requirements, include_platform_default
        assert selection is not None
        assert getattr(selection, "provider") == "openrouter"
        assert getattr(selection, "model") == "qwen/qwen3-coder:free"
        return expected

    monkeypatch.setattr("apps.flows.src.llm_proxy.proxy.resolve_ai_model", fake_resolve_ai_model)
    resolved = _resolve_llm_proxy_model("openrouter:qwen/qwen3-coder:free")
    assert resolved == expected


def test_is_rate_limit_error_detects_429_and_cooldown() -> None:
    request = httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx2.Response(429, request=request)
    assert _is_rate_limit_error(
        httpx2.HTTPStatusError("429", request=request, response=response),
        provider="openrouter",
    )
    assert _is_rate_limit_error(
        RuntimeError("LLM stream: нет доступных model candidates"),
        provider="openrouter",
    )
    assert not _is_rate_limit_error(ValueError("weird"), provider="openrouter")
    ok_response = httpx2.Response(500, request=request)
    assert not _is_rate_limit_error(
        httpx2.HTTPStatusError("500", request=request, response=ok_response),
        provider="openrouter",
    )


def test_llm_proxy_error_message_rate_limit_and_generic() -> None:
    request = httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx2.Response(429, request=request)
    rate_limited = _llm_proxy_error_message(
        httpx2.HTTPStatusError("429", request=request, response=response),
        "openrouter:qwen/qwen3-coder:free",
        provider="openrouter",
    )
    assert "Превышен лимит запросов" in rate_limited
    assert "openrouter:qwen/qwen3-coder:free" in rate_limited
    generic = _llm_proxy_error_message(ValueError("weird"), "auto", provider="openrouter")
    assert "временно недоступна" in generic


def test_build_usage_payload_platform_includes_zero_cost() -> None:
    usage = _build_usage_payload(input_tokens=3, output_tokens=5, cost_origin="platform")
    assert usage == {
        "prompt_tokens": 3,
        "completion_tokens": 5,
        "total_tokens": 8,
        "cost": 0.0,
    }
    company_usage = _build_usage_payload(input_tokens=1, output_tokens=2, cost_origin="company")
    assert "cost" not in company_usage
    assert company_usage["total_tokens"] == 3


class _RateLimitedStreamLLM:
    llm_provider: str = "openrouter"

    async def stream(self, *args: object, **kwargs: object) -> AsyncIterator[object]:
        _ = args, kwargs
        request = httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        response = httpx2.Response(429, request=request)
        for _never in ():
            yield _never
        raise httpx2.HTTPStatusError("429 Too Many Requests", request=request, response=response)


def _rate_limited_client_factory(*args: object, **kwargs: object) -> _RateLimitedStreamLLM:
    _ = args, kwargs
    return _RateLimitedStreamLLM()


@pytest.mark.asyncio
async def test_stream_llm_proxy_sse_emits_rate_limit_error() -> None:
    body = OpenAIChatCompletionsRequest(
        model="openrouter:qwen/qwen3-coder:free",
        messages=[OpenAIChatMessage(role="user", content="hi")],
        stream=True,
    )
    chunks = [
        chunk
        async for chunk in _stream_llm_proxy_sse(
            body=body,
            llm=_rate_limited_client_factory(),
            response_model_id="openrouter:qwen/qwen3-coder:free",
        )
    ]
    text = b"".join(chunks).decode("utf-8")
    assert "Превышен лимит запросов" in text
    assert '"usage"' in text
    assert '"finish_reason": "stop"' in text
    assert "data: [DONE]" in text


class _RecordingStreamLLM:
    llm_provider: str = "openrouter"

    def __init__(self) -> None:
        self.captured_llm_context: object = "unset"

    async def stream(
        self,
        messages: object,
        *,
        tools: object = None,
        max_tokens: object = None,
        temperature: object = None,
        llm_context: object = None,
        **kwargs: object,
    ) -> AsyncIterator[object]:
        _ = messages, tools, max_tokens, temperature, kwargs
        self.captured_llm_context = llm_context
        yield TaskArtifactUpdateEvent(
            context_id="ctx-test",
            task_id="task-test",
            artifact=Artifact(
                artifact_id="artifact-test",
                parts=[Part(text="Hello from passthrough")],
            ),
            append=True,
            last_chunk=True,
        )
        done = Message(
            message_id="msg-test",
            role=ROLE_AGENT,
            parts=[Part(text="Hello from passthrough")],
        )
        done.metadata.CopyFrom(
            struct_from_mapping({"usage": {"input_tokens": 7, "output_tokens": 3}})
        )
        status = TaskStatus(state=TASK_STATE_COMPLETED)
        status.message.CopyFrom(done)
        yield TaskStatusUpdateEvent(
            context_id="ctx-test",
            task_id="task-test",
            status=status,
        )


@pytest.mark.asyncio
async def test_stream_llm_proxy_sse_does_not_run_platform_context_layer() -> None:
    recording_llm = _RecordingStreamLLM()
    body = OpenAIChatCompletionsRequest(
        model="openrouter:qwen/qwen3-coder:free",
        messages=[OpenAIChatMessage(role="user", content="hi")],
        stream=True,
    )
    chunks = [
        chunk
        async for chunk in _stream_llm_proxy_sse(
            body=body,
            llm=recording_llm,
            response_model_id="openrouter:qwen/qwen3-coder:free",
        )
    ]
    assert recording_llm.captured_llm_context is None
    text = b"".join(chunks).decode("utf-8")
    assert "Hello from passthrough" in text
    assert "временно недоступна" not in text
    assert '"prompt_tokens": 7' in text
    assert '"completion_tokens": 3' in text
    assert "data: [DONE]" in text
