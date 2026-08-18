"""Нормализация FileReadResult в Universal Pages (единый постраничный слой для всех типов).

Native units (страницы PDF, листы XLS, слайды PPTX, главы EPUB) сохраняются как есть.
Сплошной контент (txt/csv/json/html/office-blob без blocks/assets) нарезается на
virtual pages окном page_size; для CSV/TSV — по границам строк, не разрывая запись.
Office с blocks/assets у reader'а (в том числе .doc/.p7s) остаётся NATIVE — `keep_reader_pages`.
"""

from __future__ import annotations

from pathlib import Path

from core.files.reader.models import (
    DEFAULT_VIRTUAL_PAGE_SIZE,
    ContentMode,
    ExtractBlock,
    ExtractBlockKind,
    FileExtract,
    FileReadKind,
    FileReadResult,
    PageLayout,
    PageLayoutKind,
    ReadLane,
    ReadPage,
    UniversalPage,
    default_page_label,
    resolved_page_label,
)

_ROW_DELIMITED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".tsv"})


def read_lane_for_kind(kind: FileReadKind) -> ReadLane:
    """Дефолтный read_lane по типу файла (без учёта forced lane)."""
    if kind == FileReadKind.IMAGE:
        return ReadLane.VISION
    if kind in (FileReadKind.AUDIO, FileReadKind.VIDEO):
        return ReadLane.STT
    return ReadLane.TEXT


_read_lane_for_kind = read_lane_for_kind


def _content_mode_for_lane(lane: ReadLane) -> ContentMode:
    if lane == ReadLane.VISION:
        return ContentMode.VISION
    if lane == ReadLane.STT:
        return ContentMode.STT
    if lane == ReadLane.HYBRID:
        return ContentMode.HYBRID
    return ContentMode.FULL


def _is_natively_paginated(result: FileReadResult) -> bool:
    """True если reader уже отдал native units (страницы, листы, слайды, главы)."""
    if result.detected_kind == FileReadKind.IMAGE:
        return True
    if result.detected_kind in (FileReadKind.PDF, FileReadKind.SPREADSHEET):
        return True
    if result.detected_kind == FileReadKind.OFFICE and len(result.pages) > 1:
        return True
    return False


def keep_reader_pages(result: FileReadResult) -> bool:
    if _is_natively_paginated(result):
        return True
    return any(page.blocks or page.assets for page in result.pages)


def page_layout_kind_for_result(result: FileReadResult) -> PageLayoutKind:
    """NATIVE, если reader уже отдал units/структуру; иначе VIRTUAL-окна."""
    return PageLayoutKind.NATIVE if keep_reader_pages(result) else PageLayoutKind.VIRTUAL


def read_pages_for_layout(
    result: FileReadResult,
    *,
    file_name: str,
    page_size: int = DEFAULT_VIRTUAL_PAGE_SIZE,
) -> list[ReadPage]:
    """Native units и страницы со структурой/ассетами — как есть; сплошной текст — окна."""
    if keep_reader_pages(result):
        return list(result.pages)

    ext = Path(file_name).suffix.lower()
    on_row_boundary = ext in _ROW_DELIMITED_EXTENSIONS
    joined = "\n\n".join(page.text for page in result.pages) if len(result.pages) > 1 else (
        result.pages[0].text if result.pages else ""
    )
    windows = _split_into_windows(joined, page_size=page_size, on_row_boundary=on_row_boundary)
    pages: list[ReadPage] = []
    for index, window in enumerate(windows):
        blocks: list[ExtractBlock] = []
        if window.strip():
            blocks.append(ExtractBlock(kind=ExtractBlockKind.PARAGRAPH, text=window))
        pages.append(
            ReadPage(
                index=index,
                text=window,
                assets=[],
                label=default_page_label(index),
                blocks=blocks,
            )
        )
    return pages


def _split_into_windows(text: str, *, page_size: int, on_row_boundary: bool) -> list[str]:
    if not text:
        return [""]
    if len(text) <= page_size:
        return [text]
    if not on_row_boundary:
        return [text[i : i + page_size] for i in range(0, len(text), page_size)]

    windows: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current and current_len + len(line) > page_size:
            windows.append("".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        windows.append("".join(current))
    return windows or [""]


def build_file_extract(
    result: FileReadResult,
    *,
    file_name: str,
    file_id: str | None,
    page_size: int = DEFAULT_VIRTUAL_PAGE_SIZE,
) -> FileExtract:
    lane = _read_lane_for_kind(result.detected_kind)
    content_mode = _content_mode_for_lane(lane)
    mime_type = result.content_type or "application/octet-stream"

    source_pages = read_pages_for_layout(result, file_name=file_name, page_size=page_size)
    layout_kind = page_layout_kind_for_result(result)
    effective_page_size = 0 if layout_kind is PageLayoutKind.NATIVE else page_size
    pages: list[UniversalPage] = []
    for page in source_pages:
        pages.append(
            UniversalPage(
                index=len(pages),
                label=resolved_page_label(page.index, page.label),
                text=page.text,
                content_mode=content_mode,
                blocks=list(page.blocks),
            )
        )

    if not pages:
        pages.append(
            UniversalPage(
                index=0,
                label=default_page_label(0),
                text="",
                content_mode=content_mode,
            )
        )

    content_chars_total = sum(len(p.text) for p in pages)

    return FileExtract(
        file_id=file_id,
        file_name=file_name,
        kind=result.detected_kind,
        mime_type=mime_type,
        read_lane=lane,
        page_layout=PageLayout(
            kind=layout_kind, pages_total=len(pages), page_size=effective_page_size
        ),
        pages=pages,
        content_chars_total=content_chars_total,
        warnings=list(result.warnings),
        source_checksum=result.source_checksum,
    )
