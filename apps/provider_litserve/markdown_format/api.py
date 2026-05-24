"""LitServe API: POST /v1/text/format_markdown."""

from __future__ import annotations

import litserve as ls

from apps.provider_litserve.markdown_format.engines import (
    MarkdownFormatEngine,
    MarkdownFormatParams,
    MarkdownFormatResult,
    parse_format_markdown_body,
)
from apps.provider_litserve.shared import resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig
from core.types import JsonObject, JsonValue


class MarkdownFormatLitAPI(ls.LitAPI):
    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/text/format_markdown")
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._engine: MarkdownFormatEngine = MarkdownFormatEngine(cfg)

    def setup(self, device: str | None) -> None:
        d = device if device is not None else resolve_torch_device(self._cfg)
        self._engine.setup(d)

    def decode_request(self, request: JsonObject, **kwargs: JsonValue) -> MarkdownFormatParams:
        _ = kwargs
        return parse_format_markdown_body(request, cfg=self._cfg)

    def predict(self, x: MarkdownFormatParams, **kwargs: JsonValue) -> MarkdownFormatResult:
        _ = kwargs
        return self._engine.format_text(x)

    def encode_response(
        self,
        output: MarkdownFormatResult,
        **kwargs: JsonValue,
    ) -> MarkdownFormatResult:
        _ = kwargs
        return output
