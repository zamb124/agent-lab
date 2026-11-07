"""nested_mode / recursive / pagination для read_file (offline envelope)."""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pytest
from a2a.types import Part

from core.clients.llm.messages import extract_content_parts
from core.files.file_ref import FileRef
from core.files.reader import NestedMode, ReadLane
from core.files.reader.engine import read_files_to_envelope
from core.files.reader.models import NestedContent, ReadAssetKind, ReadFileArgs
from core.files.reader.parts import nested_to_raw_part, parts_from_file_results
from tests.core.files.golden.bytes import (
    docx_heading_table_list_png,
    pdf_multipage_nested,
    pdf_printed_page,
    pdf_text_and_embedded_image,
)

_MOCK_VISION = "MOCK_VISION"
_TEXT_MARKER = "NESTED_TEXT_MARKER"


def _temp_file_ref(raw: bytes, name: str, content_type: str) -> FileRef:
    path = Path(tempfile.mkdtemp()) / name
    path.write_bytes(raw)
    return FileRef(
        original_name=name,
        url=str(path),
        content_type=content_type,
        file_size=len(raw),
    )


@pytest.mark.asyncio
async def test_refs_pdf_text_and_image_no_vision(mock_llm_with_queue) -> None:
    file_ref = _temp_file_ref(
        pdf_text_and_embedded_image(_TEXT_MARKER),
        "nested_text_img.pdf",
        "application/pdf",
    )
    mock_llm_with_queue([_MOCK_VISION])
    args = ReadFileArgs(
        names=[file_ref.original_name],
        nested_mode=NestedMode.REFS,
        recursive=False,
    )
    envelope = await read_files_to_envelope([file_ref], args, tool_name="read_file")
    file_result = envelope.files[0]
    assert file_result.success is True
    assert file_result.read_lane is ReadLane.TEXT
    md = file_result.results[0].result
    assert _TEXT_MARKER in md
    assert "![" in md
    assert _MOCK_VISION not in md
    assert len(file_result.nested) >= 1
    child = file_result.nested[0]
    assert child.content_type.startswith("image/")
    assert "p0_n" in child.anchor


@pytest.mark.asyncio
async def test_parts_pdf_builds_raw_parts(mock_llm_with_queue) -> None:
    file_ref = _temp_file_ref(
        pdf_text_and_embedded_image(_TEXT_MARKER),
        "nested_parts.pdf",
        "application/pdf",
    )
    mock_llm_with_queue([_MOCK_VISION])
    args = ReadFileArgs(names=[file_ref.original_name], nested_mode=NestedMode.PARTS)
    envelope = await read_files_to_envelope([file_ref], args, tool_name="read_file")
    file_result = envelope.files[0]
    md = file_result.results[0].result
    assert "![" in md
    parts = parts_from_file_results(envelope.files)
    assert len(parts) >= 2
    assert parts[0].text.startswith("Image ")
    assert parts[0].text.endswith(":")
    assert parts[1].media_type is not None and parts[1].media_type.startswith("image/")
    assert parts[1].filename is not None and "#" in parts[1].filename
    openai_parts, has_files = extract_content_parts([Part(text=md), *parts])
    assert has_files is True
    assert openai_parts[1]["type"] == "text"
    label = openai_parts[1].get("text")
    assert isinstance(label, str)
    assert label.startswith("Image ")
    assert openai_parts[2]["type"] == "image_url"


def test_parts_forces_recursive_off() -> None:
    args = ReadFileArgs(nested_mode=NestedMode.PARTS, recursive=True)
    assert args.recursive is False
    assert ReadFileArgs(nested_mode=NestedMode.PARTS).recursive is False


def test_read_file_args_null_prompt_strings_from_llm_wire() -> None:
    """LLM tool JSON часто шлёт null в prompt/model вместо \"\"."""
    args = ReadFileArgs.model_validate(
        {
            "names": ["menu_bar.pdf"],
            "nested_mode": "parts",
            "summarization_prompt": None,
            "summarization_model": None,
            "vision_prompt": None,
            "forced_lane": "text",
        }
    )
    assert args.summarization_prompt == ""
    assert args.summarization_model == ""
    assert args.vision_prompt == ""
    assert args.nested_mode is NestedMode.PARTS
    assert args.recursive is False


@pytest.mark.asyncio
async def test_forced_lane_text_no_nested(mock_llm_with_queue) -> None:
    file_ref = _temp_file_ref(
        pdf_text_and_embedded_image(_TEXT_MARKER),
        "text_lane.pdf",
        "application/pdf",
    )
    mock_llm_with_queue([_MOCK_VISION])
    args = ReadFileArgs(
        names=[file_ref.original_name],
        nested_mode=NestedMode.REFS,
        forced_lane=ReadLane.TEXT,
    )
    envelope = await read_files_to_envelope([file_ref], args, tool_name="read_file")
    file_result = envelope.files[0]
    assert file_result.nested == []
    assert _MOCK_VISION not in file_result.results[0].result


