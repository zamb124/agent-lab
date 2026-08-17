"""Тесты page_text_usable и обхода устаревшего пустого TEXT-кэша."""

from __future__ import annotations

from core.files.reader.engine import cached_extract_is_stale
from core.files.reader.models import (
    ContentMode,
    FileExtract,
    FileReadKind,
    PageLayout,
    PageLayoutKind,
    ReadLane,
    UniversalPage,
)
from core.files.reader.service import page_text_for_merge, page_text_usable


def test_page_text_usable_rejects_short_garbage() -> None:
    assert page_text_usable("") is False
    assert page_text_usable("   ") is False
    assert page_text_usable("стр. 1") is False
    assert page_text_usable("Hello PDF text marker") is False
    assert page_text_usable("Hello World Test Text\nSecond line of text here\nRotated page fixture\n") is True


def test_page_text_for_merge_keeps_short_clean_text() -> None:
    assert page_text_for_merge("") == ""
    assert page_text_for_merge("стр. 1") == ""
    assert page_text_for_merge("Hello PDF text marker") == "Hello PDF text marker"


def test_cached_extract_is_stale_for_empty_text_lane() -> None:
    extract = FileExtract(
        file_id="f1",
        file_name="scan.pdf",
        kind=FileReadKind.PDF,
        read_lane=ReadLane.TEXT,
        page_layout=PageLayout(kind=PageLayoutKind.NATIVE, pages_total=1, page_size=0),
        pages=[UniversalPage(index=0, label="page_1", text="", content_mode=ContentMode.FULL)],
        content_chars_total=0,
        warnings=[],
        source_checksum="abc",
    )
    assert cached_extract_is_stale(extract) is True


def test_cached_extract_not_stale_for_hybrid_lane() -> None:
    extract = FileExtract(
        file_id="f1",
        file_name="scan.pdf",
        kind=FileReadKind.PDF,
        read_lane=ReadLane.HYBRID,
        page_layout=PageLayout(kind=PageLayoutKind.NATIVE, pages_total=1, page_size=0),
        pages=[
            UniversalPage(
                index=0,
                label="page_1",
                text="MOCK_VISION",
                content_mode=ContentMode.HYBRID,
            )
        ],
        content_chars_total=11,
        warnings=[],
        source_checksum="abc",
    )
    assert cached_extract_is_stale(extract) is False
