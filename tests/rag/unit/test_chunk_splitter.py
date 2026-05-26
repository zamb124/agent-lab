"""Нарезка: Chonkie + fixed-token tiktoken strategy."""

import pytest
from pydantic import ValidationError

from core.rag.chunking import split_parsed_document, split_plain_text_fixed_tokens
from core.rag.parsed_document import ParsedBlock, ParsedDocument
from core.rag_indexing_schema import IndexProfileSplitConfig

# Первый импорт chonkie/tree-sitter + session autouse в unit/conftest может превысить дефолтный timeout.
pytestmark = pytest.mark.timeout(120)


def test_fixed_tokens_profile_uses_plain_tiktoken_strategy() -> None:
    text = "абв " * 200 + "english words " * 50
    for chunk_size, chunk_overlap in ((64, 8), (120, 20)):
        expected = split_plain_text_fixed_tokens(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        actual = split_parsed_document(
            ParsedDocument(canonical_text=text, blocks=None, source_metadata={}),
            IndexProfileSplitConfig(
                strategy="fixed_tokens",
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
        )
        assert actual == expected


def test_semantic_strategy_uses_recursive_chunker() -> None:
    text = "First block.\n\nSecond block here.\n\nThird."
    chunks = split_parsed_document(
        ParsedDocument(canonical_text=text, blocks=None, source_metadata={}),
        IndexProfileSplitConfig(strategy="semantic", chunk_size=8, chunk_overlap=0),
    )
    assert len(chunks) >= 1
    joined = "\n".join(chunks)
    assert "First" in joined
    assert "Third" in joined


def test_structure_splits_per_block() -> None:
    parsed = ParsedDocument(
        canonical_text="ignored for per-block path",
        blocks=[
            ParsedBlock(kind="paragraph", text="short", level=None, metadata={}),
            ParsedBlock(kind="paragraph", text="x " * 200, level=None, metadata={}),
        ],
        source_metadata={},
    )
    cfg = IndexProfileSplitConfig(strategy="structure", chunk_size=32, chunk_overlap=4)
    chunks = split_parsed_document(parsed, cfg)
    assert len(chunks) >= 2


def test_token_strategy_uses_token_chunker() -> None:
    text = "word " * 80
    chunks = split_parsed_document(
        ParsedDocument(canonical_text=text, blocks=None, source_metadata={}),
        IndexProfileSplitConfig(strategy="token", chunk_size=16, chunk_overlap=2),
    )
    assert len(chunks) >= 2


def test_sentence_strategy_splits() -> None:
    text = "One. Two. Three. Four."
    chunks = split_parsed_document(
        ParsedDocument(canonical_text=text, blocks=None, source_metadata={}),
        IndexProfileSplitConfig(strategy="sentence", chunk_size=32, chunk_overlap=0),
    )
    assert len(chunks) >= 1


def test_code_strategy_splits_python() -> None:
    src = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    chunks = split_parsed_document(
        ParsedDocument(canonical_text=src, blocks=None, source_metadata={}),
        IndexProfileSplitConfig(strategy="code", chunk_size=64, chunk_overlap=0, chonkie_code_language="python"),
    )
    assert len(chunks) >= 1


def test_fast_strategy_splits() -> None:
    text = "line one\nline two\nline three"
    chunks = split_parsed_document(
        ParsedDocument(canonical_text=text, blocks=None, source_metadata={}),
        IndexProfileSplitConfig(strategy="fast", chunk_size=12, chunk_overlap=0),
    )
    assert len(chunks) >= 1


def test_table_strategy_splits_rows() -> None:
    md = "|a|b|\n|1|2|\n|3|4|\n|5|6|\n"
    chunks = split_parsed_document(
        ParsedDocument(canonical_text=md, blocks=None, source_metadata={}),
        IndexProfileSplitConfig(strategy="table", chunk_size=2, chunk_overlap=0),
    )
    assert len(chunks) >= 1


def test_split_config_rejects_removed_embedding_semantic_strategy() -> None:
    with pytest.raises(ValidationError):
        IndexProfileSplitConfig.model_validate(
            {"strategy": "embedding_semantic", "chunk_size": 128, "chunk_overlap": 0}
        )
