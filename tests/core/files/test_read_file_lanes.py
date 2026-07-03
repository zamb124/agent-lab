"""read_file lanes: specialized tools, vision, hybrid, STT."""

from __future__ import annotations

import pytest

from apps.flows.tools.files import (
    read_docx,
    read_docx_hybrid,
    read_image_vision,
    read_pdf_hybrid,
    read_pdf_text,
    read_pdf_via_vision,
    read_text,
    read_xlsx,
)
from core.files.reader import VISION_FULL_READ_MAX_PAGES, ContentMode, ReadLane
from core.files.reader.extract_cache import load_vision_page
from core.state import ExecutionState
from core.types import require_json_object
from tests.core.files.corpus.manifest import POSITIVE
from tests.core.files.corpus.read_helpers import (
    store_corpus_bytes_in_files_service,
    store_corpus_in_files_service,
)
from tests.fixtures.s3 import require_s3_configured

_SPECIALIZED = (
    (read_text, ReadLane.TEXT, "fake-text.txt"),
    (read_pdf_text, ReadLane.TEXT, "pdf/DA-1p.pdf"),
    (read_xlsx, ReadLane.TEXT, "stanley-cups.xlsx"),
    (read_docx, ReadLane.TEXT, "simple.docx"),
    (read_pdf_via_vision, ReadLane.VISION, "pdf/multi-column-2p.pdf"),
    (read_pdf_hybrid, ReadLane.HYBRID, "pdf/multi-column-2p.pdf"),
    (read_image_vision, ReadLane.VISION, "img/example.jpg"),
)


def _state_with(file_ref) -> ExecutionState:
    return ExecutionState.create(
        task_id="lanes_task",
        context_id="lanes_ctx",
        user_id="test_user",
        session_id="lanes_flow:lanes_ctx",
        files=[file_ref],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool", "expected_lane", "relative_path"), _SPECIALIZED)
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_specialized_tool_forces_read_lane(
    tool,
    expected_lane: ReadLane,
    relative_path: str,
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == relative_path)
    if entry.uses_vision_llm or expected_lane in (ReadLane.VISION, ReadLane.HYBRID):
        mock_llm_with_queue(["MOCK_VISION"])
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = _state_with(file_ref)
    payload = require_json_object(
        await tool.run({"names": [file_ref.original_name]}, state),
        f"{tool.name}.result",
    )
    assert payload["files"][0]["read_lane"] == expected_lane.value


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_text_on_image_fails(
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "img/example.jpg")
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = _state_with(file_ref)
    payload = require_json_object(
        await read_text.run({"names": [file_ref.original_name]}, state),
        "read_text.image",
    )
    assert payload["files"][0]["success"] is False
    assert payload["files"][0]["stop_reason"] == "error"


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_pdf_vision_full_read_small_pdf(
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "pdf/multi-column-2p.pdf")
    mock_llm_with_queue(["MOCK_VISION", "MOCK_VISION"])
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = _state_with(file_ref)
    payload = require_json_object(
        await read_pdf_via_vision.run(
            {"names": [file_ref.original_name], "page_start": 0, "page_end": 1},
            state,
        ),
        "read_pdf_via_vision.full",
    )
    file_result = payload["files"][0]
    assert file_result["success"] is True
    assert file_result["read_lane"] == "vision"
    assert len(file_result["results"]) >= 1


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_pdf_vision_lazy_mode_caches_requested_pages(
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    lazy_path = "pdf/layout-parser-paper.pdf"
    mock_llm_with_queue(["MOCK_VISION"])
    file_ref = await store_corpus_bytes_in_files_service(
        frontend_container, relative_path=lazy_path
    )
    state = _state_with(file_ref)

    payload = require_json_object(
        await read_pdf_via_vision.run(
            {"names": [file_ref.original_name], "page_start": 0, "page_end": 0},
            state,
        ),
        "read_pdf_via_vision.lazy",
    )
    file_result = payload["files"][0]
    assert file_result["success"] is True
    assert file_result["pages_total"] > VISION_FULL_READ_MAX_PAGES
    assert any("vision применён только к запрошенным страницам" in w for w in file_result["warnings"])
    assert file_result["results"][0]["page"] == 0

    cached = await load_vision_page(file_id=file_ref.file_id, checksum=None, page=0)
    assert cached is not None
    assert "MOCK_VISION" in cached


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_docx_hybrid_without_images_falls_back_to_text_with_warning(
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "simple.docx")
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = _state_with(file_ref)
    payload = require_json_object(
        await read_docx_hybrid.run({"names": [file_ref.original_name]}, state),
        "read_docx_hybrid.simple",
    )
    file_result = payload["files"][0]
    assert file_result["success"] is True
    assert any("hybrid недоступен" in w for w in file_result["warnings"])


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_audio_read_uses_stt_lane(
    frontend_container,
    unique_id: str,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "CantinaBand3.wav")
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = _state_with(file_ref)
    from apps.flows.tools.files import read_file

    payload = require_json_object(
        await read_file.run({"names": [file_ref.original_name]}, state),
        "read_file.audio",
    )
    file_result = payload["files"][0]
    assert file_result["success"] is True
    assert file_result["read_lane"] == ReadLane.STT.value
    if file_result["results"]:
        assert file_result["results"][0]["content_mode"] in (
            ContentMode.STT.value,
            ContentMode.FULL.value,
        )
