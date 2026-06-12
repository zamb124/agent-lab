"""LitServe API chat LLM: POST ``/v1/chat/completions``."""

from __future__ import annotations

import litserve as ls

from apps.provider_litserve.llm.engines import LocalChatEngine, parse_chat_body
from apps.provider_litserve.openai_server_contracts import OpenAIChatCompletionsRequest
from apps.provider_litserve.provider_litserve_http_schemas import OpenAIChatCompletionsResponseBody
from apps.provider_litserve.shared import resolve_llm_device, resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig
from core.types import JsonValue


class ChatLitAPI(ls.LitAPI):
    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/chat/completions")
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._engine: LocalChatEngine = LocalChatEngine(cfg)

    def setup(self, device: str | None) -> None:
        litserve_device = device if device is not None else resolve_torch_device(self._cfg)
        llm_device = resolve_llm_device(self._cfg, litserve_device)
        self._engine.setup(llm_device)

    def decode_request(
        self,
        request: OpenAIChatCompletionsRequest | JsonValue,
        **kwargs: JsonValue,
    ) -> OpenAIChatCompletionsRequest:
        _ = kwargs
        return parse_chat_body(request)

    def predict(
        self,
        request: OpenAIChatCompletionsRequest,
        **kwargs: JsonValue,
    ) -> OpenAIChatCompletionsResponseBody:
        _ = kwargs
        return self._engine.chat(request)

    def encode_response(
        self,
        output: OpenAIChatCompletionsResponseBody,
        **kwargs: JsonValue,
    ) -> OpenAIChatCompletionsResponseBody:
        _ = kwargs
        return output
