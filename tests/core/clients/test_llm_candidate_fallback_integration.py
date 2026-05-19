"""Integration coverage for LLMClient candidate fallback.

These tests deliberately exercise the real httpx/OpenAI-compatible path.  The
local server below is a tiny deterministic endpoint, not a patched client.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import Any, Callable

import pytest
from a2a.types import (
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils.message import get_message_text

from core.clients.llm.config import LLMCallConfig
from core.clients.llm.factory import LLMClient, get_llm, should_use_platform_default_free_pool
from core.clients.llm.model_routing import HUMANITEC_LLM_AUTO_MODEL, HUMANITEC_LLM_PROVIDER
from core.config import BaseSettings, get_settings, set_settings
from core.config.models import (
    LLMConfig,
    OpenAIProviderConfig,
    OpenRouterFreePoolConfig,
    OpenRouterProviderConfig,
)


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
        messageId="test-user-message",
        role=Role.user,
        parts=[Part(root=TextPart(text=text))],
    )


def _candidate(
    model: str,
    *,
    base_url: str,
    supported_parameters: frozenset[str] = frozenset(),
    source: str = "test",
) -> LLMCallConfig:
    return LLMCallConfig(
        provider="openai",
        model=model,
        api_key="test-key",
        base_url=base_url,
        source=source,
        supported_parameters=supported_parameters,
        input_modalities=frozenset({"text"}),
        output_modalities=frozenset({"text"}),
    )


def _client_for(server: _OpenAICompatibleTestServer, candidates: list[LLMCallConfig]) -> LLMClient:
    return LLMClient(
        model=candidates[0].model,
        api_key=candidates[0].api_key,
        base_url=candidates[0].base_url,
        llm_provider=candidates[0].provider,
        candidates=candidates,
        first_token_timeout=0.05,
        candidate_cooldown_seconds=0.0,
        timeout=2.0,
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
async def test_stream_falls_back_when_primary_has_no_first_token() -> None:
    server = _OpenAICompatibleTestServer(
        {
            "primary-slow": lambda writer: _write_sse_text(
                writer,
                "too-late",
                delay_before_first_chunk=0.2,
            ),
            "fallback-fast": lambda writer: _write_sse_text(writer, "fallback-ok"),
        }
    )
    await server.start()
    try:
        client = _client_for(
            server,
            [
                _candidate("primary-slow", base_url=server.base_url),
                _candidate("fallback-fast", base_url=server.base_url),
            ],
        )

        message = await client.chat([_message("hello")])

        assert get_message_text(message) == "fallback-ok"
        assert [request.model for request in server.requests] == [
            "primary-slow",
            "fallback-fast",
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

        with pytest.raises(json.JSONDecodeError):
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
async def test_openrouter_free_candidate_requires_explicit_tool_support() -> None:
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
                    source="openrouter_free",
                ),
                _candidate(
                    "free-with-tools",
                    base_url=server.base_url,
                    supported_parameters=frozenset({"tools"}),
                    source="openrouter_free",
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
async def test_openrouter_free_pool_raises_when_no_candidate_supports_tools() -> None:
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
            source="openrouter_free",
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

        with pytest.raises(RuntimeError, match="совместимых"):
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


def test_get_llm_builds_explicit_fallback_candidates_from_real_settings() -> None:
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
            openrouter_free_pool=OpenRouterFreePoolConfig(
                enabled=True,
                first_token_timeout_seconds=12.0,
                candidate_cooldown_seconds=3.0,
            ),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = get_llm(
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
    assert client._static_candidates[1].api_key == "sk-openrouter"
    assert client._static_candidates[2].api_key == "sk-openai"
    assert client._static_candidates[1].temperature == 0.7
    assert client._static_candidates[1].extra_request_body == {"route": "openrouter-fallback"}
    assert client._static_candidates[2].base_url == "https://api.openai.example/v1"
    assert client._static_candidates[2].top_p == 0.8
    assert client._static_candidates[2].extra_request_headers == {"X-Fallback": "openai"}
    assert client.first_token_timeout == 12.0
    assert client.candidate_cooldown_seconds == 3.0


def test_get_llm_without_model_uses_platform_default_pool_in_same_client() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider="openrouter",
            default_strategy="openrouter_free_pool",
            default_model="configured/default",
            temperature=0.2,
            timeout=10.0,
            openrouter=OpenRouterProviderConfig(
                api_key="sk-openrouter",
                base_url="https://openrouter.ai/api/v1",
                site_url="https://platform.example",
                site_name="Platform Test",
            ),
            openrouter_free_pool=OpenRouterFreePoolConfig(
                enabled=True,
                fallback_model="qwen/qwen-2.5-7b-instruct",
                first_token_timeout_seconds=9.0,
                candidate_cooldown_seconds=4.0,
            ),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = get_llm()
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


def test_get_llm_default_pool_can_disable_paid_fallback_for_empty_balance() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider="openrouter",
            default_strategy="openrouter_free_pool",
            default_model="configured/default",
            temperature=0.2,
            timeout=10.0,
            openrouter=OpenRouterProviderConfig(
                api_key="sk-openrouter",
                base_url="https://openrouter.ai/api/v1",
                site_url="https://platform.example",
                site_name="Platform Test",
            ),
            openrouter_free_pool=OpenRouterFreePoolConfig(
                enabled=True,
                fallback_model="qwen/qwen-2.5-7b-instruct",
            ),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = get_llm(allow_platform_paid_fallback=False)
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
            openrouter_free_pool=OpenRouterFreePoolConfig(
                enabled=True,
                fallback_model="qwen/qwen-2.5-7b-instruct",
            ),
        ),
    )
    try:
        set_settings(settings)
        assert should_use_platform_default_free_pool(
            model_name=HUMANITEC_LLM_AUTO_MODEL,
            provider=HUMANITEC_LLM_PROVIDER,
            api_key=None,
            base_url=None,
            folder_id=None,
            settings=settings,
        ) is True
        with _production_llm_env():
            client = get_llm(
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
