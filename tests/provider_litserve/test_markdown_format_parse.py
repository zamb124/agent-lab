"""Парсинг тела POST /v1/text/format_markdown."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from apps.provider_litserve.markdown_format.api import MarkdownFormatLitAPI
from apps.provider_litserve.markdown_format.engines import parse_format_markdown_body
from core.config.models import ProviderLitserveInfraConfig


def _cfg() -> ProviderLitserveInfraConfig:
    return ProviderLitserveInfraConfig(
        llm_model_ids=["Qwen/Qwen2.5-Coder-0.5B"],
        markdown_default_api_model_id="Qwen/Qwen2.5-Coder-0.5B",
    )


def test_parse_minimal_body() -> None:
    parsed = parse_format_markdown_body({"text": "  hello  "}, cfg=_cfg())
    assert parsed["text"] == "hello"
    assert parsed["model_id"] == "Qwen/Qwen2.5-Coder-0.5B"


def test_parse_rejects_empty_text() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_format_markdown_body({"text": "   "}, cfg=_cfg())
    assert exc.value.status_code == 422


def test_parse_overrides() -> None:
    parsed = parse_format_markdown_body(
        {
            "text": "x",
            "model": "Qwen/Qwen2.5-Coder-0.5B",
            "max_chunk_chars": 2000,
            "max_microbatch": 2,
            "max_new_tokens": 128,
            "chunk_join": "---",
        },
        cfg=_cfg(),
    )
    assert parsed["max_chunk_chars"] == 2000
    assert parsed["max_microbatch"] == 2
    assert parsed["max_new_tokens"] == 128
    assert parsed["chunk_join"] == "---"


def test_markdown_format_litapi_decode_request_uses_parsed_json_dict() -> None:
    """Как у EmbeddingLitAPI: без аннотации на `request` LitServe передаёт сюда dict (после json())."""
    api = MarkdownFormatLitAPI(_cfg())
    parsed = api.decode_request({"text": "  hi  "})
    assert parsed["text"] == "hi"


def test_parse_max_chunk_out_of_range() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_format_markdown_body({"text": "ok", "max_chunk_chars": 10}, cfg=_cfg())
    assert exc.value.status_code == 422
