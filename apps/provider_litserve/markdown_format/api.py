"""LitServe API: POST /v1/text/format_markdown."""

from __future__ import annotations

from typing import Any, cast

import litserve as ls

from apps.provider_litserve.markdown_format.engines import (
    MarkdownFormatEngine,
    parse_format_markdown_body,
)
from apps.provider_litserve.shared import resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig


class MarkdownFormatLitAPI(ls.LitAPI):
    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/text/format_markdown")
        self._cfg = cfg
        self._engine = MarkdownFormatEngine(cfg)

    def setup(self, device: str | None) -> None:
        d = device if device is not None else resolve_torch_device(self._cfg)
        self._engine.setup(d)

    def decode_request(self, request, **kwargs):
        """Параметр `request` без аннотации: LitServe подставляет starlette.Request и
        в обработчик передаёт уже распарсенный JSON (dict). Аннотация ``Any`` ломает это
        и приводит к пустому телу и 422 ``text_required``."""
        return parse_format_markdown_body(cast(dict[str, Any], request), cfg=self._cfg)

    def predict(self, x: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return self._engine.format_text(x)

    def encode_response(self, output: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return output
