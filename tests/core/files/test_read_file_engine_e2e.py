"""E2E read_file: реальное хранилище, Redis extract-cache, tools, capability."""

from __future__ import annotations

import pytest

from apps.capability_gateway.container import get_capability_gateway_container
from apps.flows.tools.files.files import read_file
from core.files.reader.engine import read_files_to_envelope
from core.files.reader.extract_cache import (
    extract_cache_key,
    load_file_extract,
    store_file_extract,
)
from core.files.reader.models import ReadFileArgs, StopReason
from core.types import require_json_object
from tests.core.files.corpus.e2e_helpers import (
    assert_file_extract_body,
    capability_files_read_request,
    execution_state_for_files,
)
from tests.core.files.corpus.manifest import POSITIVE
from tests.core.files.corpus.read_helpers import (
    build_corpus_extract,
    require_corpus_bytes,
    store_corpus_in_files_service,
)
from tests.fixtures.s3 import require_s3_configured

_TEXT = "fake-text.txt"
_CSV = "stanley-cups.csv"
_PDF = "pdf/DA-1p.pdf"
_XLSX = "stanley-cups.xlsx"
_IMAGE = "img/example.jpg"


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_files_to_envelope_from_persisted_file(
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == _TEXT)
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    args = ReadFileArgs(names=[file_ref.original_name], budget=180_000)

    envelope = await read_files_to_envelope([file_ref], args, tool_name="read_file")

    assert envelope.success is True
    assert envelope.files_processed == 1
    assert envelope.files[0].success is True
    assert envelope.files[0].file_id == file_ref.file_id
    assert envelope.files[0].results
    assert envelope.files[0].stop_reason == StopReason.COMPLETE


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_extract_cache_hit_on_drilldown(
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "book-war-and-peace-1225p.txt")
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    assert file_ref.file_id is not None

    first_args = ReadFileArgs(names=[file_ref.original_name], budget=2_000)
    first = await read_files_to_envelope([file_ref], first_args, tool_name="read_file")
    cached = await load_file_extract(file_id=file_ref.file_id, checksum=None)
    assert cached is not None
    assert cached.pages

    next_start = first.files[0].continuation.next_page_start
    second_args = ReadFileArgs(
        names=[file_ref.original_name],
        budget=180_000,
        page_start=next_start,
        page_end=next_start,
    )
    second = await read_files_to_envelope([file_ref], second_args, tool_name="read_file")
    assert second.files[0].pages_processed == 1
    assert second.files[0].results[0].page == next_start


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_extract_cache_miss_reextracts_without_crash(
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == _CSV)
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    assert file_ref.file_id is not None

    args = ReadFileArgs(names=[file_ref.original_name], budget=180_000)
    _ = await read_files_to_envelope([file_ref], args, tool_name="read_file")

    key = extract_cache_key(file_id=file_ref.file_id, checksum=None)
    assert key is not None
    from core.clients.redis_client import RedisClient
    from core.config import get_settings

    redis = RedisClient(get_settings().database.redis_url)
    _ = await redis.delete(key)

    again = await read_files_to_envelope([file_ref], args, tool_name="read_file")
    assert again.files[0].success is True
    restored = await load_file_extract(file_id=file_ref.file_id, checksum=None)
    assert restored is not None


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_multi_file_batch_mixed_lanes(
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    mock_llm_with_queue(["MOCK_VISION"])
    pdf_entry = next(e for e in POSITIVE if e.relative_path == _PDF)
    image_entry = next(e for e in POSITIVE if e.relative_path == _IMAGE)
    pdf_ref = await store_corpus_in_files_service(frontend_container, pdf_entry, unique_id=unique_id)
    image_ref = await store_corpus_in_files_service(frontend_container, image_entry, unique_id=unique_id)

    args = ReadFileArgs(names=[pdf_ref.original_name, image_ref.original_name], budget=180_000)
    envelope = await read_files_to_envelope([pdf_ref, image_ref], args, tool_name="read_file")

    assert envelope.files_processed == 2
    lanes = {item.file_name: item.read_lane.value for item in envelope.files}
    assert lanes[pdf_ref.original_name] == "text"
    assert lanes[image_ref.original_name] == "vision"


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_tool_missing_name_returns_error_result(
    frontend_container,
    unique_id: str,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == _TEXT)
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    state = execution_state_for_files(files=[file_ref], user_id="test_user")
    payload = require_json_object(
        await read_file.run({"names": ["definitely-missing.txt", file_ref.original_name]}, state),
        "read_file.missing",
    )
    assert payload["success"] is True
    assert payload["files"][0]["success"] is False
    assert payload["files"][0]["stop_reason"] == "error"
    assert payload["files"][1]["success"] is True


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_capability_files_read_returns_single_file_result(
    frontend_container,
    system_user_id: str,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == _XLSX)
    raw = require_corpus_bytes(entry)
    file_ref = await store_corpus_in_files_service(frontend_container, entry, unique_id=unique_id)
    assert file_ref.file_id is not None

    registry = get_capability_gateway_container().capability_registry
    response = await registry.call(
        capability_files_read_request(user_id=system_user_id, file_id=file_ref.file_id, page_end=-1)
    )
    assert response.status == "ok"
    body = require_json_object(response.result, "files.read.result")
    assert_file_extract_body(body, entry=entry, file_ref=file_ref, raw=raw)


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_manual_extract_store_roundtrip(
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    entry = next(e for e in POSITIVE if e.relative_path == _TEXT)
    extract = await build_corpus_extract(
        entry,
        unique_id=unique_id,
        mock_llm_with_queue=mock_llm_with_queue,
        file_id="manual-roundtrip-id",
    )
    await store_file_extract(extract)
    loaded = await load_file_extract(file_id="manual-roundtrip-id", checksum=None)
    assert loaded is not None
    assert loaded.page_layout.pages_total == extract.page_layout.pages_total
    assert loaded.source_checksum == extract.source_checksum
