"""Суммаризация read_file: structural без LLM и LLM-batch через MockLLM."""

from __future__ import annotations

import base64
import json
from collections.abc import Awaitable, Callable

import pytest

from core.clients.llm.mock import MockLLM
from core.files.checksum import compute_content_checksum_sha256
from core.files.reader import MAX_READ_BUDGET, ContentMode
from core.files.reader.models import NestedContent, ReadAssetKind, ReadFileArgs, UniversalPage
from core.files.reader.render import render_file_result
from core.files.reader.summarizers import resolve_summarizer
from core.files.reader.summarizers.llm import summarize_llm_pages
from core.text_transforms import SUBMIT_PAGE_SUMMARY_TOOL_NAME
from core.types import JsonObject, JsonValue, require_json_array, require_json_object
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

# Совпадает с tests.core.files.corpus.read_helpers._MockLlmQueue
MockLlmQueue = Callable[[list[JsonValue | str]], MockLLM]
MockLlmCapture = Callable[[], Awaitable[list[JsonObject]]]


@pytest.mark.asyncio
@pytest.mark.parametrize(("relative_path", "needle"), _STRUCTURAL_CASES)
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_structural_summarization_without_llm(
    relative_path: str,
    needle: str,
    unique_id: str,
    mock_llm_with_queue: MockLlmQueue,
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
    mock_llm_with_queue: MockLlmQueue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _LLM_TEXT)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    _ = mock_llm_with_queue(["===PAGE 0===\nMOCK_PAGE_SUMMARY"])

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
    mock_llm_with_queue: MockLlmQueue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _LLM_MULTI)
    extract = await build_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    first_three = extract.pages[:3]
    batched_response = "\n".join(
        f"===PAGE {page.index}===\nSummary for page {page.index}" for page in first_three
    )
    _ = mock_llm_with_queue([batched_response])

    summaries = await summarize_llm_pages(first_three, prompt="", model="")
    assert len(summaries) == 3
    assert summaries[0] == "Summary for page 0"
    assert summaries[1] == "Summary for page 1"
    assert summaries[2] == "Summary for page 2"


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_llm_summarization_sends_nested_images_as_media_parts(
    mock_llm_with_queue: MockLlmQueue,
    mock_llm_capture: MockLlmCapture,
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
    _ = mock_llm_with_queue(["===PAGE 0===\nRevenue chart summary"])

    summaries = await summarize_llm_pages([page], prompt="focus on numbers", model="")

    assert summaries == ["Revenue chart summary"]
    calls = await mock_llm_capture()
    assert calls, "expected MockLLM capture for multimodal summarize"
    first_call = require_json_object(calls[0], "mock_llm_capture[0]")
    messages = require_json_array(first_call.get("messages"), "mock_llm_capture[0].messages")
    first_message = require_json_object(messages[0], "mock_llm_capture[0].messages[0]")
    parts = require_json_array(first_message.get("parts"), "mock_llm_capture[0].messages[0].parts")

    def _part_is_file(part: JsonValue) -> bool:
        return isinstance(part, dict) and part.get("type") == "file"

    def _part_has_image_label(part: JsonValue) -> bool:
        if not isinstance(part, dict):
            return False
        if part.get("type") != "text":
            return False
        text = part.get("text")
        return isinstance(text, str) and "Image p0_n1:" in text

    assert any(_part_is_file(part) for part in parts)
    assert any(_part_has_image_label(part) for part in parts)


_PAGE_SCHEMA: JsonObject = require_json_object(
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "items"],
        "additionalProperties": False,
    },
    "test.page_schema",
)


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_llm_structured_summarization_uses_forced_tool(
    mock_llm_with_queue: MockLlmQueue,
) -> None:
    page = UniversalPage(
        index=0,
        label="1",
        text="Soup 350; Salad 200",
        content_mode=ContentMode.FULL,
    )
    _ = mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": SUBMIT_PAGE_SUMMARY_TOOL_NAME,
                "args": {"title": "Menu", "items": ["Soup", "Salad"]},
            }
        ]
    )

    summaries = await summarize_llm_pages(
        [page],
        prompt="extract dishes",
        model="",
        schema=_PAGE_SCHEMA,
    )

    assert len(summaries) == 1
    assert json.loads(summaries[0]) == {"title": "Menu", "items": ["Soup", "Salad"]}


def test_summarization_schema_requires_page_summarizations() -> None:
    with pytest.raises(ValueError, match="page_summarizations"):
        _ = ReadFileArgs(summarization_schema=_PAGE_SCHEMA)


def test_summarization_schema_must_be_object_root() -> None:
    with pytest.raises(ValueError, match="object"):
        _ = ReadFileArgs(
            page_summarizations=True,
            summarization_schema={"type": "array", "items": {"type": "string"}},
        )
