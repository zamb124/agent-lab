"""read_file: vision только если текст единицы непригоден; иначе TEXT + figure."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.flows.src.state import ExecutionState
from apps.flows.tools.files.files import read_file
from core.files.file_ref import FileRef
from core.files.reader import ReadLane
from core.types import require_json_array, require_json_object
from tests.core.files.corpus.manifest import POSITIVE
from tests.core.files.corpus.read_helpers import store_corpus_in_files_service
from tests.fixtures.s3 import require_s3_configured

_MOCK_VISION = "MOCK_VISION"
_TEXT_MARKER = "Hello PDF text marker"
_TEXT_AND_IMAGE_PDF = Path(__file__).parent / "fixtures" / "pdf_text_and_image.pdf"


def _state_with(file_ref: FileRef) -> ExecutionState:
    return ExecutionState.create(
        task_id="pdf_hybrid_task",
        context_id="pdf_hybrid_ctx",
        user_id="test_user",
        session_id="pdf_hybrid_flow:pdf_hybrid_ctx",
        files=[file_ref],
    )


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_pdf_scanned_table_uses_hybrid_ocr(
    frontend_di,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "pdf/single_table.pdf")
    mock_llm_with_queue([_MOCK_VISION])
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    state = _state_with(file_ref)

    payload = require_json_object(
        await read_file.run({"names": [file_ref.original_name]}, state),
        "read_file.single_table",
    )
    files = require_json_array(payload["files"], "read_file.single_table.files")
    file_result = require_json_object(files[0], "read_file.single_table.files[0]")
    assert file_result["success"] is True
    assert file_result["read_lane"] == ReadLane.HYBRID.value
    results = require_json_array(file_result["results"], "read_file.single_table.results")
    merged = require_json_object(results[0], "read_file.single_table.results[0]")["result"]
    assert isinstance(merged, str)
    assert _MOCK_VISION in merged


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_pdf_text_only_stays_text_lane(
    frontend_di,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "pdf/DA-1p.pdf")
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    state = _state_with(file_ref)

    payload = require_json_object(
        await read_file.run({"names": [file_ref.original_name]}, state),
        "read_file.da_1p",
    )
    files = require_json_array(payload["files"], "read_file.da_1p.files")
    file_result = require_json_object(files[0], "read_file.da_1p.files[0]")
    assert file_result["success"] is True
    assert file_result["read_lane"] == ReadLane.TEXT.value
    results = require_json_array(file_result["results"], "read_file.da_1p.results")
    merged = "\n".join(
        str(require_json_object(item, "read_file.da_1p.result_item")["result"])
        for item in results
    )
    assert len(merged.strip()) > 0
    assert _MOCK_VISION not in merged


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_pdf_text_and_embedded_image_merged(
    mock_llm_with_queue,
) -> None:
    file_ref = FileRef(
        original_name=_TEXT_AND_IMAGE_PDF.name,
        url=str(_TEXT_AND_IMAGE_PDF),
        content_type="application/pdf",
        file_size=_TEXT_AND_IMAGE_PDF.stat().st_size,
    )
    mock_llm_with_queue([_MOCK_VISION])
    state = _state_with(file_ref)

    payload = require_json_object(
        await read_file.run({"names": [file_ref.original_name]}, state),
        "read_file.text_and_image",
    )
    files = require_json_array(payload["files"], "read_file.text_and_image.files")
    file_result = require_json_object(files[0], "read_file.text_and_image.files[0]")
    assert file_result["success"] is True
    assert file_result["read_lane"] == ReadLane.HYBRID.value
    results = require_json_array(file_result["results"], "read_file.text_and_image.results")
    merged = str(require_json_object(results[0], "read_file.text_and_image.results[0]")["result"])
    assert _TEXT_MARKER in merged
    assert _MOCK_VISION in merged
    assert "[image 1]" in merged
