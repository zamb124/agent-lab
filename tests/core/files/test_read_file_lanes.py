"""read_file lanes: engine auto-detects lane per file type."""

from __future__ import annotations

import pytest

from apps.flows.tools.files import read_file
from core.files.reader import ContentMode, ReadLane
from core.state import ExecutionState
from core.types import require_json_object
from tests.core.files.corpus.manifest import POSITIVE
from tests.core.files.corpus.read_helpers import store_corpus_in_files_service
from tests.fixtures.s3 import require_s3_configured

_AUTO_DETECT = (
    ("fake-text.txt", ReadLane.TEXT),
    ("pdf/DA-1p.pdf", ReadLane.TEXT),
    ("stanley-cups.xlsx", ReadLane.TEXT),
    ("simple.docx", ReadLane.TEXT),
    ("img/example.jpg", ReadLane.VISION),
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
@pytest.mark.parametrize(("relative_path", "expected_lane"), _AUTO_DETECT)
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_auto_detects_lane(
    relative_path: str,
    expected_lane: ReadLane,
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == relative_path)
    if entry.uses_vision_llm or expected_lane == ReadLane.VISION:
        mock_llm_with_queue(["MOCK_VISION"])
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = _state_with(file_ref)
    payload = require_json_object(
        await read_file.run({"names": [file_ref.original_name]}, state),
        "read_file.lane",
    )
    assert payload["files"][0]["read_lane"] == expected_lane.value


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_on_image_auto_uses_vision(
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "img/example.jpg")
    mock_llm_with_queue(["MOCK_VISION"])
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = _state_with(file_ref)
    payload = require_json_object(
        await read_file.run({"names": [file_ref.original_name]}, state),
        "read_file.image",
    )
    file_result = payload["files"][0]
    assert file_result["success"] is True
    assert file_result["read_lane"] == ReadLane.VISION.value


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_pdf_text_page_range(
    frontend_container,
    unique_id: str,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "pdf/multi-column-2p.pdf")
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = _state_with(file_ref)
    payload = require_json_object(
        await read_file.run(
            {"names": [file_ref.original_name], "page_start": 0, "page_end": 1},
            state,
        ),
        "read_file.pdf_range",
    )
    file_result = payload["files"][0]
    assert file_result["success"] is True
    assert len(file_result["results"]) >= 1


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_large_pdf_text_extraction(
    frontend_container,
    unique_id: str,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "pdf/DA-1p.pdf")
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = _state_with(file_ref)
    payload = require_json_object(
        await read_file.run(
            {"names": [file_ref.original_name], "page_start": 0, "page_end": 0},
            state,
        ),
        "read_file.pdf_page0",
    )
    file_result = payload["files"][0]
    assert file_result["success"] is True
    assert file_result["results"][0]["page"] == 0


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_audio_uses_stt_lane(
    frontend_container,
    unique_id: str,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "CantinaBand3.wav")
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = _state_with(file_ref)

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
