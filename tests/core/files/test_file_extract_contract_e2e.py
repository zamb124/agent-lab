"""Golden-контракт FileReader.read через FilesService/S3."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from apps.frontend.container import FrontendContainer
from apps.rag.container import get_rag_container
from core.files.reader.models import (
    ExtractBlockKind,
    FileExtract,
    FileReadKind,
    PageLayoutKind,
    ReadLane,
)
from tests.core.files.corpus.helpers import corpus_stt_company_id
from tests.core.files.golden.assert_extract import assert_file_extract
from tests.core.files.golden.bytes import (
    csv_bytes,
    docx_heading_table_list_png,
    eml_message,
    epub_two_chapters,
    html_bytes,
    jpg_printed_marker,
    marker,
    msg_with_marker,
    odt_bytes,
    pdf_long_text_with_image,
    pdf_scanned_raster,
    pdf_short_text_with_image,
    png_printed_marker,
    pptx_two_slides_table_png,
    rtf_bytes,
    sqlite_schema,
    txt_bytes,
    wav_corpus_bytes,
    xls_table,
    xlsx_two_sheets,
)
from tests.core.files.golden.store import (
    configure_file_reader_persist,
    read_stored_extract,
    store_golden_file,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.timeout(120),
    pytest.mark.usefixtures("file_reader_billing_service"),
]

_PARAGRAPH = ExtractBlockKind.PARAGRAPH
_HEADING = ExtractBlockKind.HEADING
_TABLE = ExtractBlockKind.TABLE
_LIST = ExtractBlockKind.LIST
_FIGURE = ExtractBlockKind.FIGURE


@dataclass(frozen=True, slots=True)
class GoldenReadCase:
    case_id: str
    suffix: str
    build: Callable[[str], bytes]
    kind: FileReadKind
    read_lane: ReadLane
    layout_kind: PageLayoutKind
    marker_prefix: str
    required_block_kinds: frozenset[ExtractBlockKind]
    expect_mock_vision: bool
    min_pages: int = 1
    expected_labels: tuple[str, ...] | None = None
    label_prefix: str | None = None
    stt: bool = False
    marker_from_unique_id: bool = True
    require_unique_marker: bool = True


_CASES: tuple[GoldenReadCase, ...] = (
    GoldenReadCase(
        case_id="txt",
        suffix=".txt",
        build=txt_bytes,
        kind=FileReadKind.TEXT,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.VIRTUAL,
        marker_prefix="GOLDEN_TXT",
        required_block_kinds=frozenset({_PARAGRAPH}),
        expect_mock_vision=False,
    ),
    GoldenReadCase(
        case_id="csv",
        suffix=".csv",
        build=csv_bytes,
        kind=FileReadKind.TEXT,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.VIRTUAL,
        marker_prefix="GOLDEN_CSV",
        required_block_kinds=frozenset({_PARAGRAPH}),
        expect_mock_vision=False,
    ),
    GoldenReadCase(
        case_id="html",
        suffix=".html",
        build=html_bytes,
        kind=FileReadKind.HTML,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.VIRTUAL,
        marker_prefix="GOLDEN_HTML",
        required_block_kinds=frozenset({_PARAGRAPH}),
        expect_mock_vision=False,
    ),
    GoldenReadCase(
        case_id="docx",
        suffix=".docx",
        build=docx_heading_table_list_png,
        kind=FileReadKind.OFFICE,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_DOCX",
        required_block_kinds=frozenset({_HEADING, _TABLE, _LIST, _FIGURE}),
        expect_mock_vision=False,
    ),
    GoldenReadCase(
        case_id="pptx",
        suffix=".pptx",
        build=pptx_two_slides_table_png,
        kind=FileReadKind.OFFICE,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_PPTX",
        required_block_kinds=frozenset({_TABLE, _FIGURE}),
        expect_mock_vision=False,
        min_pages=2,
        expected_labels=("slide_1", "slide_2"),
    ),
    GoldenReadCase(
        case_id="xlsx",
        suffix=".xlsx",
        build=xlsx_two_sheets,
        kind=FileReadKind.SPREADSHEET,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_XLSX",
        required_block_kinds=frozenset({_TABLE}),
        expect_mock_vision=False,
        min_pages=2,
        expected_labels=("alpha", "beta"),
    ),
    GoldenReadCase(
        case_id="xls",
        suffix=".xls",
        build=xls_table,
        kind=FileReadKind.SPREADSHEET,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_XLS",
        required_block_kinds=frozenset({_TABLE}),
        expect_mock_vision=False,
    ),
    GoldenReadCase(
        case_id="epub",
        suffix=".epub",
        build=epub_two_chapters,
        kind=FileReadKind.OFFICE,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_EPUB",
        required_block_kinds=frozenset({_PARAGRAPH}),
        expect_mock_vision=False,
        min_pages=2,
        label_prefix="chapter_",
    ),
    GoldenReadCase(
        case_id="eml",
        suffix=".eml",
        build=eml_message,
        kind=FileReadKind.OFFICE,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.VIRTUAL,
        marker_prefix="GOLDEN_EML",
        required_block_kinds=frozenset({_PARAGRAPH}),
        expect_mock_vision=False,
    ),
    GoldenReadCase(
        case_id="msg",
        suffix=".msg",
        build=msg_with_marker,
        kind=FileReadKind.OFFICE,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.VIRTUAL,
        marker_prefix="GOLDEN_MSG",
        required_block_kinds=frozenset({_PARAGRAPH}),
        expect_mock_vision=False,
    ),
    GoldenReadCase(
        case_id="rtf",
        suffix=".rtf",
        build=rtf_bytes,
        kind=FileReadKind.OFFICE,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.VIRTUAL,
        marker_prefix="GOLDEN_RTF",
        required_block_kinds=frozenset({_PARAGRAPH}),
        expect_mock_vision=False,
    ),
    GoldenReadCase(
        case_id="odt",
        suffix=".odt",
        build=odt_bytes,
        kind=FileReadKind.OFFICE,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.VIRTUAL,
        marker_prefix="GOLDEN_ODT",
        required_block_kinds=frozenset({_PARAGRAPH}),
        expect_mock_vision=False,
    ),
    GoldenReadCase(
        case_id="doc",
        suffix=".doc",
        build=docx_heading_table_list_png,
        kind=FileReadKind.OFFICE,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_DOCX",
        required_block_kinds=frozenset({_HEADING, _TABLE, _LIST, _FIGURE}),
        expect_mock_vision=False,
    ),
    GoldenReadCase(
        case_id="sqlite",
        suffix=".sqlite",
        build=sqlite_schema,
        kind=FileReadKind.DATA_TABLE,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.VIRTUAL,
        marker_prefix="golden",
        required_block_kinds=frozenset({_PARAGRAPH}),
        expect_mock_vision=False,
        marker_from_unique_id=False,
    ),
    GoldenReadCase(
        case_id="pdf_text",
        suffix=".pdf",
        build=pdf_long_text_with_image,
        kind=FileReadKind.PDF,
        read_lane=ReadLane.TEXT,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_PDF_TEXT",
        required_block_kinds=frozenset({_FIGURE}),
        expect_mock_vision=False,
        expected_labels=("page_1",),
    ),
    GoldenReadCase(
        case_id="pdf_scan",
        suffix=".pdf",
        build=pdf_scanned_raster,
        kind=FileReadKind.PDF,
        read_lane=ReadLane.HYBRID,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_PDF_SCAN",
        required_block_kinds=frozenset({_FIGURE}),
        expect_mock_vision=True,
        expected_labels=("page_1",),
        require_unique_marker=False,
    ),
    GoldenReadCase(
        case_id="pdf_short",
        suffix=".pdf",
        build=pdf_short_text_with_image,
        kind=FileReadKind.PDF,
        read_lane=ReadLane.HYBRID,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_PDF_SHORT",
        required_block_kinds=frozenset({_FIGURE}),
        expect_mock_vision=True,
        expected_labels=("page_1",),
    ),
    GoldenReadCase(
        case_id="png",
        suffix=".png",
        build=png_printed_marker,
        kind=FileReadKind.IMAGE,
        read_lane=ReadLane.VISION,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_PNG",
        required_block_kinds=frozenset({_FIGURE}),
        expect_mock_vision=True,
        require_unique_marker=False,
    ),
    GoldenReadCase(
        case_id="jpg",
        suffix=".jpg",
        build=jpg_printed_marker,
        kind=FileReadKind.IMAGE,
        read_lane=ReadLane.VISION,
        layout_kind=PageLayoutKind.NATIVE,
        marker_prefix="GOLDEN_JPG",
        required_block_kinds=frozenset({_FIGURE}),
        expect_mock_vision=True,
        require_unique_marker=False,
    ),
    GoldenReadCase(
        case_id="wav",
        suffix=".wav",
        build=wav_corpus_bytes,
        kind=FileReadKind.AUDIO,
        read_lane=ReadLane.STT,
        layout_kind=PageLayoutKind.VIRTUAL,
        marker_prefix="Тестовая транскрипция",
        required_block_kinds=frozenset({_PARAGRAPH}),
        expect_mock_vision=False,
        stt=True,
        marker_from_unique_id=False,
    ),
)


_CASES_BY_ID: dict[str, GoldenReadCase] = {case.case_id: case for case in _CASES}


def _case_marker(case: GoldenReadCase, unique_id: str) -> str:
    if case.marker_from_unique_id:
        return marker(case.marker_prefix, unique_id)
    if case.case_id == "sqlite":
        return f"golden_{unique_id}"
    return case.marker_prefix


async def _read_case(
    case: GoldenReadCase,
    *,
    frontend_container: FrontendContainer,
    unique_id: str,
    mock_llm_with_queue,
    persist_assets_namespace: str | None,
) -> tuple[bytes, FileExtract]:
    configure_file_reader_persist(frontend_container.files_service)
    if case.expect_mock_vision:
        mock_llm_with_queue(["MOCK_VISION"])
    raw = case.build(unique_id)
    file_ref = await store_golden_file(
        frontend_container.files_service,
        raw=raw,
        original_name=f"golden_{case.case_id}_{unique_id}{case.suffix}",
    )
    transcription_company_id = corpus_stt_company_id(unique_id) if case.stt else None
    extract = await read_stored_extract(
        file_ref,
        persist_assets_namespace=persist_assets_namespace,
        transcription_company_id=transcription_company_id,
    )
    return raw, extract


@pytest.mark.parametrize("case_id", tuple(_CASES_BY_ID))
async def test_file_extract_contract_without_persist(
    case_id: str,
    frontend_container: FrontendContainer,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    case = _CASES_BY_ID[case_id]
    raw, extract = await _read_case(
        case,
        frontend_container=frontend_container,
        unique_id=unique_id,
        mock_llm_with_queue=mock_llm_with_queue,
        persist_assets_namespace=None,
    )
    await assert_file_extract(
        extract,
        raw=raw,
        kind=case.kind,
        read_lane=case.read_lane,
        layout_kind=case.layout_kind,
        marker=_case_marker(case, unique_id),
        required_block_kinds=case.required_block_kinds,
        persist_assets=False,
        expect_mock_vision=case.expect_mock_vision,
        require_unique_marker=case.require_unique_marker,
        min_pages=case.min_pages,
        expected_labels=case.expected_labels,
        label_prefix=case.label_prefix,
    )


async def _create_rag_namespace(unique_namespace_name: str) -> str:
    namespace = await get_rag_container().namespace_service.get_or_create(
        unique_namespace_name
    )
    return namespace.name


@pytest.mark.parametrize(
    "case_id",
    ["docx", "pptx", "png", "pdf_scan", "pdf_text"],
)
async def test_file_extract_persist_writes_fileref(
    case_id: str,
    frontend_container: FrontendContainer,
    unique_id: str,
    mock_llm_with_queue,
    office_service,
    unique_namespace_name: str,
) -> None:
    _ = office_service
    case = _CASES_BY_ID[case_id]
    namespace_id = await _create_rag_namespace(unique_namespace_name)
    raw, extract = await _read_case(
        case,
        frontend_container=frontend_container,
        unique_id=unique_id,
        mock_llm_with_queue=mock_llm_with_queue,
        persist_assets_namespace=namespace_id,
    )
    await assert_file_extract(
        extract,
        raw=raw,
        kind=case.kind,
        read_lane=case.read_lane,
        layout_kind=case.layout_kind,
        marker=_case_marker(case, unique_id),
        required_block_kinds=case.required_block_kinds,
        persist_assets=True,
        expect_mock_vision=case.expect_mock_vision,
        require_unique_marker=case.require_unique_marker,
        files_service=frontend_container.files_service,
        min_pages=case.min_pages,
        expected_labels=case.expected_labels,
        label_prefix=case.label_prefix,
    )
