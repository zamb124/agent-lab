"""E2E files.read на полном корпусе unstructured/example-docs.

Реальные файлы, S3/FilesService, Redis extract-cache, capability gateway и read_file tool.
Без unittest.mock.patch и monkeypatch внутренностей FileReader.

Vision/STT: только канон MockLLM и mock STT-tier (testing.mdc).
"""

from __future__ import annotations

import pytest

from apps.capability_gateway.container import get_capability_gateway_container
from apps.flows.tools.files import read_file
from core.files.reader import FileReader
from core.files.reader.models import ReadFileArgs
from core.types import JsonObject, require_json_object
from tests.core.files.corpus.e2e_helpers import (
    assert_file_extract_body,
    capability_files_read_request,
    execution_state_for_files,
    read_file_kwargs_for_entry,
)
from tests.core.files.corpus.helpers import require_heic_entry_supported
from tests.core.files.corpus.manifest import POSITIVE, CorpusFile
from tests.core.files.corpus.read_helpers import require_corpus_bytes, store_corpus_in_files_service
from tests.fixtures.s3 import require_s3_configured

_MOCK_VISION_TEXT = "MOCK_VISION"

_POSITIVE_E2E: tuple[CorpusFile, ...] = tuple(
    entry for entry in POSITIVE if entry.path.stat().st_size > 0
)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", _POSITIVE_E2E, ids=lambda entry: entry.relative_path)
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_capability_files_read_corpus_file(
    frontend_container,
    system_user_id: str,
    unique_id: str,
    mock_llm_with_queue,
    entry: CorpusFile,
) -> None:
    """files.read capability на каждом файле корпуса через реальное хранилище."""
    require_s3_configured()
    require_heic_entry_supported(entry.relative_path)
    if entry.uses_vision_llm:
        mock_llm_with_queue([_MOCK_VISION_TEXT])

    raw = require_corpus_bytes(entry)
    file_ref = await store_corpus_in_files_service(
        frontend_container,
        entry,
        unique_id=unique_id,
    )
    assert file_ref.file_id is not None

    registry = get_capability_gateway_container().capability_registry
    read_kwargs = read_file_kwargs_for_entry(entry, unique_id=unique_id)
    response = await registry.call(
        capability_files_read_request(
            user_id=system_user_id,
            file_id=file_ref.file_id,
            page_end=read_kwargs.page_end,
            vision_prompt=read_kwargs.vision_prompt,
            transcription_company_id=read_kwargs.transcription_company_id,
        )
    )
    assert response.status == "ok"
    body = require_json_object(response.result, "files.read.result")
    assert_file_extract_body(body, entry=entry, file_ref=file_ref, raw=raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", _POSITIVE_E2E, ids=lambda entry: entry.relative_path)
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_tool_corpus_file(
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
    entry: CorpusFile,
) -> None:
    """read_file tool на каждом файле корпуса через ExecutionState.files."""
    require_s3_configured()
    require_heic_entry_supported(entry.relative_path)
    if entry.uses_vision_llm:
        mock_llm_with_queue([_MOCK_VISION_TEXT])

    _ = require_corpus_bytes(entry)
    file_ref = await store_corpus_in_files_service(
        frontend_container,
        entry,
        unique_id=unique_id,
    )
    state = execution_state_for_files(files=[file_ref], user_id="test_user")
    read_kwargs = read_file_kwargs_for_entry(entry, unique_id=unique_id)
    tool_payload: JsonObject = {
        "names": [file_ref.original_name],
        "page_end": read_kwargs.page_end,
    }
    if read_kwargs.vision_prompt is not None:
        tool_payload["vision_prompt"] = read_kwargs.vision_prompt
    if read_kwargs.transcription_company_id is not None:
        tool_payload["transcription_company_id"] = read_kwargs.transcription_company_id
    payload = require_json_object(
        await read_file.run(tool_payload, state),
        "read_file.result",
    )

    assert payload["success"] is True
    assert payload["files_processed"] == 1
    files = payload["files"]
    assert isinstance(files, list)
    assert len(files) == 1
    file_result = require_json_object(files[0], "read_file.files[0]")
    assert file_result["success"] is True
    assert file_result["file_id"] == file_ref.file_id
    assert file_result["kind"] == entry.expected_kind.value
    page_results_raw = file_result["results"]
    assert isinstance(page_results_raw, list)
    assert page_results_raw
    joined = "\n".join(
        str(require_json_object(page_result, "read_file.results[]")["result"])
        for page_result in page_results_raw
    )
    if not entry.allows_empty_text:
        assert len(joined.strip()) > 0
    if entry.expected_text_substring:
        assert entry.expected_text_substring in joined
    if entry.uses_vision_llm:
        assert _MOCK_VISION_TEXT in joined


@pytest.mark.asyncio
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_empty_corpus_file_read_without_storage(
    unique_id: str,
) -> None:
    """0-byte corpus files: FilesService rejects upload; read() на bytes без S3."""
    entry = next(entry for entry in POSITIVE if entry.relative_path == "empty.txt")
    _ = unique_id
    raw = require_corpus_bytes(entry)
    assert raw == b""
    extract = await FileReader().read(
        raw,
        ReadFileArgs(page_end=-1, vision_prompt=""),
        file_name=entry.path.name,
    )
    assert extract.kind == entry.expected_kind
    assert extract.pages
    assert extract.pages[0].text == ""
