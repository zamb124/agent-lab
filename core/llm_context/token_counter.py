"""Token counters used by the LLM context compiler."""

from __future__ import annotations

import json
import re
from typing import Protocol, override

import tiktoken

from core.types import JsonObject


class TokenCounter(Protocol):
    def count_text(self, text: str) -> int:
        ...  # pragma: no cover

    def count_message(self, message: JsonObject) -> int:
        ...  # pragma: no cover


class SimpleTokenCounter:
    """Deterministic fallback counter for tests and dependency-light runtimes."""

    _token_re: re.Pattern[str] = re.compile(r"\S+", flags=re.UNICODE)

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        return len(self._token_re.findall(text))

    def count_message(self, message: JsonObject) -> int:
        role = message.get("role")
        if not isinstance(role, str) or not role:
            raise ValueError("LLM message.role must be a non-empty string")
        if "content" not in message:
            raise ValueError("LLM message.content is required")
        content = message.get("content")
        if isinstance(content, str):
            content_tokens = self.count_text(content)
        else:
            content_tokens = self.count_text(json.dumps(content, ensure_ascii=False, sort_keys=True))
        role_tokens = self.count_text(role)
        return role_tokens + content_tokens


class TiktokenTokenCounter(SimpleTokenCounter):
    """cl100k_base token counter."""

    def __init__(self) -> None:
        self._encoding: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")

    @override
    def count_text(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text))


__all__ = ["SimpleTokenCounter", "TiktokenTokenCounter", "TokenCounter"]
