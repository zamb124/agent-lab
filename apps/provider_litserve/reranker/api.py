"""
LitServe API реранкера: POST ``/v1/rerank``, тело ``{query, passages}``.
"""

import litserve as ls

from apps.provider_litserve.openai_server_contracts import RerankQueryPassagesRequest
from apps.provider_litserve.provider_litserve_http_schemas import RerankResponseBody
from apps.provider_litserve.shared import resolve_rerank_device, resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig
from core.types import JsonValue

from .engines import LocalRerankerEngine, parse_rerank_body


class RerankerLitAPI(ls.LitAPI):
    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/rerank")
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._engine: LocalRerankerEngine = LocalRerankerEngine(cfg)

    def setup(self, device: str | None) -> None:
        litserve_device = device if device is not None else resolve_torch_device(self._cfg)
        d = resolve_rerank_device(self._cfg, litserve_device)
        self._engine.setup(d)

    def decode_request(self, request: RerankQueryPassagesRequest | JsonValue, **kwargs: JsonValue) -> RerankQueryPassagesRequest:
        _ = kwargs
        return parse_rerank_body(request)

    def predict(self, x: RerankQueryPassagesRequest, **kwargs: JsonValue) -> RerankResponseBody:
        _ = kwargs
        return self._engine.rerank(x.query, x.passages, x.model)

    def encode_response(self, output: RerankResponseBody, **kwargs: JsonValue) -> RerankResponseBody:
        _ = kwargs
        return output
