"""
LitServe API эмбеддера: POST ``/v1/embeddings`` (OpenAI-совместимое тело).
"""

import litserve as ls

from core.config.models import ProviderLitserveInfraConfig

from apps.provider_litserve.shared import resolve_torch_device

from .engines import LocalEmbeddingEngine, parse_embedding_body


class EmbeddingLitAPI(ls.LitAPI):
    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/embeddings")
        self._cfg = cfg
        self._engine = LocalEmbeddingEngine(cfg)

    def setup(self, device) -> None:
        d = device if device is not None else resolve_torch_device(self._cfg)
        self._engine.setup(d)

    def decode_request(self, request, **kwargs):
        return parse_embedding_body(request)

    def predict(self, x, **kwargs):
        return self._engine.embed(x["model"], x["input"])
