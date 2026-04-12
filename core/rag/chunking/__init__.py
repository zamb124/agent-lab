"""Нарезка текста (Chonkie + legacy tiktoken)."""

from .split import (
    fixed_token_chunks_match_legacy,
    split_parsed_document,
    split_plain_text_fixed_tokens,
)

__all__ = [
    "fixed_token_chunks_match_legacy",
    "split_parsed_document",
    "split_plain_text_fixed_tokens",
]