@pytest.mark.asyncio
async def test_forced_lane_text_skips_vision_on_scanned_pdf(mock_llm_with_queue) -> None:
    """forced_lane=text не вызывает vision даже если текст страницы непригоден."""
    file_ref = _temp_file_ref(
        pdf_printed_page("SCANNED_MENU_NO_SELECTABLE_TEXT"),
        "scanned_menu.pdf",
        "application/pdf",
    )
    mock_llm_with_queue([_MOCK_VISION])
    args = ReadFileArgs(
        names=[file_ref.original_name],
        nested_mode=NestedMode.REFS,
        forced_lane=ReadLane.TEXT,
    )
    envelope = await read_files_to_envelope([file_ref], args, tool_name="read_file")
    file_result = envelope.files[0]
    assert file_result.success is True
    assert file_result.read_lane is ReadLane.TEXT
    assert _MOCK_VISION not in file_result.results[0].result


@pytest.mark.asyncio
async def test_pagination_nested_window(mock_llm_with_queue) -> None:
    file_ref = _temp_file_ref(
        pdf_multipage_nested("MULTI", pages=3),
        "multi.pdf",
        "application/pdf",
    )
    mock_llm_with_queue([_MOCK_VISION])
    first_env = await read_files_to_envelope(
        [file_ref],
        ReadFileArgs(
            names=[file_ref.original_name],
            page_start=0,
            page_end=0,
            nested_mode=NestedMode.REFS,
            recursive=False,
        ),
        tool_name="read_file",
    )
    first = first_env.files[0]
    assert first.pages_processed == 1
    assert all(item.page_index == 0 for item in first.nested)
    assert first.continuation.has_more is True
    assert first.continuation.next_page_start == 1

    second_env = await read_files_to_envelope(
        [file_ref],
        ReadFileArgs(
            names=[file_ref.original_name],
            page_start=1,
            page_end=1,
            nested_mode=NestedMode.REFS,
            recursive=False,
        ),
        tool_name="read_file",
    )
    second = second_env.files[0]
    assert all(item.page_index == 1 for item in second.nested)
    anchors0 = {item.anchor for item in first.nested}
    anchors1 = {item.anchor for item in second.nested}
    assert anchors0.isdisjoint(anchors1)


@pytest.mark.asyncio
async def test_docx_media_nested_refs(mock_llm_with_queue) -> None:
    file_ref = _temp_file_ref(
        docx_heading_table_list_png("docxmedia"),
        "docx_media.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    mock_llm_with_queue([_MOCK_VISION])
    envelope = await read_files_to_envelope(
        [file_ref],
        ReadFileArgs(
            names=[file_ref.original_name],
            nested_mode=NestedMode.REFS,
            recursive=False,
        ),
        tool_name="read_file",
    )
    nested = envelope.files[0].nested
    assert len(nested) >= 1
    assert nested[0].original_name.startswith(file_ref.original_name + "#")


@pytest.mark.asyncio
async def test_max_nested_zero_omitted_stubs(mock_llm_with_queue) -> None:
    file_ref = _temp_file_ref(
        pdf_text_and_embedded_image(_TEXT_MARKER),
        "max0.pdf",
        "application/pdf",
    )
    mock_llm_with_queue([_MOCK_VISION])
    envelope = await read_files_to_envelope(
        [file_ref],
        ReadFileArgs(
            names=[file_ref.original_name],
            nested_mode=NestedMode.REFS,
            recursive=False,
            max_nested=0,
        ),
        tool_name="read_file",
    )
    file_result = envelope.files[0]
    assert len(file_result.nested) >= 1
    md = file_result.results[0].result
    assert "(omitted:budget)" in md


@pytest.mark.asyncio
async def test_pseudo_text_page_hybrid_or_recursive(
    mock_llm_with_queue,
) -> None:
    """Псевдотекст: page hybrid и/или recursive дают MOCK_VISION в md."""
    file_ref = _temp_file_ref(
        pdf_printed_page("PSEUDO"),
        "pseudo.pdf",
        "application/pdf",
    )
    mock_llm_with_queue([_MOCK_VISION, _MOCK_VISION, _MOCK_VISION])
    envelope = await read_files_to_envelope(
        [file_ref],
        ReadFileArgs(
            names=[file_ref.original_name],
            nested_mode=NestedMode.REFS,
            recursive=True,
        ),
        tool_name="read_file",
    )
    file_result = envelope.files[0]
    assert file_result.success is True
    md = file_result.results[0].result
    assert md.strip()
    assert _MOCK_VISION in md


@pytest.mark.asyncio
async def test_nested_to_raw_part_and_openai() -> None:
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode("ascii")
    item = NestedContent(
        anchor="p0_n1",
        original_name="menu.pdf#p0_n1",
        content_type="image/png",
        kind=ReadAssetKind.EMBEDDED_IMAGE,
        checksum="a" * 64,
        page_index=0,
        bytes_b64=png,
    )
    part = nested_to_raw_part(item)
    content_parts, has_files = extract_content_parts([Part(text="hi"), part])
    assert has_files is True
    assert content_parts[1]["type"] == "image_url"
