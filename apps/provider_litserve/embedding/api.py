"""
LitServe API эмбеддера: POST ``/v1/embeddings`` (OpenAI-совместимое тело).
"""

import litserve as ls

from apps.provider_litserve.openai_server_contracts import OpenAIEmbeddingsRequest
from apps.provider_litserve.provider_litserve_http_schemas import OpenAIEmbeddingsResponseBody
from apps.provider_litserve.shared import resolve_embedding_device, resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig
from core.types import JsonValue

from .engines import LocalEmbeddingEngine, parse_embedding_body


class EmbeddingLitAPI(ls.LitAPI):
    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/embeddings")
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._engine: LocalEmbeddingEngine = LocalEmbeddingEngine(cfg)

    def setup(self, device: str | None) -> None:
        litserve_device = device if device is not None else resolve_torch_device(self._cfg)
        d = resolve_embedding_device(self._cfg, litserve_device)
        self._engine.setup(d)

    def decode_request(self, request: OpenAIEmbeddingsRequest | JsonValue, **kwargs: JsonValue) -> OpenAIEmbeddingsRequest:
        _ = kwargs
        return parse_embedding_body(request)

    def predict(self, x: OpenAIEmbeddingsRequest, **kwargs: JsonValue) -> OpenAIEmbeddingsResponseBody:
        _ = kwargs
        return self._engine.embed(x.model, x.input)

    def encode_response(self, output: OpenAIEmbeddingsResponseBody, **kwargs: JsonValue) -> OpenAIEmbeddingsResponseBody:
        _ = kwargs
        return output
