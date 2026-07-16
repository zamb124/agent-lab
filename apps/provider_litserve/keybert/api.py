"""LitServe API KeyBERT: POST ``/v1/keybert``."""

import litserve as ls

from apps.provider_litserve.provider_litserve_http_schemas import KeybertExtractResponseBody
from apps.provider_litserve.shared import resolve_keybert_device, resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig
from core.types import JsonValue

from .engines import KeybertExtractRequest, LocalKeybertEngine, parse_keybert_body


class KeybertLitAPI(ls.LitAPI):
    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/keybert")
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._engine: LocalKeybertEngine = LocalKeybertEngine(cfg)

    def setup(self, device: str | None) -> None:
        litserve_device = device if device is not None else resolve_torch_device(self._cfg)
        d = resolve_keybert_device(self._cfg, litserve_device)
        self._engine.setup(d)

    def decode_request(self, request: KeybertExtractRequest | JsonValue, **kwargs: JsonValue) -> KeybertExtractRequest:
        _ = kwargs
        return parse_keybert_body(request)

    def predict(self, x: KeybertExtractRequest, **kwargs: JsonValue) -> KeybertExtractResponseBody:
        _ = kwargs
        return self._engine.extract(x)

    def encode_response(self, output: KeybertExtractResponseBody, **kwargs: JsonValue) -> KeybertExtractResponseBody:
        _ = kwargs
        return output
