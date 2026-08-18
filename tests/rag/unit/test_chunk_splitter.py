"""Нарезка FileExtract: Chonkie + fixed-token tiktoken strategy."""

import pytest
from pydantic import ValidationError

from core.files.reader.models import (
    ContentMode,
    ExtractBlock,
    ExtractBlockKind,
    FileExtract,
    FileReadKind,
    PageLayout,
    PageLayoutKind,
    ReadLane,
    UniversalPage,
)
from core.rag.chunking import (
    resolve_split_config,
    split_file_extract,
    split_plain_text_fixed_tokens,
)
from core.rag_indexing_schema import IndexProfileConfig, IndexProfileSplitConfig

# Первый импорт chonkie/tree-sitter + session autouse в unit/conftest может превысить дефолтный timeout.
pytestmark = pytest.mark.timeout(120)


def _extract(text: str, *, blocks: list[ExtractBlock] | None = None) -> FileExtract:
    page_blocks = blocks if blocks is not None else (
        [ExtractBlock(kind=ExtractBlockKind.PARAGRAPH, text=text)] if text.strip() else []
    )
    return FileExtract(
        file_id="doc1",
        file_name="doc.txt",
        kind=FileReadKind.TEXT,
        mime_type="text/plain",
        read_lane=ReadLane.TEXT,
        page_layout=PageLayout(kind=PageLayoutKind.VIRTUAL, pages_total=1, page_size=4000),
        pages=[
            UniversalPage(
                index=0,
                label="",
                text=text,
                content_mode=ContentMode.FULL,
                blocks=page_blocks,
            )
        ],
        content_chars_total=len(text),
    )


def _split(text: str, cfg: IndexProfileSplitConfig, *, blocks: list[ExtractBlock] | None = None) -> list[str]:
    chunks = split_file_extract(
        _extract(text, blocks=blocks),
        cfg,
        document_id="doc1",
        document_name="doc.txt",
        namespace="ns",
    )
    return [chunk.content for chunk in chunks]


def test_fixed_tokens_profile_uses_plain_tiktoken_strategy() -> None:
    text = "абв " * 200 + "english words " * 50
    for chunk_size, chunk_overlap in ((64, 8), (120, 20)):
        expected = split_plain_text_fixed_tokens(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        actual = _split(
            text,
            IndexProfileSplitConfig(
                strategy="fixed_tokens",
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
        )
        assert actual == [fragment.strip() for fragment in expected]


def test_semantic_strategy_uses_recursive_chunker() -> None:
    text = "First block.\n\nSecond block here.\n\nThird."
    chunks = _split(text, IndexProfileSplitConfig(strategy="semantic", chunk_size=8, chunk_overlap=0))
    assert len(chunks) >= 1
    joined = "\n".join(chunks)
    assert "First" in joined
    assert "Third" in joined


def test_structure_splits_per_block() -> None:
    text = "short\n" + ("x " * 200)
    blocks = [
        ExtractBlock(kind=ExtractBlockKind.PARAGRAPH, text="short"),
        ExtractBlock(kind=ExtractBlockKind.PARAGRAPH, text="x " * 200),
    ]
    cfg = IndexProfileSplitConfig(strategy="structure", chunk_size=32, chunk_overlap=4)
    chunks = _split(text, cfg, blocks=blocks)
    assert len(chunks) >= 2


def test_sentence_strategy_splits() -> None:
    text = "One. Two. Three. Four."
    chunks = _split(text, IndexProfileSplitConfig(strategy="sentence", chunk_size=32, chunk_overlap=0))
    assert len(chunks) >= 1


def test_code_strategy_splits_python() -> None:
    src = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    chunks = _split(
        src,
        IndexProfileSplitConfig(
            strategy="code",
            chunk_size=64,
            chunk_overlap=0,
            chonkie_code_language="python",
        ),
    )
    joined = "\n".join(chunks)
    assert "def a():" in joined
    assert "def b():" in joined


def test_table_strategy_splits_rows() -> None:
    md = "|a|b|\n|1|2|\n|3|4|\n|5|6|\n"
    chunks = _split(md, IndexProfileSplitConfig(strategy="table", chunk_size=2, chunk_overlap=0))
    assert len(chunks) >= 1


def test_auto_heading_and_table_uses_structure_and_heading_trail() -> None:
    heading = "Section title"
    paragraph = "Body after heading"
    extract = FileExtract(
        file_id="doc1",
        file_name="doc.docx",
        kind=FileReadKind.OFFICE,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        read_lane=ReadLane.TEXT,
        page_layout=PageLayout(kind=PageLayoutKind.NATIVE, pages_total=1, page_size=0),
        pages=[
            UniversalPage(
                index=0,
                label="",
                text=f"{heading}\n{paragraph}",
                content_mode=ContentMode.FULL,
                blocks=[
                    ExtractBlock(kind=ExtractBlockKind.HEADING, text=heading, level=1),
                    ExtractBlock(kind=ExtractBlockKind.PARAGRAPH, text=paragraph),
                    ExtractBlock(kind=ExtractBlockKind.TABLE, text="|a|b|\n|1|2|"),
                ],
            )
        ],
        content_chars_total=len(heading) + len(paragraph),
    )
    split = resolve_split_config(extract, IndexProfileConfig())
    assert split.strategy == "structure"
    chunks = split_file_extract(
        extract,
        split,
        document_id="doc1",
        document_name="doc.docx",
        namespace="ns",
    )
    matching = [chunk for chunk in chunks if paragraph in chunk.content]
    assert matching
    assert matching[0].heading_trail == [heading]
    assert matching[0].page_label == "page_1"


def test_auto_native_table_without_heading_stays_table() -> None:
    table = "|a|b|\n|1|2|"
    extract = FileExtract(
        file_id="sheet1",
        file_name="sheet.xlsx",
        kind=FileReadKind.SPREADSHEET,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        read_lane=ReadLane.TEXT,
        page_layout=PageLayout(kind=PageLayoutKind.NATIVE, pages_total=1, page_size=0),
        pages=[
            UniversalPage(
                index=0,
                label="alpha",
                text=table,
                content_mode=ContentMode.FULL,
                blocks=[ExtractBlock(kind=ExtractBlockKind.TABLE, text=table)],
            )
        ],
        content_chars_total=len(table),
    )
    split = resolve_split_config(extract, IndexProfileConfig())
    assert split.strategy == "table"


def test_split_config_rejects_removed_strategies() -> None:
    with pytest.raises(ValidationError):
        IndexProfileSplitConfig.model_validate(
            {"strategy": "embedding_semantic", "chunk_size": 128, "chunk_overlap": 0}
        )
    with pytest.raises(ValidationError):
        IndexProfileSplitConfig.model_validate(
            {"strategy": "token", "chunk_size": 16, "chunk_overlap": 2}
        )
    with pytest.raises(ValidationError):
        IndexProfileSplitConfig.model_validate(
            {"strategy": "fast", "chunk_size": 12, "chunk_overlap": 0}
        )
