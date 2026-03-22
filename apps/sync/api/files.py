"""API роутер для файлов (Files)."""

from __future__ import annotations

import hashlib
import mimetypes
import uuid
from pathlib import Path

from botocore.exceptions import ClientError
from fastapi import APIRouter, File, HTTPException, UploadFile

from apps.sync.container import get_sync_container
from apps.sync.db.models import SyncFile
from apps.sync.models.files import FileRead, FileUploadResponse
from core.config import get_settings
from core.context import get_context
from core.files.s3_client import S3ClientFactory, build_s3_key_from_context

router = APIRouter()

_UPLOAD_MAX_BYTES = 25 * 1024 * 1024


def _safe_original_name(raw: str | None) -> str:
    if not raw or not isinstance(raw, str):
        return "file"
    name = Path(raw).name.strip()
    if name == "" or name == ".":
        return "file"
    return name[:255]


@router.post("/", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)) -> FileUploadResponse:
    """Загрузка файла в S3 и запись метаданных в sync_files."""
    settings = get_settings()
    if not settings.s3.enabled or not settings.s3.default_bucket:
        raise HTTPException(
            status_code=503,
            detail="Загрузка файлов недоступна: S3 не настроен (s3.enabled / default_bucket).",
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Пустой файл.")
    if len(data) > _UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше {_UPLOAD_MAX_BYTES} байт.",
        )

    original_name = _safe_original_name(file.filename)
    guessed, _ = mimetypes.guess_type(original_name)
    raw_ct = file.content_type
    if isinstance(raw_ct, str) and raw_ct.strip() != "":
        mime_type = raw_ct.split(";")[0].strip()
    elif guessed:
        mime_type = guessed
    else:
        mime_type = "application/octet-stream"

    context = get_context()
    company_id = context.active_company.company_id

    file_id = uuid.uuid4().hex
    checksum = hashlib.sha256(data).hexdigest()

    relative_key = f"sync/files/{file_id}/{original_name}"
    s3_key = build_s3_key_from_context(relative_key)

    s3_client = S3ClientFactory.create_default_client()
    try:
        try:
            await s3_client.upload_bytes(
                data=data,
                key=s3_key,
                content_type=mime_type,
                public=True,
            )
        except ClientError as exc:
            err_code = exc.response.get("Error", {}).get("Code", "")
            if err_code == "RequestTimeTooSkewed":
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Время на этой машине не совпадает с временем сервера S3 (RequestTimeTooSkewed). "
                        "Включите автоматическую синхронизацию часов (NTP). "
                        "Если объектное хранилище в Docker — проверьте время на хосте и в контейнере."
                    ),
                ) from exc
            raise
        storage_url = s3_client.get_public_url(s3_key)
    finally:
        await s3_client.close()

    entity = SyncFile(
        file_id=file_id,
        company_id=company_id,
        original_name=original_name,
        mime_type=mime_type,
        size_bytes=len(data),
        storage_url=storage_url,
        checksum=checksum,
    )
    container = get_sync_container()
    await container.file_repository.create(entity)

    read = FileRead(
        id=file_id,
        original_name=original_name,
        mime_type=mime_type,
        size_bytes=len(data),
        storage_url=storage_url,
        checksum=checksum,
        created_at=entity.created_at,
    )
    return FileUploadResponse(file=read)


@router.get("/{file_id}")
async def get_file(file_id: str) -> FileRead:
    """Получение метаданных файла."""
    container = get_sync_container()
    file = await container.file_repository.get(file_id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileRead(
        id=file.file_id,
        original_name=file.original_name,
        mime_type=file.mime_type,
        size_bytes=file.size_bytes,
        storage_url=file.storage_url,
        checksum=file.checksum,
        created_at=file.created_at,
    )
