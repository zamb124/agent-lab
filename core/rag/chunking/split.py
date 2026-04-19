"""
Нарезка текста на чанки: Chonkie (без LLM и без отдельных эмбеддинг-моделей на этапе сплита) + legacy tiktoken (RAG-40, RAG-41).
"""

from __future__ import annotations

from typing import Any, List

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

from core.rag_indexing_schema import IndexProfileSplitConfig
from core.rag.parsed_document import ParsedDocument

_ENCODING_NAME = "cl100k_base"


def split_plain_text_fixed_tokens(
    text_content: str,
    chunk_size: int,
    chunk_overlap: int,
) -> List[str]:
    """
    Нарезка по токенам cl100k_base (исторический путь PgVectorProvider._chunk_text).

    Используется как эталон для согласования с TokenChunker (RAG-41).
    """
    tokenizer = tiktoken.get_encoding(_ENCODING_NAME)
    tokens = tokenizer.encode(text_content)
    chunks: List[str] = []
    start = 0
    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunk_text = tokenizer.decode(chunk_tokens)
        chunks.append(chunk_text)
        start = end - chunk_overlap
    return chunks


def _chunker_to_texts(chunker: Any, text: str) -> List[str]:
    parts = chunker(text)
    return [c.text for c in parts]


def split_parsed_document(parsed: ParsedDocument, split_config: IndexProfileSplitConfig) -> List[str]:
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
            tokenizer=_ENCODING_NAME,
            chunk_size=split_config.chunk_size,
        )
        parts = chunker(raw)
        if split_config.chunk_overlap <= 0:
            return [c.text for c in parts]
        refined = OverlapRefinery(
            tokenizer=_ENCODING_NAME,
            context_size=split_config.chunk_overlap,
        )(parts)
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
            raise ValueError(
                "split.strategy=code: CodeChunker требует tree-sitter-language-pack "
                "(dependency-groups rag-worker). Установите зависимости и повторите индексацию."
            ) from exc
        return _chunker_to_texts(chunker, raw)

    if strategy == "table":
        chunker = TableChunker(tokenizer="row", chunk_size=split_config.chunk_size)
        return _chunker_to_texts(chunker, raw)

    if strategy == "fast":
        kw: dict[str, Any] = {"chunk_size": split_config.chunk_size}
        if split_config.chonkie_fast_delimiters is not None:
            kw["delimiters"] = split_config.chonkie_fast_delimiters
        chunker = FastChunker(**kw)
        return _chunker_to_texts(chunker, raw)

    raise ValueError(f"Неизвестная split.strategy: {strategy!r}")


def _split_structure(parsed: ParsedDocument, split_config: IndexProfileSplitConfig) -> List[str]:
    blocks = parsed.blocks
    if not blocks:
        chunker = TokenChunker(
            tokenizer=_ENCODING_NAME,
            chunk_size=split_config.chunk_size,
            chunk_overlap=split_config.chunk_overlap,
        )
        return _chunker_to_texts(chunker, parsed.canonical_text)

    chunker = TokenChunker(
        tokenizer=_ENCODING_NAME,
        chunk_size=split_config.chunk_size,
        chunk_overlap=split_config.chunk_overlap,
    )
    out: List[str] = []
    for block in blocks:
        fragment = block.text.strip()
        if not fragment:
            continue
        out.extend(c.text for c in chunker(fragment))
    if not out:
        return _chunker_to_texts(chunker, parsed.canonical_text)
    return out


def fixed_token_chunks_match_legacy(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> bool:
    """Инвариант RAG-41: split_parsed_document(fixed_tokens) == split_plain_text_fixed_tokens."""
    legacy = split_plain_text_fixed_tokens(text, chunk_size, chunk_overlap)
    profile_chunks = split_parsed_document(
        ParsedDocument(
            canonical_text=text,
            blocks=None,
            source_metadata={},
        ),
        IndexProfileSplitConfig(
            strategy="fixed_tokens",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        ),
    )
    return legacy == profile_chunks
