"""Суммаризация read_file: structural без LLM и LLM-batch через MockLLM."""

from __future__ import annotations

import base64

import pytest

from core.files.checksum import compute_content_checksum_sha256
from core.files.reader import MAX_READ_BUDGET, ContentMode
from core.files.reader.models import NestedContent, ReadAssetKind, UniversalPage
from core.files.reader.render import render_file_result
from core.files.reader.summarizers import resolve_summarizer
from core.files.reader.summarizers.llm import summarize_llm_pages
from tests.core.files.corpus.manifest import POSITIVE
from tests.core.files.corpus.read_helpers import (
    build_corpus_extract,
    read_args_for,
)
from tests.core.files.golden.bytes import png_with_text

_STRUCTURAL_CASES: tuple[tuple[str, str], ...] = (
    ("csv-with-escaped-commas.csv", "columns:"),
    ("stanley-cups.tsv", "columns:"),
    ("simple.json", "element_id"),
    ("factbook.xml", "<"),
    ("simple.yaml", "deer"),
    ("logger.py", "def "),
    ("fake.go", "func "),
    ("stanley-cups.xlsx", "columns:"),
)

_LLM_TEXT = "fake-text.txt"
_LLM_MULTI = "book-war-and-peace-1225p.txt"


@pytest.mark.asyncio
@pytest.mark.parametrize(("relative_path", "needle"), _STRUCTURAL_CASES)
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_structural_summarization_without_llm(
    relative_path: str,
    needle: str,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == relative_path)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    summarizer = resolve_summarizer(kind=extract.kind, file_name=entry.path.name)
    from core.files.reader.summarizers import DEFAULT_SUMMARIZER

    assert summarizer is not DEFAULT_SUMMARIZER

    args = read_args_for(entry, page_summarizations=True)
    result = await render_file_result(extract, args, tool_name="read_file", budget=MAX_READ_BUDGET)

    assert result.page_summarizations_used is True
    assert result.results
    for page_result in result.results:
        assert page_result.content_mode == ContentMode.SUMMARY
    joined = "\n".join(r.result for r in result.results)
    assert needle in joined.lower() or needle in joined


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_llm_summarization_single_page(
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _LLM_TEXT)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    mock_llm_with_queue(["===PAGE 0===\nMOCK_PAGE_SUMMARY"])

    args = read_args_for(entry, page_summarizations=True)
    result = await render_file_result(extract, args, tool_name="read_file", budget=MAX_READ_BUDGET)

    assert result.page_summarizations_used is True
    assert result.results[0].content_mode == ContentMode.SUMMARY
    assert "MOCK_PAGE_SUMMARY" in result.results[0].result


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_llm_summarization_batches_multiple_pages_in_one_call(
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _LLM_MULTI)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    first_three = extract.pages[:3]
    batched_response = "\n".join(
        f"===PAGE {page.index}===\nSummary for page {page.index}" for page in first_three
    )
    mock_llm_with_queue([batched_response])

    summaries = await summarize_llm_pages(first_three, prompt="", model="")
    assert len(summaries) == 3
    assert summaries[0] == "Summary for page 0"
    assert summaries[1] == "Summary for page 1"
    assert summaries[2] == "Summary for page 2"


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_llm_summarization_sends_nested_images_as_media_parts(
    mock_llm_with_queue,
    mock_llm_capture,
    unique_id: str,
) -> None:
    png = png_with_text(f"chart-{unique_id}")
    page = UniversalPage(
        index=0,
        label="1",
        text="Figure caption about revenue",
        content_mode=ContentMode.FULL,
        nested=[
            NestedContent(
                anchor="p0_n1",
                original_name=f"chart-{unique_id}.png",
                content_type="image/png",
                kind=ReadAssetKind.EMBEDDED_IMAGE,
                checksum=compute_content_checksum_sha256(png),
                page_index=0,
                bytes_b64=base64.b64encode(png).decode("utf-8"),
            )
        ],
    )
    mock_llm_with_queue(["===PAGE 0===\nRevenue chart summary"])

    summaries = await summarize_llm_pages([page], prompt="focus on numbers", model="")

    assert summaries == ["Revenue chart summary"]
    calls = await mock_llm_capture()
    assert calls, "expected MockLLM capture for multimodal summarize"
    parts = calls[0]["messages"][0].get("parts") or []
    assert any(isinstance(part, dict) and part.get("type") == "file" for part in parts)
    assert any(
        isinstance(part, dict)
        and part.get("type") == "text"
        and "Image p0_n1:" in str(part.get("text", ""))
        for part in parts
    )
