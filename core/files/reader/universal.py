"""Нормализация FileReadResult в Universal Pages (единый постраничный слой для всех типов).

Native units (страницы PDF, листы XLS, слайды PPTX, главы EPUB) сохраняются как есть.
Сплошной контент (txt/csv/json/html/docx-one-blob/аудио-транскрипт) нарезается на
virtual pages окном page_size; для CSV/TSV — по границам строк, не разрывая запись.
"""

from __future__ import annotations

from pathlib import Path

from core.files.reader.models import (
    DEFAULT_VIRTUAL_PAGE_SIZE,
    ContentMode,
    FileExtract,
    FileReadKind,
    FileReadResult,
    PageLayout,
    PageLayoutKind,
    ReadLane,
    UniversalPage,
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
    """True если формат уже постраничный (несколько native units)."""
    if result.detected_kind == FileReadKind.IMAGE:
        return True
    if result.detected_kind in (FileReadKind.PDF, FileReadKind.SPREADSHEET):
        return True
    if result.detected_kind == FileReadKind.OFFICE and len(result.pages) > 1:
        return True
    return False


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

    pages: list[UniversalPage] = []
    if _is_natively_paginated(result):
        layout_kind = PageLayoutKind.NATIVE
        effective_page_size = 0
        for page in result.pages:
            pages.append(
                UniversalPage(
                    index=len(pages),
                    label=page.label or "",
                    text=page.text,
                    content_mode=content_mode,
                )
            )
    else:
        layout_kind = PageLayoutKind.VIRTUAL
        effective_page_size = page_size
        ext = Path(file_name).suffix.lower()
        on_row_boundary = ext in _ROW_DELIMITED_EXTENSIONS
        joined = "\n\n".join(p.text for p in result.pages) if len(result.pages) > 1 else (
            result.pages[0].text if result.pages else ""
        )
        for window in _split_into_windows(
            joined, page_size=page_size, on_row_boundary=on_row_boundary
        ):
            pages.append(
                UniversalPage(index=len(pages), label="", text=window, content_mode=content_mode)
            )

    if not pages:
        pages.append(UniversalPage(index=0, label="", text="", content_mode=content_mode))

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
