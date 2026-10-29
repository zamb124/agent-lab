"""Интеграционное покрытие fallback кандидатов LLMClient.

Эти тесты намеренно проходят через реальный путь httpx2/OpenAI-compatible.
Локальный сервер ниже — маленький детерминированный endpoint, а не патченный клиент.

Короткие first_token_timeout используются только там, где таймаут ДОЛЖЕН
сработать (проверка fallback) — parallel-safe под xdist без сериализации.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any, Callable

import httpx2
import pytest
from a2a.helpers.proto_helpers import get_message_text
from a2a.types import (
    Message,
    Part,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from a2a.types.a2a_pb2 import (
    ROLE_USER,
)

from core.ai.llm_config import LLMCallConfig
from core.ai.providers import HUMANITEC_LLM_AUTO_MODEL, HUMANITEC_LLM_PROVIDER
from core.ai.runtime import should_use_platform_default_free_pool
from core.clients.llm.client import LLMClient
from core.clients.llm.runtime import create_llm_transport_client as create_transport_llm_client
from core.config import BaseSettings, get_settings, set_settings
from core.config.models import (
    LLMConfig,
    ModelConfig,
    OpenAIProviderConfig,
    OpenRouterProviderConfig,
    PlatformFreePoolConfig,
    PlatformFreePoolPaidFallbackConfig,
)
from core.llm_context import LLMContextBudget, LLMContextProfile, LLMContextRetrievalPolicy


@dataclass(frozen=True)
class _RequestRecord:
    model: str
    headers: dict[str, str]
    body: dict[str, Any]


class _OpenAICompatibleTestServer:
    def __init__(self, handlers: dict[str, Callable[[asyncio.StreamWriter], Any]]) -> None:
        self._handlers = handlers
        self._server: asyncio.AbstractServer | None = None
        self.requests: list[_RequestRecord] = []

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("server is not started")
        socket = self._server.sockets[0]
        host, port = socket.getsockname()[:2]
        return f"http://{host}:{port}/v1"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            header_bytes = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=1.0)
            header_text = header_bytes.decode("latin-1")
            lines = header_text.split("\r\n")
            headers: dict[str, str] = {}
            for line in lines[1:]:
                if not line or ":" not in line:
                    continue
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
            body_bytes = await reader.readexactly(int(headers.get("content-length", "0")))
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            model = str(body.get("model") or "")
            self.requests.append(_RequestRecord(model=model, headers=headers, body=body))
            handler = self._handlers.get(model)
            if handler is None:
                await _write_json_response(writer, 404, {"error": f"unexpected model {model}"})
                return
            await handler(writer)
        except (asyncio.IncompleteReadError, ConnectionError, BrokenPipeError):
            return
        finally:
            writer.close()
            with suppress(ConnectionError, BrokenPipeError):
                await writer.wait_closed()


async def _write_json_response(
    writer: asyncio.StreamWriter,
    status: int,
    payload: dict[str, Any],
) -> None:
    reason = "OK" if status == 200 else "Internal Server Error"
    body = json.dumps(payload).encode("utf-8")
    writer.write(
        (
            f"HTTP/1.1 {status} {reason}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        + body
    )
    await writer.drain()


async def _write_sse_headers(writer: asyncio.StreamWriter) -> None:
    writer.write(
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/event-stream\r\n"
        b"Cache-Control: no-cache\r\n"
        b"Connection: close\r\n"
        b"\r\n"
    )
    await writer.drain()


async def _write_sse_data(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
    writer.write(f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode("utf-8"))
    await writer.drain()


async def _write_sse_text(
    writer: asyncio.StreamWriter,
    text: str,
    *,
    delay_before_first_chunk: float = 0.0,
) -> None:
    await _write_sse_headers(writer)
    if delay_before_first_chunk:
        await asyncio.sleep(delay_before_first_chunk)
    await _write_sse_data(
        writer,
        {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
        },
    )
    await _write_sse_data(
        writer,
        {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )
    writer.write(b"data: [DONE]\n\n")
    await writer.drain()


async def _write_invalid_json_after_first_chunk(writer: asyncio.StreamWriter) -> None:
    await _write_sse_headers(writer)
    await _write_sse_data(
        writer,
        {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"content": "partial"}, "finish_reason": None}],
        },
    )
    writer.write(b"data: {not-json}\n\n")
    await writer.drain()


def _message(text: str) -> Message:
    return Message(
        message_id="test-user-message",
        role=ROLE_USER,
        parts=[Part(text=text)],
    )


def _candidate(
    model: str,
    *,
    base_url: str,
    provider: str = "openai",
    supported_parameters: frozenset[str] = frozenset(),
    source: str = "test",
    context_length: int | None = None,
    input_modalities: frozenset[str] = frozenset({"text"}),
) -> LLMCallConfig:
    return LLMCallConfig(
        provider=provider,
        model=model,
        api_key="test-key",
        base_url=base_url,
        source=source,
        supported_parameters=supported_parameters,
        input_modalities=input_modalities,
        output_modalities=frozenset({"text"}),
        context_length=context_length,
    )


def _client_for(server: _OpenAICompatibleTestServer, candidates: list[LLMCallConfig]) -> LLMClient:
    return LLMClient(
        model=candidates[0].model,
        api_key=candidates[0].api_key,
        base_url=candidates[0].base_url,
        llm_provider=candidates[0].provider,
        candidates=candidates,
        first_token_timeout=0.5,
        candidate_cooldown_seconds=0.0,
        timeout=5.0,
    )


def _context_profile() -> LLMContextProfile:
    return LLMContextProfile(
        mode="window",
        budget=LLMContextBudget(
            max_input_tokens=200,
            output_reserve_tokens=2,
            reasoning_reserve_tokens=0,
            safety_buffer_tokens=1,
            active_window_tokens=160,
            memory_tokens=10,
            rag_tokens=10,
            tool_result_tokens=8,
        ),
        memory="off",
        retrieval=LLMContextRetrievalPolicy(mode="off", rerank=False),
        compaction="auto",
        cache="auto",
    )


@contextmanager
def _production_llm_env():
    old_testing = os.environ.get("TESTING")
    old_pytest_current = os.environ.pop("PYTEST_CURRENT_TEST", None)
    os.environ["TESTING"] = "false"
    try:
        yield
    finally:
        if old_testing is None:
            os.environ.pop("TESTING", None)
        else:
            os.environ["TESTING"] = old_testing
        if old_pytest_current is not None:
            os.environ["PYTEST_CURRENT_TEST"] = old_pytest_current


@pytest.mark.asyncio
async def test_stream_falls_back_when_primary_has_no_first_token(unique_id: str) -> None:
    primary_model = f"primary-slow-{unique_id}"
    fallback_model = f"fallback-fast-{unique_id}"
    server = _OpenAICompatibleTestServer(
        {
            primary_model: lambda writer: _write_sse_text(
                writer,
                "too-late",
                delay_before_first_chunk=2.0,
            ),
            fallback_model: lambda writer: _write_sse_text(writer, "fallback-ok"),
        }
    )
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate(primary_model, base_url=server.base_url),
                _candidate(fallback_model, base_url=server.base_url),
            ],
        )

        message = await client.chat([_message("hello")])

        assert get_message_text(message) == "fallback-ok"
        assert [request.model for request in server.requests] == [
            primary_model,
            fallback_model,
        ]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_chat_model_override_uses_requested_model_for_single_call() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "override-model": lambda writer: _write_sse_text(writer, "override-ok"),
        }
    )
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate("primary-model", base_url=server.base_url),
                _candidate("fallback-model", base_url=server.base_url),
            ],
        )

        message = await client.chat([_message("hello")], model="override-model")

        assert get_message_text(message) == "override-ok"
        assert [request.model for request in server.requests] == ["override-model"]
        assert client.model == "primary-model"
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_stream_status_metadata_uses_resolved_candidate_model_provider_and_source() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "primary-500": lambda writer: _write_json_response(writer, 500, {"error": "boom"}),
            "fallback-fast": lambda writer: _write_sse_text(writer, "fallback-ok"),
        }
    )
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate("primary-500", base_url=server.base_url, source="primary-source"),
                _candidate("fallback-fast", base_url=server.base_url, source="fallback-source"),
            ],
        )

        events = []
        async for event in client.stream([_message("hello")]):
            events.append(event)

        status_events = [event for event in events if isinstance(event, TaskStatusUpdateEvent)]
        final_metadata = status_events[-1].status.message.metadata
        assert final_metadata["model"] == "fallback-fast"
        assert final_metadata["provider"] == "openai"
        assert final_metadata["source"] == "fallback-source"
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_stream_context_layer_clamps_to_candidate_context_length_and_reports_metadata() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "small-context": lambda writer: _write_sse_text(writer, "ok"),
        }
    )
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate(
                    "small-context",
                    base_url=server.base_url,
                    context_length=32,
                ),
            ],
        )
        messages = [
            Message(
                message_id="system-message",
                role=ROLE_USER,
                parts=[Part(text="strict rules")],
                metadata={"system": True},
            ),
            _message(" ".join(f"old{i}" for i in range(160))),
            _message("current"),
        ]

        events = []
        async for event in client.stream(messages, llm_context=_context_profile()):
            events.append(event)

        body_messages = server.requests[0].body["messages"]
        assert body_messages == [
            {"role": "system", "content": "strict rules"},
            {"role": "user", "content": "current"},
        ]
        status_events = [event for event in events if isinstance(event, TaskStatusUpdateEvent)]
        final_metadata = status_events[-1].status.message.metadata
        llm_context = final_metadata["llm_context"]
        assert llm_context["usage"]["max_input_tokens"] == 32
        assert llm_context["usage"]["model_context_length"] == 32
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_stream_context_layer_adds_openrouter_anthropic_cache_control() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "anthropic/claude-sonnet-4.5": lambda writer: _write_sse_text(writer, "ok"),
        }
    )
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate(
                    "anthropic/claude-sonnet-4.5",
                    provider="openrouter",
                    base_url=server.base_url,
                ),
            ],
        )
        messages = [
            Message(
                message_id="system-message",
                role=ROLE_USER,
                parts=[Part(text="stable rules")],
                metadata={"system": True},
            ),
            _message("current"),
        ]

        events = []
        async for event in client.stream(messages, llm_context=_context_profile()):
            events.append(event)

        assert events
        assert server.requests[0].body["cache_control"] == {"type": "ephemeral"}
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_fallback_candidate_uses_its_own_full_llm_config() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "primary-500": lambda writer: _write_json_response(writer, 500, {"error": "boom"}),
            "fallback-configured": lambda writer: _write_sse_text(writer, "fallback-ok"),
        }
    )
    await server.start()
    try:
        primary = _candidate("primary-500", base_url=server.base_url).model_copy(
            update={
                "temperature": 0.1,
                "top_p": 0.2,
                "max_tokens": 100,
                "extra_request_body": {"route": "primary"},
                "extra_request_headers": {"X-Route": "primary"},
            }
        )
        fallback = _candidate("fallback-configured", base_url=server.base_url).model_copy(
            update={
                "temperature": 0.8,
                "top_p": 0.9,
                "top_k": 40,
                "max_tokens": 512,
                "frequency_penalty": 0.4,
                "presence_penalty": 0.5,
                "seed": 42,
                "reasoning_effort": "low",
                "extra_request_body": {"route": "fallback"},
                "extra_request_headers": {"X-Route": "fallback"},
            }
        )
        client = _client_for(server, [primary, fallback])

        message = await client.chat([_message("hello")])

        assert get_message_text(message) == "fallback-ok"
        assert [request.model for request in server.requests] == [
            "primary-500",
            "fallback-configured",
        ]
        assert server.requests[0].body["temperature"] == 0.1
        assert server.requests[0].body["top_p"] == 0.2
        assert server.requests[0].body["max_tokens"] == 100
        assert server.requests[0].body["route"] == "primary"
        assert server.requests[0].headers["x-route"] == "primary"
        assert server.requests[1].body["temperature"] == 0.8
        assert server.requests[1].body["top_p"] == 0.9
        assert server.requests[1].body["top_k"] == 40
        assert server.requests[1].body["max_tokens"] == 512
        assert server.requests[1].body["frequency_penalty"] == 0.4
        assert server.requests[1].body["presence_penalty"] == 0.5
        assert server.requests[1].body["seed"] == 42
        assert server.requests[1].body["reasoning_effort"] == "low"
        assert server.requests[1].body["route"] == "fallback"
        assert server.requests[1].headers["x-route"] == "fallback"
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_primary_extra_request_config_does_not_bleed_into_fallback() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "primary-500": lambda writer: _write_json_response(writer, 500, {"error": "boom"}),
            "fallback-clean": lambda writer: _write_sse_text(writer, "fallback-ok"),
        }
    )
    await server.start()
    try:
        primary = _candidate("primary-500", base_url=server.base_url).model_copy(
            update={
                "extra_request_body": {"primary_only": True},
                "extra_request_headers": {"X-Primary-Only": "1"},
            }
        )
        fallback = _candidate("fallback-clean", base_url=server.base_url)
        client = _client_for(server, [primary, fallback])

        message = await client.chat([_message("hello")])

        assert get_message_text(message) == "fallback-ok"
        assert server.requests[0].body["primary_only"] is True
        assert server.requests[0].headers["x-primary-only"] == "1"
        assert "primary_only" not in server.requests[1].body
        assert "x-primary-only" not in server.requests[1].headers
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_stream_does_not_fallback_after_first_chunk_is_emitted() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "primary-breaks-after-first": _write_invalid_json_after_first_chunk,
            "fallback-must-not-run": lambda writer: _write_sse_text(writer, "unexpected"),
        }
    )
    stream = None
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate("primary-breaks-after-first", base_url=server.base_url),
                _candidate("fallback-must-not-run", base_url=server.base_url),
            ],
        )

        stream = client.stream([_message("hello")])
        first_event = await stream.__anext__()
        assert isinstance(first_event, TaskArtifactUpdateEvent)

        with pytest.raises(ValueError, match="llm.stream.chunk"):
            await stream.__anext__()

        assert [request.model for request in server.requests] == ["primary-breaks-after-first"]
    finally:
        if stream is not None:
            with suppress(Exception):
                await stream.aclose()
        await server.close()


@pytest.mark.asyncio
async def test_stream_skips_candidate_that_cannot_handle_tools() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "primary-no-tools": lambda writer: _write_sse_text(writer, "unexpected"),
            "fallback-with-tools": lambda writer: _write_sse_text(writer, "tools-ok"),
        }
    )
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate(
                    "primary-no-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"temperature"}),
                ),
                _candidate(
                    "fallback-with-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"temperature", "tools"}),
                ),
            ],
        )

        message = await client.chat(
            [_message("hello")],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Lookup something",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        )

        assert get_message_text(message) == "tools-ok"
        assert [request.model for request in server.requests] == ["fallback-with-tools"]
        assert "tools" in server.requests[0].body
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_platform_free_candidate_requires_explicit_tool_support() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "free-no-metadata": lambda writer: _write_sse_text(writer, "unexpected"),
            "free-with-tools": lambda writer: _write_sse_text(writer, "tools-ok"),
        }
    )
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate(
                    "free-no-metadata",
                    base_url=server.base_url,
                    supported_parameters=frozenset(),
                    source="platform_free",
                ),
                _candidate(
                    "free-with-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"tools"}),
                    source="platform_free",
                ),
            ],
        )

        message = await client.chat(
            [_message("hello")],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Lookup something",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        )

        assert get_message_text(message) == "tools-ok"
        assert [request.model for request in server.requests] == ["free-with-tools"]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_platform_free_pool_raises_when_no_candidate_supports_tools() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "free-no-tools": lambda writer: _write_sse_text(writer, "unexpected"),
        }
    )
    await server.start()
    try:
        candidate = _candidate(
            "free-no-tools",
            base_url=server.base_url,
            supported_parameters=frozenset({"temperature"}),
            source="platform_free",
        )
        client = LLMClient(
            model=str(candidate.model),
            api_key=str(candidate.api_key),
            base_url=candidate.base_url,
            llm_provider=candidate.provider,
            candidates=[candidate],
            first_token_timeout=0.05,
            candidate_cooldown_seconds=0.0,
            timeout=2.0,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=False,
        )

        with pytest.raises(RuntimeError, match="compatible with request parameters"):
            await client.chat(
                [_message("hello")],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "lookup",
                            "description": "Lookup something",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )

        assert server.requests == []
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_invoke_uses_same_ordered_candidate_fallback() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "primary-500": lambda writer: _write_json_response(
                writer,
                500,
                {"error": "primary failed"},
            ),
            "fallback-json": lambda writer: _write_json_response(
                writer,
                200,
                {"choices": [{"message": {"content": "invoke-ok"}}]},
            ),
        }
    )
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate("primary-500", base_url=server.base_url),
                _candidate("fallback-json", base_url=server.base_url),
            ],
        )

        result = await client.invoke([_message("hello")])

        assert result == "invoke-ok"
        assert [request.model for request in server.requests] == ["primary-500", "fallback-json"]
    finally:
        await server.close()


def test_create_transport_llm_client_builds_explicit_fallback_candidates_from_real_settings() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider="openrouter",
            default_strategy="configured",
            default_model="openrouter/default",
            temperature=0.2,
            max_tokens=4096,
            timeout=10.0,
            models={
                "openrouter/primary": ModelConfig(context_length=65_536),
            },
            openrouter=OpenRouterProviderConfig(
                api_key="sk-openrouter",
                base_url="https://openrouter.ai/api/v1",
                site_url="https://platform.example",
                site_name="Platform Test",
            ),
            openai=OpenAIProviderConfig(
                api_key="sk-openai",
                base_url="https://api.openai.example/v1",
            ),
            platform_free_pool=PlatformFreePoolConfig(
                enabled=True,
                first_token_timeout_seconds=12.0,
                candidate_cooldown_seconds=3.0,
            ),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = create_transport_llm_client(
                model_name="openrouter/primary",
                fallback_models=[
                    {
                        "model": "openrouter/fallback",
                        "temperature": 0.7,
                        "extra_request_body": {"route": "openrouter-fallback"},
                    },
                    {
                        "model": "openai:gpt-4o-mini",
                        "base_url": "https://api.openai.example/v1",
                        "top_p": 0.8,
                        "extra_request_headers": {"X-Fallback": "openai"},
                    },
                ],
            )
    finally:
        set_settings(old_settings)

    assert isinstance(client, LLMClient)
    assert client._candidate_resolver is None
    assert [candidate.model for candidate in client._static_candidates] == [
        "openrouter/primary",
        "openrouter/fallback",
        "gpt-4o-mini",
    ]
    assert [candidate.provider for candidate in client._static_candidates] == [
        "openrouter",
        "openrouter",
        "openai",
    ]
    assert client._static_candidates[0].api_key == "sk-openrouter"
    assert client._static_candidates[0].context_length == 65_536
    assert client._static_candidates[1].api_key == "sk-openrouter"
    assert client._static_candidates[2].api_key == "sk-openai"
    assert client._static_candidates[1].temperature == 0.7
    assert client._static_candidates[1].extra_request_body == {"route": "openrouter-fallback"}
    assert client._static_candidates[2].base_url == "https://api.openai.example/v1"
    assert client._static_candidates[2].top_p == 0.8
    assert client._static_candidates[2].extra_request_headers == {"X-Fallback": "openai"}
    assert client.first_token_timeout == 12.0
    assert client.candidate_cooldown_seconds == 3.0


def test_create_transport_llm_client_without_model_uses_platform_default_pool_in_same_client() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider="openrouter",
            default_strategy="platform_free_pool",
            default_model="configured/default",
            temperature=0.2,
            timeout=10.0,
            openrouter=OpenRouterProviderConfig(
                api_key="sk-openrouter",
                base_url="https://openrouter.ai/api/v1",
                site_url="https://platform.example",
                site_name="Platform Test",
            ),
            platform_free_pool=PlatformFreePoolConfig(
                enabled=True,
                paid_fallback=PlatformFreePoolPaidFallbackConfig(
                    provider="openrouter",
                    model="qwen/qwen-2.5-7b-instruct",
                ),
                first_token_timeout_seconds=9.0,
                candidate_cooldown_seconds=4.0,
            ),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = create_transport_llm_client()
    finally:
        set_settings(old_settings)

    assert isinstance(client, LLMClient)
    assert client.model == "qwen/qwen-2.5-7b-instruct"
    assert client._candidate_resolver is not None
    assert [candidate.source for candidate in client._static_candidates] == [
        "platform_paid_fallback"
    ]
    assert client.platform_default_free_pool is True
    assert client.platform_paid_fallback_enabled is True
    assert client.first_token_timeout == 9.0
    assert client.candidate_cooldown_seconds == 4.0


def test_create_transport_llm_client_default_pool_can_disable_paid_fallback_for_empty_balance() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider="openrouter",
            default_strategy="platform_free_pool",
            default_model="configured/default",
            temperature=0.2,
            timeout=10.0,
            openrouter=OpenRouterProviderConfig(
                api_key="sk-openrouter",
                base_url="https://openrouter.ai/api/v1",
                site_url="https://platform.example",
                site_name="Platform Test",
            ),
            platform_free_pool=PlatformFreePoolConfig(
                enabled=True,
                paid_fallback=PlatformFreePoolPaidFallbackConfig(
                    provider="openrouter",
                    model="qwen/qwen-2.5-7b-instruct",
                ),
            ),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = create_transport_llm_client(allow_platform_paid_fallback=False)
    finally:
        set_settings(old_settings)

    assert isinstance(client, LLMClient)
    assert client.platform_default_free_pool is True
    assert client.platform_paid_fallback_enabled is False
    assert client._static_candidates == []


def test_humanitec_llm_provider_uses_dynamic_pool_independent_of_default_strategy() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider="openai",
            default_strategy="configured",
            default_model="configured/default",
            temperature=0.2,
            timeout=10.0,
            openrouter=OpenRouterProviderConfig(
                api_key="sk-openrouter",
                base_url="https://openrouter.ai/api/v1",
                site_url="https://platform.example",
                site_name="Platform Test",
            ),
            platform_free_pool=PlatformFreePoolConfig(
                enabled=True,
                paid_fallback=PlatformFreePoolPaidFallbackConfig(
                    provider="openrouter",
                    model="qwen/qwen-2.5-7b-instruct",
                ),
            ),
        ),
    )
    try:
        set_settings(settings)
        assert should_use_platform_default_free_pool(
            model=HUMANITEC_LLM_AUTO_MODEL,
            provider=HUMANITEC_LLM_PROVIDER,
            api_key=None,
            base_url=None,
            folder_id=None,
            settings=settings,
        ) is True
        with _production_llm_env():
            client = create_transport_llm_client(
                provider=HUMANITEC_LLM_PROVIDER,
                model_name=HUMANITEC_LLM_AUTO_MODEL,
                allow_platform_paid_fallback=False,
            )
    finally:
        set_settings(old_settings)

    assert isinstance(client, LLMClient)
    assert client.platform_default_free_pool is True
    assert client.platform_paid_fallback_enabled is False
    assert client._candidate_resolver is not None
    assert client._static_candidates == []


def test_create_transport_llm_client_uses_humanitec_default_provider_as_platform_route() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider=HUMANITEC_LLM_PROVIDER,
            default_strategy="configured",
            default_model=HUMANITEC_LLM_AUTO_MODEL,
            temperature=0.2,
            timeout=10.0,
            openrouter=OpenRouterProviderConfig(
                api_key="sk-openrouter",
                base_url="https://openrouter.ai/api/v1",
                site_url="https://platform.example",
                site_name="Platform Test",
            ),
            platform_free_pool=PlatformFreePoolConfig(
                enabled=True,
                paid_fallback=PlatformFreePoolPaidFallbackConfig(
                    provider="openrouter",
                    model="qwen/qwen-2.5-7b-instruct",
                ),
            ),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = create_transport_llm_client(allow_platform_paid_fallback=False)
    finally:
        set_settings(old_settings)

    assert isinstance(client, LLMClient)
    assert client.platform_default_free_pool is True
    assert client.platform_paid_fallback_enabled is False
    assert client._candidate_resolver is not None
    assert client._static_candidates == []


def test_humanitec_llm_accepts_concrete_free_pool_model() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider="openrouter",
            default_strategy="configured",
            default_model="configured/default",
            openrouter=OpenRouterProviderConfig(
                api_key="sk-openrouter",
                base_url="https://openrouter.ai/api/v1",
            ),
            platform_free_pool=PlatformFreePoolConfig(enabled=True),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = create_transport_llm_client(
                provider=HUMANITEC_LLM_PROVIDER,
                model_name="openrouter:qwen/qwen3-coder:free",
                allow_platform_paid_fallback=False,
            )
    finally:
        set_settings(old_settings)

    assert isinstance(client, LLMClient)
    assert client.llm_provider == "openrouter"
    assert client.model == "qwen/qwen3-coder:free"
    assert client.platform_default_free_pool is True
    assert client.platform_paid_fallback_enabled is False
    assert client._candidate_resolver is not None


def test_explicit_platform_provider_accepts_humanitec_llms_fallback() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider="openrouter",
            default_strategy="configured",
            default_model="configured/default",
            openrouter=OpenRouterProviderConfig(
                api_key="sk-openrouter",
                base_url="https://openrouter.ai/api/v1",
            ),
            platform_free_pool=PlatformFreePoolConfig(enabled=True),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = create_transport_llm_client(
                provider="openrouter",
                model_name="primary/model",
                fallback_models=[
                    LLMCallConfig(
                        provider=HUMANITEC_LLM_PROVIDER,
                        model=HUMANITEC_LLM_AUTO_MODEL,
                    )
                ],
            )
    finally:
        set_settings(old_settings)

    assert isinstance(client, LLMClient)
    assert client.llm_provider == "openrouter"
    assert client.model == "primary/model"
    assert client._candidate_resolver is not None


def test_platform_free_pool_provider_is_configured_with_api_keys_only() -> None:
    from core.config.llm_openai_compat import provider_is_configured_for_free_pool

    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider="humanitec_llm",
            openrouter=OpenRouterProviderConfig(
                api_keys=["sk-extra"],
                base_url="https://openrouter.ai/api/v1",
            ),
            platform_free_pool=PlatformFreePoolConfig(enabled=True),
        ),
    )
    try:
        set_settings(settings)
        assert provider_is_configured_for_free_pool(settings.llm, "openrouter") is True
    finally:
        set_settings(old_settings)


def test_platform_free_pool_provider_not_configured_without_keys() -> None:
    from core.config.llm_openai_compat import provider_is_configured_for_free_pool

    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider="humanitec_llm",
            openrouter=OpenRouterProviderConfig(
                base_url="https://openrouter.ai/api/v1",
            ),
            platform_free_pool=PlatformFreePoolConfig(enabled=True),
        ),
    )
    try:
        set_settings(settings)
        assert provider_is_configured_for_free_pool(settings.llm, "openrouter") is False
    finally:
        set_settings(old_settings)


def _tools_payload() -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Lookup something",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 402, 403, 404, 429, 500])
async def test_stream_falls_back_before_first_chunk_on_http_status(
    status: int,
    unique_id: str,
) -> None:
    primary_model = f"primary-fail-{status}-{unique_id}"
    fallback_model = f"fallback-fast-{status}-{unique_id}"
    server = _OpenAICompatibleTestServer(
        {
            primary_model: lambda writer: _write_json_response(
                writer,
                status,
                {"error": f"http-{status}"},
            ),
            fallback_model: lambda writer: _write_sse_text(writer, "fallback-ok"),
        }
    )
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate(primary_model, base_url=server.base_url),
                _candidate(fallback_model, base_url=server.base_url),
            ],
        )
        message = await client.chat([_message("hello")])
        assert get_message_text(message) == "fallback-ok"
        assert [request.model for request in server.requests] == [
            primary_model,
            fallback_model,
        ]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_all_free_fail_then_paid_succeeds(unique_id: str) -> None:
    free_model = f"free-500-{unique_id}"
    paid_model = f"paid-ok-{unique_id}"
    server = _OpenAICompatibleTestServer(
        {
            free_model: lambda writer: _write_json_response(writer, 500, {"error": "free"}),
            paid_model: lambda writer: _write_sse_text(writer, "paid-ok"),
        }
    )
    await server.start()
    try:
        client = LLMClient(
            model=free_model,
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[
                _candidate(free_model, base_url=server.base_url, source="platform_free"),
                _candidate(paid_model, base_url=server.base_url, source="platform_paid_fallback"),
            ],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=0.0,
            timeout=5.0,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=True,
        )
        message = await client.chat([_message("hello")])
        assert get_message_text(message) == "paid-ok"
        assert [request.model for request in server.requests] == [free_model, paid_model]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_all_free_and_paid_fail_raises_last_http_error(unique_id: str) -> None:
    free_model = f"free-500-{unique_id}"
    paid_model = f"paid-500-{unique_id}"
    server = _OpenAICompatibleTestServer(
        {
            free_model: lambda writer: _write_json_response(writer, 500, {"error": "free"}),
            paid_model: lambda writer: _write_json_response(writer, 500, {"error": "paid"}),
        }
    )
    await server.start()
    try:
        client = LLMClient(
            model=free_model,
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[
                _candidate(free_model, base_url=server.base_url, source="platform_free"),
                _candidate(paid_model, base_url=server.base_url, source="platform_paid_fallback"),
            ],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=0.0,
            timeout=5.0,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=True,
        )
        with pytest.raises(httpx2.HTTPStatusError):
            await client.chat([_message("hello")])
        assert [request.model for request in server.requests] == [free_model, paid_model]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_platform_free_pool_raises_when_no_candidate_supports_files() -> None:
    server = _OpenAICompatibleTestServer(
        {"free-text": lambda writer: _write_sse_text(writer, "unexpected")}
    )
    await server.start()
    try:
        candidate = _candidate(
            "free-text",
            base_url=server.base_url,
            supported_parameters=frozenset({"temperature"}),
            source="platform_free",
        )
        client = LLMClient(
            model=str(candidate.model),
            api_key=str(candidate.api_key),
            base_url=candidate.base_url,
            llm_provider=candidate.provider,
            candidates=[candidate],
            first_token_timeout=0.05,
            candidate_cooldown_seconds=0.0,
            timeout=2.0,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=False,
        )
        with pytest.raises(RuntimeError, match="compatible with request parameters"):
            await client.chat(
                [
                    Message(
                        message_id="file-msg",
                        role=ROLE_USER,
                        parts=[
                            Part(raw=b"image", filename="image.png", media_type="image/png"),
                        ],
                    )
                ]
            )
        assert server.requests == []
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_platform_free_pool_raises_when_no_candidate_supports_response_format() -> None:
    server = _OpenAICompatibleTestServer(
        {"free-text": lambda writer: _write_sse_text(writer, "unexpected")}
    )
    await server.start()
    try:
        candidate = _candidate(
            "free-text",
            base_url=server.base_url,
            supported_parameters=frozenset({"temperature"}),
            source="platform_free",
        )
        client = LLMClient(
            model=str(candidate.model),
            api_key=str(candidate.api_key),
            base_url=candidate.base_url,
            llm_provider=candidate.provider,
            candidates=[candidate],
            first_token_timeout=0.05,
            candidate_cooldown_seconds=0.0,
            timeout=2.0,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=False,
        )
        with pytest.raises(RuntimeError, match="compatible with request parameters"):
            async for _event in client.stream(
                [_message("hello")],
                response_format={"type": "json_object"},
            ):
                raise AssertionError("stream must not yield")
        assert server.requests == []
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_paid_fallback_used_when_free_has_no_tools() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "free-no-tools": lambda writer: _write_sse_text(writer, "unexpected"),
            "paid-tools": lambda writer: _write_sse_text(writer, "paid-tools-ok"),
        }
    )
    await server.start()
    try:
        client = LLMClient(
            model="free-no-tools",
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[
                _candidate(
                    "free-no-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"temperature"}),
                    source="platform_free",
                ),
                _candidate(
                    "paid-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"tools"}),
                    source="platform_paid_fallback",
                ),
            ],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=0.0,
            timeout=5.0,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=True,
        )
        message = await client.chat([_message("hello")], tools=_tools_payload())
        assert get_message_text(message) == "paid-tools-ok"
        assert [request.model for request in server.requests] == ["paid-tools"]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_paid_without_tools_does_not_guess() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "free-no-tools": lambda writer: _write_sse_text(writer, "unexpected"),
            "paid-no-tools": lambda writer: _write_sse_text(writer, "unexpected-paid"),
        }
    )
    await server.start()
    try:
        client = LLMClient(
            model="free-no-tools",
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[
                _candidate(
                    "free-no-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"temperature"}),
                    source="platform_free",
                ),
                _candidate(
                    "paid-no-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"temperature"}),
                    source="platform_paid_fallback",
                ),
            ],
            first_token_timeout=0.05,
            candidate_cooldown_seconds=0.0,
            timeout=2.0,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=True,
        )
        with pytest.raises(RuntimeError, match="compatible with request parameters"):
            await client.chat([_message("hello")], tools=_tools_payload())
        assert server.requests == []
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_authored_fallback_used_when_free_has_no_tools() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "free-no-tools": lambda writer: _write_sse_text(writer, "unexpected"),
            "authored-tools": lambda writer: _write_sse_text(writer, "authored-ok"),
        }
    )
    await server.start()
    try:
        client = LLMClient(
            model="free-no-tools",
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[
                _candidate(
                    "free-no-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"temperature"}),
                    source="platform_free",
                ),
                _candidate(
                    "authored-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"tools"}),
                    source="fallback",
                ),
            ],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=0.0,
            timeout=5.0,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=False,
        )
        message = await client.chat([_message("hello")], tools=_tools_payload())
        assert get_message_text(message) == "authored-ok"
        assert [request.model for request in server.requests] == ["authored-tools"]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_explicit_byok_without_tools_uses_first_candidate() -> None:
    server = _OpenAICompatibleTestServer(
        {"byok-no-tools": lambda writer: _write_sse_text(writer, "byok-ok")}
    )
    await server.start()
    try:
        client = LLMClient(
            model="byok-no-tools",
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[
                _candidate(
                    "byok-no-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"temperature"}),
                    source="explicit",
                )
            ],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=0.0,
            timeout=5.0,
            platform_default_free_pool=False,
        )
        message = await client.chat([_message("hello")], tools=_tools_payload())
        assert get_message_text(message) == "byok-ok"
        assert [request.model for request in server.requests] == ["byok-no-tools"]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_empty_candidates_platform_pool_without_paid_raises() -> None:
    client = LLMClient(
        model="unused",
        api_key="test-key",
        base_url="https://example.invalid/v1",
        llm_provider="openai",
        candidates=[],
        first_token_timeout=0.05,
        candidate_cooldown_seconds=0.0,
        timeout=2.0,
        platform_default_free_pool=True,
        platform_paid_fallback_enabled=False,
    )
    with pytest.raises(RuntimeError, match="no available free models"):
        await client.chat([_message("hello")])


@pytest.mark.asyncio
async def test_filter_then_cap_keeps_tool_capable_platform_free_beyond_global_rank() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "no-tools-0": lambda writer: _write_sse_text(writer, "unexpected-0"),
            "no-tools-1": lambda writer: _write_sse_text(writer, "unexpected-1"),
            "tools-late": lambda writer: _write_sse_text(writer, "tools-ok"),
        }
    )
    await server.start()
    try:
        client = LLMClient(
            model="no-tools-0",
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[
                _candidate(
                    "no-tools-0",
                    base_url=server.base_url,
                    supported_parameters=frozenset(),
                    source="platform_free",
                ),
                _candidate(
                    "no-tools-1",
                    base_url=server.base_url,
                    supported_parameters=frozenset(),
                    source="platform_free",
                ),
                _candidate(
                    "tools-late",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"tools"}),
                    source="platform_free",
                ),
            ],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=0.0,
            timeout=5.0,
            max_candidates_total=2,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=False,
        )
        message = await client.chat([_message("hello")], tools=_tools_payload())
        assert get_message_text(message) == "tools-ok"
        assert [request.model for request in server.requests] == ["tools-late"]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_filter_then_cap_keeps_file_capable_platform_free_beyond_global_rank() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "text-0": lambda writer: _write_sse_text(writer, "unexpected-0"),
            "text-1": lambda writer: _write_sse_text(writer, "unexpected-1"),
            "vision-late": lambda writer: _write_sse_text(writer, "vision-ok"),
        }
    )
    await server.start()
    try:
        client = LLMClient(
            model="text-0",
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[
                _candidate(
                    "text-0",
                    base_url=server.base_url,
                    source="platform_free",
                ),
                _candidate(
                    "text-1",
                    base_url=server.base_url,
                    source="platform_free",
                ),
                _candidate(
                    "vision-late",
                    base_url=server.base_url,
                    source="platform_free",
                    input_modalities=frozenset({"text", "image"}),
                ),
            ],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=0.0,
            timeout=5.0,
            max_candidates_total=2,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=False,
        )
        message = await client.chat(
            [
                Message(
                    message_id="file-msg",
                    role=ROLE_USER,
                    parts=[
                        Part(raw=b"image", filename="image.png", media_type="image/png"),
                    ],
                )
            ]
        )
        assert get_message_text(message) == "vision-ok"
        assert [request.model for request in server.requests] == ["vision-late"]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_filter_then_cap_keeps_json_capable_platform_free_beyond_global_rank() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "plain-0": lambda writer: _write_sse_text(writer, "unexpected-0"),
            "plain-1": lambda writer: _write_sse_text(writer, "unexpected-1"),
            "json-late": lambda writer: _write_sse_text(writer, "json-ok"),
        }
    )
    await server.start()
    try:
        client = LLMClient(
            model="plain-0",
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[
                _candidate(
                    "plain-0",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"temperature"}),
                    source="platform_free",
                ),
                _candidate(
                    "plain-1",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"temperature"}),
                    source="platform_free",
                ),
                _candidate(
                    "json-late",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"json_schema"}),
                    source="platform_free",
                ),
            ],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=0.0,
            timeout=5.0,
            max_candidates_total=2,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=False,
        )
        message_events: list[object] = []
        async for event in client.stream(
            [_message("hello")],
            response_format={"type": "json_object"},
        ):
            message_events.append(event)
        assert message_events
        assert [request.model for request in server.requests] == ["json-late"]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_filter_then_cap_limits_matching_platform_free_candidates() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "tools-0": lambda writer: _write_json_response(writer, 500, {"error": "0"}),
            "tools-1": lambda writer: _write_json_response(writer, 500, {"error": "1"}),
            "tools-2": lambda writer: _write_sse_text(writer, "should-not-run"),
            "paid": lambda writer: _write_sse_text(writer, "paid-ok"),
        }
    )
    await server.start()
    try:
        client = LLMClient(
            model="tools-0",
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[
                _candidate(
                    "tools-0",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"tools"}),
                    source="platform_free",
                ),
                _candidate(
                    "tools-1",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"tools"}),
                    source="platform_free",
                ),
                _candidate(
                    "tools-2",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"tools"}),
                    source="platform_free",
                ),
                _candidate(
                    "paid",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"tools"}),
                    source="platform_paid_fallback",
                ),
            ],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=0.0,
            timeout=5.0,
            max_candidates_total=2,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=True,
        )
        message = await client.chat([_message("hello")], tools=_tools_payload())
        assert get_message_text(message) == "paid-ok"
        assert [request.model for request in server.requests] == ["tools-0", "tools-1", "paid"]
    finally:
        await server.close()


async def _write_429_retry_after(writer: asyncio.StreamWriter, seconds: int) -> None:
    body = b'{"error":"rate_limited"}'
    writer.write(
        (
            "HTTP/1.1 429 Too Many Requests\r\n"
            "Content-Type: application/json\r\n"
            f"Retry-After: {seconds}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        + body
    )
    await writer.drain()


async def _write_429_retry_after_http_date(writer: asyncio.StreamWriter, seconds: int) -> None:
    body = b'{"error":"rate_limited"}'
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    writer.write(
        (
            "HTTP/1.1 429 Too Many Requests\r\n"
            "Content-Type: application/json\r\n"
            f"Retry-After: {format_datetime(retry_at, usegmt=True)}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        + body
    )
    await writer.drain()


@pytest.mark.asyncio
async def test_stream_uses_redis_cooldown_and_retry_after(unique_id: str) -> None:
    from core.ai.provider_error import AIProviderErrorClass
    from core.clients.llm.candidate_cooldown import (
        cooldown_redis_key,
        parse_candidate_cooldown_payload,
    )
    from core.clients.redis_client import RedisClient

    fail_model = f"fail-429-{unique_id}"
    ok_model = f"ok-{unique_id}"
    redis = RedisClient(get_settings().database.redis_url)
    server = _OpenAICompatibleTestServer(
        {
            fail_model: lambda writer: _write_429_retry_after(writer, 30),
            ok_model: lambda writer: _write_sse_text(writer, "ok"),
        }
    )
    await server.start()
    fail_on_server = _candidate(fail_model, base_url=server.base_url)
    ok_on_server = _candidate(ok_model, base_url=server.base_url)
    try:
        client = LLMClient(
            model=fail_model,
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[fail_on_server, ok_on_server],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=5.0,
            timeout=5.0,
        )
        message = await client.chat([_message("hello")])
        assert get_message_text(message) == "ok"
        ttl = await redis.ttl(cooldown_redis_key(fail_on_server))
        assert 20 <= ttl <= 30
        raw_cooldown = await redis.get(cooldown_redis_key(fail_on_server))
        assert raw_cooldown is not None
        record = parse_candidate_cooldown_payload(raw_cooldown)
        assert record.error_class == AIProviderErrorClass.RATE_LIMITED
        assert record.http_status == 429
        second = await client.chat([_message("hello")])
        assert get_message_text(second) == "ok"
        assert [request.model for request in server.requests] == [fail_model, ok_model, ok_model]
    finally:
        _ = await redis.delete(cooldown_redis_key(fail_on_server))
        await server.close()


@pytest.mark.asyncio
async def test_stream_uses_redis_cooldown_and_http_date_retry_after(unique_id: str) -> None:
    from core.clients.llm.candidate_cooldown import cooldown_redis_key
    from core.clients.redis_client import RedisClient

    fail_model = f"fail-429-date-{unique_id}"
    ok_model = f"ok-date-{unique_id}"
    redis = RedisClient(get_settings().database.redis_url)
    server = _OpenAICompatibleTestServer(
        {
            fail_model: lambda writer: _write_429_retry_after_http_date(writer, 30),
            ok_model: lambda writer: _write_sse_text(writer, "ok"),
        }
    )
    await server.start()
    fail_on_server = _candidate(fail_model, base_url=server.base_url)
    ok_on_server = _candidate(ok_model, base_url=server.base_url)
    try:
        client = LLMClient(
            model=fail_model,
            api_key="test-key",
            base_url=server.base_url,
            llm_provider="openai",
            candidates=[fail_on_server, ok_on_server],
            first_token_timeout=0.5,
            candidate_cooldown_seconds=5.0,
            timeout=5.0,
        )
        message = await client.chat([_message("hello")])
        assert get_message_text(message) == "ok"
        ttl = await redis.ttl(cooldown_redis_key(fail_on_server))
        assert 20 <= ttl <= 30
        second = await client.chat([_message("hello")])
        assert get_message_text(second) == "ok"
        assert [request.model for request in server.requests] == [fail_model, ok_model, ok_model]
    finally:
        _ = await redis.delete(cooldown_redis_key(fail_on_server))
        await server.close()

