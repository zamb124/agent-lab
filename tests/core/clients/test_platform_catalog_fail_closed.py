from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

import pytest

from apps.flows.config import get_settings as flows_get_settings
from apps.flows.config import set_settings as flows_set_settings
from core.ai.adapters.catalog_base import AIProviderAdapterError, BaseModelCatalogAdapter
from core.ai.adapters.openai_compatible import OpenAICompatibleModelCatalogAdapter
from core.ai.adapters.openrouter import OpenRouterModelCatalogAdapter
from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.config import BaseSettings
from core.config.models import (
    GroqProviderConfig,
    LLMConfig,
    NvidiaProviderConfig,
    OpenRouterProviderConfig,
)


class _UnknownProviderAdapter(BaseModelCatalogAdapter):
    provider = "not-a-real-provider"

    async def list_models(self, *, probe_embeddings: bool = True) -> list[AIModelRecord]:
        raise RuntimeError("list_models must not run")


class _JsonGetServer:
    def __init__(self, *, status: int, payload: Mapping[str, Any] | None = None) -> None:
        self.status = status
        self.payload = dict(payload) if payload is not None else None
        self._server: asyncio.AbstractServer | None = None
        self.requests = 0

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("server is not started")
        host, port = self._server.sockets[0].getsockname()[:2]
        return f"http://{host}:{port}"

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
            _ = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=1.0)
            self.requests += 1
            if self.payload is None:
                body = b""
            else:
                body = json.dumps(self.payload).encode("utf-8")
            reason = "OK" if self.status == 200 else "Error"
            writer.write(
                (
                    f"HTTP/1.1 {self.status} {reason}\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ).encode("ascii")
                + body
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, BrokenPipeError):
            return
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, BrokenPipeError):
                pass


def _unconfigured_settings() -> BaseSettings:
    return BaseSettings(
        testing=False,
        llm=LLMConfig(
            openrouter=OpenRouterProviderConfig(api_key=None),
            groq=GroqProviderConfig(api_key=None),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider",
    ["openrouter", "bothub", "groq", "cerebras", "nvidia", "mistral", "zai", "sambanova"],
)
async def test_list_models_unconfigured_raises(provider: str) -> None:
    settings = _unconfigured_settings()
    if provider == "openrouter":
        adapter = OpenRouterModelCatalogAdapter(settings)
    else:
        adapter = OpenAICompatibleModelCatalogAdapter(provider, settings)
    assert adapter.is_configured() is False
    with pytest.raises(ValueError, match="model provider is not configured"):
        await adapter.list_models(probe_embeddings=False)


def test_groq_adapter_is_configured_with_api_keys_only() -> None:
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            groq=GroqProviderConfig(
                api_keys=["sk-extra"],
                smoke_model="openai/gpt-oss-20b",
            ),
        ),
    )
    adapter = OpenAICompatibleModelCatalogAdapter("groq", settings)
    assert adapter.is_configured() is True


def test_nvidia_adapter_is_configured_with_api_keys_only() -> None:
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            nvidia=NvidiaProviderConfig(
                api_keys=["nvapi-extra"],
                smoke_model="openai/gpt-oss-20b",
            ),
        ),
    )
    adapter = OpenAICompatibleModelCatalogAdapter("nvidia", settings)
    assert adapter.is_configured() is True


def test_configured_llm_provider_unknown_raises() -> None:
    adapter = _UnknownProviderAdapter(_unconfigured_settings())
    with pytest.raises(ValueError, match="is not supported for the OpenAI-compatible API"):
        adapter._configured_llm_provider()


@pytest.mark.asyncio
async def test_list_models_empty_catalog_returns_empty_list() -> None:
    server = _JsonGetServer(status=200, payload={"data": []})
    await server.start()
    try:
        settings = BaseSettings(
            testing=False,
            llm=LLMConfig(
                groq=GroqProviderConfig(
                    api_key="sk-test",
                    models_url=f"{server.url}/models",
                    smoke_model="llama-3.1-8b-instant",
                ),
            ),
        )
        adapter = OpenAICompatibleModelCatalogAdapter("groq", settings)
        records = await adapter.list_models(probe_embeddings=False)
        assert records == []
    finally:
        await server.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [410, 500])
async def test_list_models_http_error_raises_adapter_error(status: int) -> None:
    server = _JsonGetServer(status=status, payload={"error": "fail"})
    await server.start()
    try:
        settings = BaseSettings(
            testing=False,
            llm=LLMConfig(
                groq=GroqProviderConfig(
                    api_key="sk-test",
                    models_url=f"{server.url}/models",
                    smoke_model="llama-3.1-8b-instant",
                ),
            ),
        )
        adapter = OpenAICompatibleModelCatalogAdapter("groq", settings)
        with pytest.raises(AIProviderAdapterError, match=f"HTTP {status}"):
            await adapter.list_models(probe_embeddings=False)
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_sync_empty_catalog_does_not_delete_existing_records(
    di,
    unique_id: str,
) -> None:
    server = _JsonGetServer(status=200, payload={"data": []})
    await server.start()
    old_settings = flows_get_settings()
    model_id = f"keep-{unique_id}"
    existing = AIModelRecord(
        provider="groq",
        model_id=model_id,
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
    )
    await AIModelRecord.set(existing)
    try:
        flows_set_settings(
            old_settings.model_copy(
                update={
                    "llm": old_settings.llm.model_copy(
                        update={
                            "groq": GroqProviderConfig(
                                api_key="sk-test",
                                models_url=f"{server.url}/models",
                                smoke_model="llama-3.1-8b-instant",
                            ),
                        }
                    )
                }
            )
        )
        with pytest.raises(RuntimeError, match="did not return models"):
            await di.llm_models_service.sync_models_by_provider("groq")
        stored = await AIModelRecord.by_provider_and_model_id("groq", model_id)
        assert stored is not None
        assert stored.model_id == model_id
    finally:
        flows_set_settings(old_settings)
        await server.close()


@pytest.mark.asyncio
async def test_sync_http_500_does_not_empty_catalog(
    di,
    unique_id: str,
) -> None:
    server = _JsonGetServer(status=500, payload={"error": "fail"})
    await server.start()
    old_settings = flows_get_settings()
    model_id = f"keep-500-{unique_id}"
    existing = AIModelRecord(
        provider="groq",
        model_id=model_id,
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
    )
    await AIModelRecord.set(existing)
    try:
        flows_set_settings(
            old_settings.model_copy(
                update={
                    "llm": old_settings.llm.model_copy(
                        update={
                            "groq": GroqProviderConfig(
                                api_key="sk-test",
                                models_url=f"{server.url}/models",
                                smoke_model="llama-3.1-8b-instant",
                            ),
                        }
                    )
                }
            )
        )
        with pytest.raises(AIProviderAdapterError, match="HTTP 500"):
            await di.llm_models_service.sync_models_by_provider("groq")
        stored = await AIModelRecord.by_provider_and_model_id("groq", model_id)
        assert stored is not None
        assert stored.model_id == model_id
    finally:
        flows_set_settings(old_settings)
        await server.close()
