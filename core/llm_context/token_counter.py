"""Token counters used by the LLM context compiler."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

import tiktoken


class TokenCounter(Protocol):
    def count_text(self, text: str) -> int:
        ...  # pragma: no cover

    def count_message(self, message: dict[str, Any]) -> int:
        ...  # pragma: no cover


class SimpleTokenCounter:
    """Deterministic fallback counter for tests and dependency-light runtimes."""

    _token_re = re.compile(r"\S+", flags=re.UNICODE)

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        return len(self._token_re.findall(text))

    def count_message(self, message: dict[str, Any]) -> int:
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, str):
            content_tokens = self.count_text(content)
        else:
            content_tokens = self.count_text(json.dumps(content, ensure_ascii=False, sort_keys=True))
        role_tokens = self.count_text(str(role or ""))
        return role_tokens + content_tokens


class TiktokenTokenCounter(SimpleTokenCounter):
    """cl100k_base token counter."""

    def __init__(self) -> None:
        self._encoding: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text))


__all__ = ["SimpleTokenCounter", "TiktokenTokenCounter", "TokenCounter"]
