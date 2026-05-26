"""Нарезка текста (Chonkie + fixed-token tiktoken strategy)."""

from .split import (
    split_parsed_document,
    split_plain_text_fixed_tokens,
)

__all__ = [
    "split_parsed_document",
    "split_plain_text_fixed_tokens",
]
