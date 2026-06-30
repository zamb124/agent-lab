"""Unit tests for HumanitecAgent LLM proxy model catalog."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from fastapi import HTTPException

from apps.agent.llm_proxy import (
    AgentOpenAIChatCompletionsRequest,
    AgentOpenAIChatMessage,
    _agent_llm_error_message,
    _agent_llm_option_value,
    _build_usage_payload,
    _is_rate_limit_error,
    _read_agent_llm_model_ids,
    _resolve_agent_llm_model,
    _stream_agent_llm_sse,
    _validate_requested_agent_model,
)
from core.ai.models import AIModelRecord, ResolvedAIModel
from core.ai.providers import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    AICapability,
)


def test_agent_llm_option_value_reads_string_and_json_object() -> None:
    assert _agent_llm_option_value("auto") == HUMANITEC_LLM_AUTO_MODEL
    assert _agent_llm_option_value({"value": "openrouter:qwen/qwen3-coder:free"}) == (
        "openrouter:qwen/qwen3-coder:free"
    )
    assert _agent_llm_option_value({"label": "auto"}) is None


def test_validate_requested_agent_model_rejects_unknown_model() -> None:
    allowed = {HUMANITEC_LLM_AUTO_MODEL, "openrouter:qwen/qwen3-coder:free"}
    with pytest.raises(HTTPException) as exc_info:
        _validate_requested_agent_model("anthropic:claude-3.5-sonnet", allowed)
    assert exc_info.value.status_code == 400


def test_validate_requested_agent_model_accepts_auto() -> None:
    allowed = {HUMANITEC_LLM_AUTO_MODEL}
    assert _validate_requested_agent_model("auto", allowed) == HUMANITEC_LLM_AUTO_MODEL


@pytest.mark.asyncio
async def test_read_agent_llm_model_ids_uses_catalog_and_llm_models_service() -> None:
    catalog_record = AIModelRecord(
        provider="openrouter",
        model_id="qwen/qwen3-coder:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
    )
    container = MagicMock()
    container.llm_models_service.get_configured_providers_by_capability.return_value = [
        HUMANITEC_LLM_PROVIDER,
        "openrouter",
    ]
    container.ai_model_catalog_repository.list_by_provider_capability = AsyncMock(
        return_value=[catalog_record],
    )
    container.llm_models_service.get_model_ids_by_provider_capability = AsyncMock(
        return_value=[],
    )

    model_ids = await _read_agent_llm_model_ids(container)

    assert model_ids[0] == HUMANITEC_LLM_AUTO_MODEL
    assert "openrouter:qwen/qwen3-coder:free" in model_ids
    container.llm_models_service.get_model_ids_by_provider_capability.assert_not_called()


@pytest.mark.asyncio
async def test_read_agent_llm_model_ids_falls_back_to_humanitec_llm_options() -> None:
    container = MagicMock()
    container.llm_models_service.get_configured_providers_by_capability.return_value = [
        HUMANITEC_LLM_PROVIDER,
    ]
    container.ai_model_catalog_repository.list_by_provider_capability = AsyncMock(
        return_value=[],
    )
    container.llm_models_service.get_model_ids_by_provider_capability = AsyncMock(
        return_value=[
            {"value": HUMANITEC_LLM_AUTO_MODEL, "label": HUMANITEC_LLM_AUTO_MODEL},
            {"value": "groq:llama-3.1-8b-instant", "label": "groq / llama-3.1-8b-instant"},
        ],
    )

    model_ids = await _read_agent_llm_model_ids(container)

    assert model_ids == [HUMANITEC_LLM_AUTO_MODEL, "groq:llama-3.1-8b-instant"]


def test_resolve_agent_llm_model_auto_uses_humanitec_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = ResolvedAIModel(
        capability=AICapability.LLM_CHAT,
        provider=HUMANITEC_LLM_PROVIDER,
        model=HUMANITEC_LLM_AUTO_MODEL,
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
        assert getattr(selection, "provider") == HUMANITEC_LLM_PROVIDER
        assert getattr(selection, "model") == HUMANITEC_LLM_AUTO_MODEL
        return expected

    monkeypatch.setattr("apps.agent.llm_proxy.resolve_ai_model", fake_resolve_ai_model)
    resolved = _resolve_agent_llm_model(HUMANITEC_LLM_AUTO_MODEL)
    assert resolved == expected


def test_resolve_agent_llm_model_provider_prefixed_uses_direct_provider(
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

    monkeypatch.setattr("apps.agent.llm_proxy.resolve_ai_model", fake_resolve_ai_model)
    resolved = _resolve_agent_llm_model("openrouter:qwen/qwen3-coder:free")
    assert resolved == expected


def test_is_rate_limit_error_detects_429_and_cooldown() -> None:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(429, request=request)
    assert _is_rate_limit_error(
        httpx.HTTPStatusError("429", request=request, response=response)
    )
    assert _is_rate_limit_error(RuntimeError("LLM stream: нет доступных model candidates"))
    assert not _is_rate_limit_error(ValueError("weird"))
    ok_response = httpx.Response(500, request=request)
    assert not _is_rate_limit_error(
        httpx.HTTPStatusError("500", request=request, response=ok_response)
    )


def test_agent_llm_error_message_rate_limit_and_generic() -> None:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(429, request=request)
    rate_limited = _agent_llm_error_message(
        httpx.HTTPStatusError("429", request=request, response=response),
        "openrouter:qwen/qwen3-coder:free",
    )
    assert "Превышен лимит запросов" in rate_limited
    assert "openrouter:qwen/qwen3-coder:free" in rate_limited
    generic = _agent_llm_error_message(ValueError("weird"), "auto")
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
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        response = httpx.Response(429, request=request)
        for _never in ():
            yield _never
        raise httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)


def _rate_limited_client_factory(*args: object, **kwargs: object) -> _RateLimitedStreamLLM:
    _ = args, kwargs
    return _RateLimitedStreamLLM()


@pytest.mark.asyncio
async def test_stream_agent_llm_sse_emits_rate_limit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.agent.llm_proxy.create_llm_client_from_ai_model",
        _rate_limited_client_factory,
    )
    resolved = ResolvedAIModel(
        capability=AICapability.LLM_CHAT,
        provider="openrouter",
        model="qwen/qwen3-coder:free",
        cost_origin="platform",
    )
    body = AgentOpenAIChatCompletionsRequest(
        model="openrouter:qwen/qwen3-coder:free",
        messages=[AgentOpenAIChatMessage(role="user", content="hi")],
        stream=True,
    )
    chunks = [
        chunk
        async for chunk in _stream_agent_llm_sse(
            body=body,
            resolved=resolved,
            allow_platform_paid_fallback=True,
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
                parts=[Part(root=TextPart(text="Hello from passthrough"))],
            ),
            append=True,
            last_chunk=True,
        )
        yield TaskStatusUpdateEvent(
            context_id="ctx-test",
            task_id="task-test",
            status=TaskStatus(
                state=TaskState.completed,
                message=Message(
                    message_id="msg-test",
                    role=Role.agent,
                    parts=[Part(root=TextPart(text="Hello from passthrough"))],
                    metadata={"usage": {"input_tokens": 7, "output_tokens": 3}},
                ),
            ),
            final=False,
        )


@pytest.mark.asyncio
async def test_stream_agent_llm_sse_does_not_run_platform_context_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recording_llm = _RecordingStreamLLM()

    def _recording_client_factory(*args: object, **kwargs: object) -> _RecordingStreamLLM:
        _ = args, kwargs
        return recording_llm

    monkeypatch.setattr(
        "apps.agent.llm_proxy.create_llm_client_from_ai_model",
        _recording_client_factory,
    )
    resolved = ResolvedAIModel(
        capability=AICapability.LLM_CHAT,
        provider="openrouter",
        model="qwen/qwen3-coder:free",
        cost_origin="platform",
    )
    body = AgentOpenAIChatCompletionsRequest(
        model="openrouter:qwen/qwen3-coder:free",
        messages=[AgentOpenAIChatMessage(role="user", content="hi")],
        stream=True,
    )
    chunks = [
        chunk
        async for chunk in _stream_agent_llm_sse(
            body=body,
            resolved=resolved,
            allow_platform_paid_fallback=True,
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
