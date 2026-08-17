"""Проверка канонической FileExtract без twin-модели."""

from __future__ import annotations

from core.files.checksum import compute_content_checksum_sha256
from core.files.file_ref import FileRef
from core.files.reader.models import (
    ExtractBlock,
    ExtractBlockKind,
    FileExtract,
    FileReadKind,
    PageLayoutKind,
    ReadLane,
)
from core.files.service import FilesService

_MOCK_VISION = "MOCK_VISION"


def extract_blocks(extract: FileExtract) -> list[ExtractBlock]:
    blocks: list[ExtractBlock] = []
    for page in extract.pages:
        blocks.extend(page.blocks)
    return blocks


def extract_file_refs(extract: FileExtract) -> list[FileRef]:
    refs: list[FileRef] = []
    seen: set[str] = set()
    for page in extract.pages:
        for file_ref in [*page.files, *[ref for block in page.blocks for ref in block.files]]:
            file_id = file_ref.file_id
            if file_id is None or file_id in seen:
                continue
            seen.add(file_id)
            refs.append(file_ref)
    return refs


async def assert_file_extract(
    extract: FileExtract,
    *,
    raw: bytes,
    kind: FileReadKind,
    read_lane: ReadLane,
    layout_kind: PageLayoutKind,
    marker: str,
    required_block_kinds: frozenset[ExtractBlockKind],
    persist_assets: bool,
    expect_mock_vision: bool,
    require_unique_marker: bool = True,
    files_service: FilesService | None = None,
    min_pages: int = 1,
    expected_labels: tuple[str, ...] | None = None,
    label_prefix: str | None = None,
) -> None:
    assert extract.kind == kind
    assert extract.read_lane == read_lane
    assert extract.page_layout.kind == layout_kind
    assert extract.page_layout.pages_total == len(extract.pages)
    assert len(extract.pages) >= min_pages
    assert extract.source_checksum == compute_content_checksum_sha256(raw)
    canonical = extract.canonical_text()
    if expect_mock_vision:
        assert _MOCK_VISION in canonical
    else:
        assert _MOCK_VISION not in canonical
    if require_unique_marker:
        assert marker in canonical

    blocks = extract_blocks(extract)
    present_kinds = {block.kind for block in blocks}
    missing = required_block_kinds - present_kinds
    assert missing == set(), f"нет блоков {sorted(kind.value for kind in missing)}"
    for required_kind in required_block_kinds:
        if required_kind is ExtractBlockKind.FIGURE:
            continue
        if not require_unique_marker:
            continue
        kind_texts = [block.text for block in blocks if block.kind is required_kind]
        assert any(marker in text for text in kind_texts), (
            f"маркер {marker!r} не найден в блоках {required_kind.value}"
        )

    if expected_labels is not None:
        labels = tuple(page.label for page in extract.pages)
        assert labels == expected_labels
    if label_prefix is not None:
        assert all(page.label.startswith(label_prefix) for page in extract.pages)

    figure_blocks = [block for block in blocks if block.kind is ExtractBlockKind.FIGURE]
    page_files = [file_ref for page in extract.pages for file_ref in page.files]
    if persist_assets:
        if files_service is None:
            raise ValueError("persist_assets требует files_service")
        assert figure_blocks, "persist: нет figure при картинке в golden"
        for figure in figure_blocks:
            assert len(figure.files) == 1
            file_ref = figure.files[0]
            file_id = file_ref.file_id
            if file_id is None:
                raise AssertionError("figure без FileRef.file_id при persist")
            record = await files_service.get(file_id)
            assert record.file_id == file_id
        assert page_files, "persist: UniversalPage.files пуст"
        for file_ref in page_files:
            file_id = file_ref.file_id
            if file_id is None:
                raise AssertionError("page.files без file_id при persist")
            record = await files_service.get(file_id)
            assert record.file_id == file_id
        return
    assert page_files == []
    for figure in figure_blocks:
        assert figure.files == []
