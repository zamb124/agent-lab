"""Контракт read_file на реальном корпусе unstructured/example-docs без моков.

Проверяется детерминированный конвейер:
  FileReader.read(ReadFileArgs) -> FileExtract -> render_file_result.

Vision/STT: только санкционированные MockLLM и mock STT-tier (см. testing.mdc).
"""

from __future__ import annotations

import pytest

from core.files.reader import (
    MAX_READ_BUDGET,
    ContentMode,
    PageLayoutKind,
    ReadLane,
    StopReason,
)
from core.files.reader.render import render_file_result
from tests.core.files.corpus.manifest import POSITIVE, CorpusFile
from tests.core.files.corpus.read_helpers import (
    assert_checksum_stable,
    assert_extract_read_lane,
    build_corpus_extract,
    expected_layout_kind,
    read_args_for,
    require_corpus_bytes,
)

_BIG_TEXT = "book-war-and-peace-1225p.txt"
_SMALL_TEXT = "book-war-and-peace-1p.txt"
_CSV = "csv-with-escaped-commas.csv"
_XLSX = "2023-half-year-analyses-by-segment.xlsx"

_PIPELINE_POSITIVE = POSITIVE


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", _PIPELINE_POSITIVE, ids=lambda e: e.relative_path)
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_corpus_extract_pipeline_invariants(
    entry: CorpusFile,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    """Universal Pages + read_lane + checksum для каждого текстового файла корпуса."""
    raw = require_corpus_bytes(entry)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )

    assert extract.kind == entry.expected_kind
    assert_extract_read_lane(entry, extract)
    assert extract.page_layout.kind == expected_layout_kind(extract, entry.path.name)
    assert extract.page_layout.pages_total == len(extract.pages)
    assert extract.page_layout.pages_total >= entry.expected_min_pages
    assert_checksum_stable(raw, extract)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", _PIPELINE_POSITIVE, ids=lambda e: e.relative_path)
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_corpus_first_page_render_completes(
    entry: CorpusFile,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    """Первая страница каждого файла укладывается в budget и завершается COMPLETE."""
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    args = read_args_for(entry, page_start=0, page_end=0, budget=MAX_READ_BUDGET)
    rendered = await render_file_result(extract, args, tool_name="read_file", budget=MAX_READ_BUDGET)

    assert rendered.success is True
    assert rendered.pages_processed >= 1
    if extract.page_layout.pages_total <= 1:
        assert rendered.stop_reason == StopReason.COMPLETE
        assert rendered.complete is True
        assert rendered.continuation.has_more is False
        assert rendered.continuation.next_actions == []
    else:
        assert rendered.continuation.has_more is True
        assert rendered.stop_reason in (
            StopReason.PAGE_END_REACHED,
            StopReason.COMPLETE,
            StopReason.BUDGET_EXHAUSTED,
        )


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_big_text_splits_into_virtual_pages(
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _BIG_TEXT)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    assert extract.read_lane == ReadLane.TEXT
    assert extract.page_layout.kind == PageLayoutKind.VIRTUAL
    assert extract.page_layout.page_size > 0
    assert extract.page_layout.pages_total > 1


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_budget_truncates_and_offers_continuation(
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _BIG_TEXT)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    args = read_args_for(entry, budget=2_000)
    result = await render_file_result(extract, args, tool_name="read_file", budget=2_000)

    assert result.stop_reason == StopReason.BUDGET_EXHAUSTED
    assert result.truncated is True
    assert result.complete is False
    total_chars = sum(r.span_chars for r in result.results)
    assert total_chars <= 2_000
    assert result.continuation.has_more is True
    assert result.continuation.next_page_start >= 1
    assert result.continuation.next_actions


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_drilldown_reads_next_window_from_same_extract(
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _BIG_TEXT)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    first = await render_file_result(
        extract, read_args_for(entry, budget=2_000), tool_name="read_file", budget=2_000
    )
    next_start = first.continuation.next_page_start

    second = await render_file_result(
        extract,
        read_args_for(entry, page_start=next_start, page_end=next_start, budget=MAX_READ_BUDGET),
        tool_name="read_file",
        budget=MAX_READ_BUDGET,
    )
    assert second.pages_processed == 1
    assert second.results[0].page == next_start
    assert second.results[0].content_mode == ContentMode.FULL


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_small_text_completes_within_budget(
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _SMALL_TEXT)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    result = await render_file_result(
        extract, read_args_for(entry), tool_name="read_file", budget=MAX_READ_BUDGET
    )
    assert result.complete is True
    assert result.stop_reason == StopReason.COMPLETE
    assert result.continuation.has_more is False


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_csv_virtual_pages_respect_row_boundaries(
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _CSV)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    assert extract.page_layout.kind == PageLayoutKind.VIRTUAL
    for page in extract.pages:
        if page.text and "\n" in page.text:
            assert not page.text.startswith("\n")


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_xlsx_uses_native_page_layout(
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _XLSX)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    assert extract.page_layout.kind == PageLayoutKind.NATIVE
    result = await render_file_result(
        extract, read_args_for(entry), tool_name="read_file", budget=MAX_READ_BUDGET
    )
    assert result.pages_total == extract.page_layout.pages_total


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_page_start_out_of_range_reports_stop_reason(
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _SMALL_TEXT)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    huge = extract.page_layout.pages_total + 5
    result = await render_file_result(
        extract,
        read_args_for(entry, page_start=huge),
        tool_name="read_file",
        budget=MAX_READ_BUDGET,
    )
    assert result.stop_reason == StopReason.OUT_OF_RANGE
    assert result.pages_processed == 0
