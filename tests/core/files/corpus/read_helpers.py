"""Хелперы для тестов read_file на корпусе example-docs."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.files.checksum import compute_content_checksum_sha256
from core.files.file_ref import FileRef
from core.files.reader.models import (
    DEFAULT_READ_BUDGET,
    FileExtract,
    FileReadKind,
    FileReadResult,
    PageLayoutKind,
    ReadFileArgs,
    ReadLane,
)
from core.files.reader.service import FileReader
from core.files.reader.universal import build_file_extract, read_lane_for_kind
from tests.core.files.corpus.helpers import corpus_stt_company_id
from tests.core.files.corpus.manifest import CORPUS_DIR, CorpusFile

_MOCK_VISION_TEXT = "MOCK_VISION"


def corpus_path(entry: CorpusFile) -> Path:
    return CORPUS_DIR / entry.relative_path


def require_corpus_bytes(entry: CorpusFile) -> bytes:
    path = corpus_path(entry)
    if not path.exists():
        pytest.skip(f"Файл отсутствует в корпусе: {entry.relative_path}")
    return path.read_bytes()


def expected_read_lane(entry: CorpusFile) -> ReadLane:
    if entry.uses_vision_llm:
        return ReadLane.VISION
    if entry.uses_mock_stt_tier:
        return ReadLane.STT
    return read_lane_for_kind(entry.expected_kind)


def expected_layout_kind(result: FileReadResult, file_name: str) -> PageLayoutKind:
    if result.detected_kind == FileReadKind.PDF:
        return PageLayoutKind.NATIVE
    if result.detected_kind == FileReadKind.SPREADSHEET:
        return PageLayoutKind.NATIVE
    if result.detected_kind == FileReadKind.IMAGE:
        return PageLayoutKind.NATIVE
    if result.detected_kind == FileReadKind.OFFICE and len(result.pages) > 1:
        return PageLayoutKind.NATIVE
    _ = file_name
    return PageLayoutKind.VIRTUAL


async def read_corpus_result(
    entry: CorpusFile,
    *,
    unique_id: str,
    mock_llm_with_queue,
    vision_prompt: str | None = None,
) -> FileReadResult:
    if entry.skip_reason:
        pytest.skip(entry.skip_reason)
    raw = require_corpus_bytes(entry)
    if entry.uses_vision_llm:
        mock_llm_with_queue([_MOCK_VISION_TEXT])
    transcription_company_id: str | None = None
    if entry.uses_mock_stt_tier:
        transcription_company_id = corpus_stt_company_id(unique_id)
    return await FileReader().read(
        raw,
        file_name=entry.path.name,
        transcription_company_id=transcription_company_id,
        vision_prompt=vision_prompt,
    )


async def build_corpus_extract(
    entry: CorpusFile,
    *,
    unique_id: str,
    mock_llm_with_queue,
    file_id: str = "test-file-id",
) -> FileExtract:
    result = await read_corpus_result(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    return build_file_extract(result, file_name=entry.path.name, file_id=file_id)


def read_args_for(entry: CorpusFile, **overrides: object) -> ReadFileArgs:
    base = {
        "names": [entry.path.name],
        "budget": DEFAULT_READ_BUDGET,
    }
    base.update(overrides)
    return ReadFileArgs.model_validate(base)


async def store_corpus_bytes_in_files_service(
    container: object,
    *,
    relative_path: str,
    original_name: str | None = None,
) -> FileRef:
    from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
    from core.files.registry import default_retention_for_source
    from core.files.types import ext_to_mime

    path = CORPUS_DIR / relative_path
    if not path.exists():
        pytest.skip(f"Файл отсутствует: {relative_path}")
    raw = path.read_bytes()
    name = original_name or path.name
    ext = Path(name).suffix.lower()
    spec = FileCreateSpec.model_validate(
        {
            "source_kind": FileSourceKind.PLATFORM_AUXILIARY.value,
            "source_ref": FileSourceRef.model_validate({}).model_dump(),
            "retention": default_retention_for_source(FileSourceKind.PLATFORM_AUXILIARY),
        }
    )
    files_service = container.files_service  # type: ignore[attr-defined]
    record = await files_service.create(
        spec,
        raw,
        original_name=name,
        content_type=ext_to_mime(ext) or "application/octet-stream",
    )
    return FileRef.model_validate(record)


async def store_corpus_in_files_service(
    container: object,
    entry: CorpusFile,
    *,
    unique_id: str,
) -> FileRef:
    from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
    from core.files.registry import default_retention_for_source

    raw = require_corpus_bytes(entry)
    spec = FileCreateSpec.model_validate(
        {
            "source_kind": FileSourceKind.PLATFORM_AUXILIARY.value,
            "source_ref": FileSourceRef.model_validate({}).model_dump(),
            "retention": default_retention_for_source(FileSourceKind.PLATFORM_AUXILIARY),
        }
    )
    files_service = container.files_service  # type: ignore[attr-defined]
    record = await files_service.create(
        spec,
        raw,
        original_name=entry.path.name,
        content_type=_guess_content_type(entry),
    )
    _ = unique_id
    return FileRef.model_validate(record)


def _guess_content_type(entry: CorpusFile) -> str:
    from core.files.types import ext_to_mime

    ext = Path(entry.path.name).suffix.lower()
    return ext_to_mime(ext) or "application/octet-stream"


def assert_checksum_stable(raw: bytes, extract: FileExtract) -> None:
    assert extract.source_checksum == compute_content_checksum_sha256(raw)
