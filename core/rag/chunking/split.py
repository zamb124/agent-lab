"""Нарезка текста на чанки: Chonkie + fixed-token tiktoken strategy."""

from __future__ import annotations

from typing import Protocol

import tiktoken
from chonkie import (
    CodeChunker,
    FastChunker,
    RecursiveChunker,
    SemanticChunker,
    SentenceChunker,
    TableChunker,
    TokenChunker,
)
from chonkie.refinery import OverlapRefinery
from chonkie.types import Chunk

from core.rag.parsed_document import ParsedDocument
from core.rag_indexing_schema import IndexProfileSplitConfig

_ENCODING_NAME = "cl100k_base"


class _TextChunker(Protocol):
    def __call__(self, text: str) -> list[Chunk]: ...


def split_plain_text_fixed_tokens(
    text_content: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """
    Нарезка по токенам cl100k_base для профиля ``fixed_tokens``.
    """
    tokenizer = tiktoken.get_encoding(_ENCODING_NAME)
    tokens = tokenizer.encode(text_content)
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunk_text = tokenizer.decode(chunk_tokens)
        chunks.append(chunk_text)
        start = end - chunk_overlap
    return chunks


def _chunker_to_texts(chunker: _TextChunker, text: str) -> list[str]:
    parts = chunker(text)
    return [c.text for c in parts]


def split_parsed_document(parsed: ParsedDocument, split_config: IndexProfileSplitConfig) -> list[str]:
    """
    Единая точка нарезки по профилю.

    Стратегии см. ``IndexProfileSplitConfig.strategy`` и раздел «Нарезка чанков» в ``rag.mdc``.
    """
    raw = parsed.canonical_text
    if not raw.strip():
        return []

    strategy = split_config.strategy
    if strategy == "fixed_tokens":
        return split_plain_text_fixed_tokens(
            raw,
            split_config.chunk_size,
            split_config.chunk_overlap,
        )

    if strategy == "semantic":
        chunker = SemanticChunker(
            chunk_size=split_config.chunk_size,
        )
        parts = chunker(raw)
        if split_config.chunk_overlap <= 0:
            return [c.text for c in parts]
        refinery = OverlapRefinery(
            tokenizer=_ENCODING_NAME,
            context_size=split_config.chunk_overlap,
        )
        refined = refinery(parts)
        return [c.text for c in refined]

    if strategy == "recursive":
        chunker = RecursiveChunker(
            tokenizer=_ENCODING_NAME,
            chunk_size=split_config.chunk_size,
        )
        return _chunker_to_texts(chunker, raw)

    if strategy == "structure":
        return _split_structure(parsed, split_config)

    if strategy == "token":
        chunker = TokenChunker(
            tokenizer=_ENCODING_NAME,
            chunk_size=split_config.chunk_size,
            chunk_overlap=split_config.chunk_overlap,
        )
        return _chunker_to_texts(chunker, raw)

    if strategy == "sentence":
        chunker = SentenceChunker(
            tokenizer=_ENCODING_NAME,
            chunk_size=split_config.chunk_size,
            chunk_overlap=split_config.chunk_overlap,
        )
        return _chunker_to_texts(chunker, raw)

    if strategy == "code":
        try:
            chunker = CodeChunker(
                tokenizer=_ENCODING_NAME,
                chunk_size=split_config.chunk_size,
                language=split_config.chonkie_code_language,
            )
        except ImportError as exc:
            message = (
                "split.strategy=code: CodeChunker требует tree-sitter-language-pack "
                + "(dependency-groups rag-worker). Установите зависимости и повторите индексацию."
            )
            raise ValueError(message) from exc
        return _chunker_to_texts(chunker, raw)

    if strategy == "table":
        chunker = TableChunker(tokenizer="row", chunk_size=split_config.chunk_size)
        return _chunker_to_texts(chunker, raw)

    if strategy == "fast":
        if split_config.chonkie_fast_delimiters is None:
            chunker = FastChunker(chunk_size=split_config.chunk_size)
        else:
            chunker = FastChunker(
                chunk_size=split_config.chunk_size,
                delimiters=split_config.chonkie_fast_delimiters,
            )
        return _chunker_to_texts(chunker, raw)

    raise ValueError(f"Неизвестная split.strategy: {strategy!r}")


def _split_structure(parsed: ParsedDocument, split_config: IndexProfileSplitConfig) -> list[str]:
    blocks = parsed.blocks
    chunker = TokenChunker(
        tokenizer=_ENCODING_NAME,
        chunk_size=split_config.chunk_size,
        chunk_overlap=split_config.chunk_overlap,
    )
    if not blocks:
        return _chunker_to_texts(chunker, parsed.canonical_text)
    out: list[str] = []
    for block in blocks:
        fragment = block.text.strip()
        if not fragment:
            continue
        out.extend(_chunker_to_texts(chunker, fragment))
    if not out:
        return _chunker_to_texts(chunker, parsed.canonical_text)
    return out
