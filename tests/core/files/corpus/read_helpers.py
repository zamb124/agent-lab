"""Хелперы для тестов read_file на корпусе example-docs."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.files.checksum import compute_content_checksum_sha256
from core.files.file_ref import FileRef
from core.files.reader.models import (
    MAX_READ_BUDGET,
    FileExtract,
    FileReadKind,
    FileReadResult,
    PageLayoutKind,
    ReadFileArgs,
    ReadLane,
)
from core.files.reader.service import FileReader
from core.files.reader.universal import page_layout_kind_for_result, read_lane_for_kind
from tests.core.files.corpus.helpers import corpus_stt_company_id, require_heic_entry_supported
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


def assert_extract_read_lane(entry: CorpusFile, extract: FileExtract) -> None:
    if entry.expected_kind == FileReadKind.PDF:
        if entry.uses_vision_llm:
            assert extract.read_lane in (ReadLane.HYBRID, ReadLane.VISION)
        else:
            assert extract.read_lane in (ReadLane.TEXT, ReadLane.HYBRID)
        return
    if entry.expected_kind == FileReadKind.OFFICE:
        # Слайды/страницы без пригодного текста идут в vision → HYBRID, как у PDF.
        assert extract.read_lane in (ReadLane.TEXT, ReadLane.HYBRID, ReadLane.VISION)
        return
    expected = expected_read_lane(entry)
    assert extract.read_lane == expected


def expected_layout_kind(extract: FileExtract, raw_result: FileReadResult | None) -> PageLayoutKind:
    """PDF/лист/картинка — native units. Остальное совпадает с keep_reader_pages сырого parse."""
    if extract.kind in (FileReadKind.PDF, FileReadKind.SPREADSHEET, FileReadKind.IMAGE):
        return PageLayoutKind.NATIVE
    if raw_result is None:
        raise ValueError(f"layout для kind={extract.kind.value} требует FileReadResult")
    return page_layout_kind_for_result(raw_result)


async def read_corpus_extract(
    entry: CorpusFile,
    *,
    unique_id: str,
    mock_llm_with_queue,
    vision_prompt: str | None = None,
) -> FileExtract:
    if entry.skip_reason:
        pytest.skip(entry.skip_reason)
    require_heic_entry_supported(entry.relative_path)
    raw = require_corpus_bytes(entry)
    if entry.uses_vision_llm:
        mock_llm_with_queue([_MOCK_VISION_TEXT])
    transcription_company_id: str | None = None
    if entry.uses_mock_stt_tier:
        transcription_company_id = corpus_stt_company_id(unique_id)
    read_args = ReadFileArgs(
        page_end=-1,
        vision_prompt=vision_prompt or "",
        transcription_company_id=transcription_company_id,
    )
    return await FileReader().read(
        raw,
        read_args,
        file_name=entry.path.name,
    )


async def read_corpus_raw(
    entry: CorpusFile,
    *,
    unique_id: str,
    mock_llm_with_queue,
    vision_prompt: str | None = None,
) -> FileReadResult:
    """Low-level parse без extract engine (unit-тесты парсера)."""
    if entry.skip_reason:
        pytest.skip(entry.skip_reason)
    require_heic_entry_supported(entry.relative_path)
    raw = require_corpus_bytes(entry)
    if entry.uses_vision_llm:
        mock_llm_with_queue([_MOCK_VISION_TEXT])
    transcription_company_id: str | None = None
    if entry.uses_mock_stt_tier:
        transcription_company_id = corpus_stt_company_id(unique_id)
    return await FileReader().read_raw(
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
    extract = await read_corpus_extract(
        entry, unique_id=unique_id, mock_llm_with_queue=mock_llm_with_queue
    )
    if file_id != "test-file-id" and extract.file_id != file_id:
        return extract.model_copy(update={"file_id": file_id})
    return extract


def read_args_for(entry: CorpusFile, **overrides: object) -> ReadFileArgs:
    base = {
        "names": [entry.path.name],
        "budget": MAX_READ_BUDGET,
    }
    base.update(overrides)
    return ReadFileArgs.model_validate(base)


async def store_corpus_bytes_in_files_service(
    di,
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
    files_service = di.files_service  # type: ignore[attr-defined]
    record = await files_service.create(
        spec,
        raw,
        original_name=name,
        content_type=ext_to_mime(ext) or "application/octet-stream",
    )
    return FileRef.model_validate(record)


async def store_corpus_in_files_service(
    di,
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
    files_service = di.files_service  # type: ignore[attr-defined]
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
