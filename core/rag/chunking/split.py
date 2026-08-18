"""Нарезка FileExtract на чанки: Chonkie + fixed-token tiktoken strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import tiktoken
from chonkie import (
    RecursiveChunker,
    SemanticChunker,
    SentenceChunker,
    TableChunker,
    TokenChunker,
)
from chonkie.refinery import OverlapRefinery
from chonkie.types import Chunk

from core.files.file_ref import FileRef
from core.files.reader.models import (
    ExtractBlock,
    ExtractBlockKind,
    FileExtract,
    PageLayoutKind,
    UniversalPage,
    resolved_page_label,
)
from core.rag.chunking.code_split import split_code_text
from core.rag.models import RAGChunk
from core.rag_indexing_schema import IndexProfileConfig, IndexProfileSplitConfig

_ENCODING_NAME = "cl100k_base"


class _TextChunker(Protocol):
    def __call__(self, text: str) -> list[Chunk]: ...


@dataclass
class _SplitUnit:
    content: str
    page_index: int | None
    page_label: str
    heading_trail: list[str]
    files: list[FileRef]


def _page_label(page: UniversalPage) -> str:
    return resolved_page_label(page.index, page.label)


def split_plain_text_fixed_tokens(
    text_content: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Нарезка по токенам cl100k_base для профиля ``fixed_tokens``."""
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


def resolve_split_config(extract: FileExtract, profile: IndexProfileConfig) -> IndexProfileSplitConfig:
    """Выбирает конкретную strategy. ``auto`` — единственная точка выбора."""
    split = profile.split
    if split.strategy != "auto":
        return split
    return split.model_copy(update={"strategy": _auto_strategy(extract)})


def _auto_strategy(extract: FileExtract) -> str:
    kinds: set[ExtractBlockKind] = set()
    for page in extract.pages:
        for block in page.blocks:
            kinds.add(block.kind)
    if ExtractBlockKind.CODE in kinds:
        return "code"
    if ExtractBlockKind.HEADING in kinds or ExtractBlockKind.FIGURE in kinds:
        return "structure"
    if ExtractBlockKind.TABLE in kinds:
        return "table"
    if extract.page_layout.kind == PageLayoutKind.NATIVE:
        return "structure"
    return "recursive"


def split_file_extract(
    extract: FileExtract,
    split_config: IndexProfileSplitConfig,
    *,
    document_id: str,
    document_name: str,
    namespace: str,
) -> list[RAGChunk]:
    """Единая точка нарезки FileExtract по профилю."""
    if split_config.strategy == "auto":
        raise ValueError("split_file_extract требует resolved strategy, не auto")
    units = _split_units(extract, split_config)
    if not units:
        return []
    total = len(units)
    return [
        RAGChunk(
            content=unit.content,
            document_id=document_id,
            document_name=document_name,
            namespace=namespace,
            chunk_index=index,
            total_chunks=total,
            page_index=unit.page_index,
            page_label=unit.page_label,
            heading_trail=list(unit.heading_trail),
            files=list(unit.files),
            split=split_config,
        )
        for index, unit in enumerate(units)
    ]


def _split_units(extract: FileExtract, split_config: IndexProfileSplitConfig) -> list[_SplitUnit]:
    strategy = split_config.strategy
    if strategy == "structure":
        return _split_structure(extract, split_config)
    return _split_pages_with_text_strategy(extract, split_config)


def _texts_for_strategy(
    text: str,
    split_config: IndexProfileSplitConfig,
    *,
    file_name: str,
) -> list[str]:
    raw = text
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
        chunker = SemanticChunker(chunk_size=split_config.chunk_size)
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
    if strategy == "sentence":
        chunker = SentenceChunker(
            tokenizer=_ENCODING_NAME,
            chunk_size=split_config.chunk_size,
            chunk_overlap=split_config.chunk_overlap,
        )
        return _chunker_to_texts(chunker, raw)
    if strategy == "code":
        return split_code_text(raw, split_config, file_name=file_name)
    if strategy == "table":
        chunker = TableChunker(tokenizer="row", chunk_size=split_config.chunk_size)
        return _chunker_to_texts(chunker, raw)
    raise ValueError(f"Неизвестная split.strategy: {strategy!r}")


def _split_pages_with_text_strategy(
    extract: FileExtract,
    split_config: IndexProfileSplitConfig,
) -> list[_SplitUnit]:
    units: list[_SplitUnit] = []
    for page in extract.pages:
        page_files = list(page.files)
        if not page.text.strip():
            if page_files:
                units.append(
                    _SplitUnit(
                        content="[figure]",
                        page_index=page.index,
                        page_label=_page_label(page),
                        heading_trail=[],
                        files=page_files,
                    )
                )
            continue
        for fragment in _texts_for_strategy(
            page.text, split_config, file_name=extract.file_name
        ):
            units.append(
                _SplitUnit(
                    content=fragment,
                    page_index=page.index,
                    page_label=_page_label(page),
                    heading_trail=[],
                    files=list(page_files),
                )
            )
    return units


def _page_blocks(page_blocks: list[ExtractBlock], page_text: str) -> list[ExtractBlock]:
    if page_blocks:
        return page_blocks
    stripped = page_text.strip()
    if not stripped:
        return []
    return [ExtractBlock(kind=ExtractBlockKind.PARAGRAPH, text=stripped)]


def _merge_files(*groups: list[FileRef]) -> list[FileRef]:
    seen: set[str] = set()
    out: list[FileRef] = []
    for group in groups:
        for item in group:
            key = item.file_id or item.checksum or item.original_name
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def _split_structure(extract: FileExtract, split_config: IndexProfileSplitConfig) -> list[_SplitUnit]:
    chunker = TokenChunker(
        tokenizer=_ENCODING_NAME,
        chunk_size=split_config.chunk_size,
        chunk_overlap=split_config.chunk_overlap,
    )
    units: list[_SplitUnit] = []
    heading_trail: list[str] = []
    for page in extract.pages:
        pending_files: list[FileRef] = list(page.files)
        for block in _page_blocks(page.blocks, page.text):
            if block.kind == ExtractBlockKind.HEADING:
                heading = block.text.strip()
                if not heading:
                    continue
                level = block.level if block.level is not None else 1
                heading_trail = heading_trail[: level - 1]
                heading_trail.append(heading)
                pending_files = _merge_files(pending_files, block.files)
                continue
            if block.kind == ExtractBlockKind.FIGURE:
                pending_files = _merge_files(pending_files, block.files)
                caption = block.text.strip()
                if not caption:
                    continue
                units.append(
                    _SplitUnit(
                        content=caption,
                        page_index=page.index,
                        page_label=_page_label(page),
                        heading_trail=list(heading_trail),
                        files=_merge_files(pending_files),
                    )
                )
                pending_files = []
                continue
            fragment = block.text.strip()
            if not fragment:
                pending_files = _merge_files(pending_files, block.files)
                continue
            attached = _merge_files(pending_files, block.files)
            pending_files = []
            for text in _chunker_to_texts(chunker, fragment):
                units.append(
                    _SplitUnit(
                        content=text,
                        page_index=page.index,
                        page_label=_page_label(page),
                        heading_trail=list(heading_trail),
                        files=list(attached),
                    )
                )
        if pending_files:
            if units and units[-1].page_index == page.index:
                units[-1].files = _merge_files(units[-1].files, pending_files)
            else:
                units.append(
                    _SplitUnit(
                        content="[figure]",
                        page_index=page.index,
                        page_label=_page_label(page),
                        heading_trail=list(heading_trail),
                        files=pending_files,
                    )
                )
    return units
