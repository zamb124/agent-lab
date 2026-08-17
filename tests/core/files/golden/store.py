"""Store golden-байтов в FilesService и канонический FileReader.read."""

from __future__ import annotations

from pathlib import Path

from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.file_ref import FileRef
from core.files.reader import FileReader
from core.files.reader.models import FileExtract, ReadFileArgs
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.files.types import ext_to_mime
from tests.fixtures.s3 import require_s3_configured


def configure_file_reader_persist(files_service: FilesService) -> None:
    FileReader.configure_asset_persist(files_service)


async def store_golden_file(
    files_service: FilesService,
    *,
    raw: bytes,
    original_name: str,
) -> FileRef:
    require_s3_configured()
    ext = Path(original_name).suffix.lower()
    content_type = ext_to_mime(ext)
    if content_type is None:
        raise ValueError(f"нет MIME для {original_name}")
    spec = FileCreateSpec(
        source_kind=FileSourceKind.PLATFORM_AUXILIARY,
        source_ref=FileSourceRef(),
        retention=default_retention_for_source(FileSourceKind.PLATFORM_AUXILIARY),
    )
    record = await files_service.create(
        spec,
        raw,
        original_name=original_name,
        content_type=content_type,
    )
    return FileRef.model_validate(record)


async def read_stored_extract(
    file_ref: FileRef,
    *,
    persist_assets_namespace: str | None = None,
    transcription_company_id: str | None = None,
) -> FileExtract:
    return await FileReader().read(
        file_ref,
        ReadFileArgs(
            page_end=-1,
            persist_assets_namespace=persist_assets_namespace,
            transcription_company_id=transcription_company_id,
        ),
    )
