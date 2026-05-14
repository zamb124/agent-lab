"""
LitServe API реранкера: POST ``/v1/rerank``, тело ``{query, passages}``.
"""

import litserve as ls

from apps.provider_litserve.shared import resolve_rerank_device, resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig

from .engines import LocalRerankerEngine, parse_rerank_body


class RerankerLitAPI(ls.LitAPI):
    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/rerank")
        self._cfg = cfg
        self._engine = LocalRerankerEngine(cfg)

    def setup(self, device) -> None:
        litserve_device = device if device is not None else resolve_torch_device(self._cfg)
        d = resolve_rerank_device(self._cfg, litserve_device)
        self._engine.setup(d)

    def decode_request(self, request, **kwargs):
        return parse_rerank_body(request)

    def predict(self, x, **kwargs):
        return self._engine.rerank(x["query"], x["passages"], x.get("model"))
