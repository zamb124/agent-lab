"""
Единый файловый API для всех сервисов платформы.

Подключается автоматически в create_service_app — никакого кода на уровне сервиса.
Предоставляет три эндпоинта:
  POST   /                      — загрузка файла
  GET    /download/{file_id}    — стриминг содержимого
  GET    /{file_id}             — метаданные файла
"""

import hashlib
import logging
import mimetypes
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from core.files.models import FileRecord, FileResponse
from core.files.processors import FileProcessor
from core.files.s3_client import S3ClientFactory
from core.files.streaming import stream_s3_file

logger = logging.getLogger(__name__)

_DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _safe_original_name(raw: str | None) -> str:
    if not raw or not isinstance(raw, str):
        return "file"
    name = Path(raw).name.strip()
    return name[:255] if name and name != "." else "file"


def build_file_api_router(
    get_file_repo: Callable,
    service_api_prefix: str,
    max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES,
) -> APIRouter:
    """
    Строит полный файловый APIRouter для сервиса.

    Args:
        get_file_repo: Callable, возвращающий FileRepository (core, shared DB).
                       Вызывается при каждом запросе (lazy).
        service_api_prefix: Префикс API сервиса, например "/sync/api/v1".
                            Используется для формирования download_url в FileRecord.
        max_upload_bytes: Максимальный размер загружаемого файла.
    """
    router = APIRouter(tags=["files"])
    download_url_prefix = f"{service_api_prefix}/files/download"

    @router.post("/", response_model=FileResponse, summary="Загрузить файл")
    async def upload_file(file: UploadFile = File(...)) -> FileResponse:
        from core.config import get_settings
        settings = get_settings()
        if not settings.s3.enabled or not settings.s3.default_bucket:
            raise HTTPException(
                status_code=503,
                detail="Загрузка файлов недоступна: S3 не настроен.",
            )

        data = await file.read()
        if len(data) == 0:
            raise HTTPException(status_code=400, detail="Пустой файл.")
        if len(data) > max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"Файл превышает {max_upload_bytes} байт.")

        original_name = _safe_original_name(file.filename)
        guessed, _ = mimetypes.guess_type(original_name)
        raw_ct = file.content_type
        if isinstance(raw_ct, str) and raw_ct.strip():
            content_type = raw_ct.split(";")[0].strip()
        elif guessed:
            content_type = guessed
        else:
            content_type = "application/octet-stream"

        from core.context import get_context
        context = get_context()
        company_id = context.active_company.company_id
        user_id = context.user.user_id
        checksum = hashlib.sha256(data).hexdigest()

        repo = get_file_repo()
        processor = FileProcessor(file_repository=repo)
        file_record = await processor.process_file_from_bytes(
            data=data,
            original_name=original_name,
            content_type=content_type,
            uploaded_by=user_id,
            public=True,
        )
        file_record = file_record.model_copy(update={
            "company_id": company_id,
            "checksum": checksum,
            "download_url": f"{download_url_prefix}/{file_record.file_id}",
        })
        await repo.set(file_record)

        logger.info(f"Файл загружен: {file_record.file_id} ({original_name}, {len(data)} байт)")
        return FileResponse.from_record(file_record)

    @router.get("/download/{file_id}", response_class=StreamingResponse, summary="Скачать файл")
    async def download_file(file_id: str) -> StreamingResponse:
        repo = get_file_repo()
        file_record: FileRecord | None = await repo.get(file_id)
        if file_record is None:
            raise HTTPException(status_code=404, detail="Файл не найден.")

        if not file_record.is_public:
            from core.context import get_context
            ctx = get_context()
            company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
            if company_id != file_record.company_id:
                raise HTTPException(status_code=403, detail="Нет доступа к файлу.")

        s3_client = S3ClientFactory.create_client_for_bucket(file_record.s3_bucket)
        return await stream_s3_file(
            s3_client=s3_client,
            s3_key=file_record.s3_key,
            content_type=file_record.content_type,
        )

    @router.get("/{file_id}", response_model=FileResponse, summary="Метаданные файла")
    async def get_file_metadata(file_id: str) -> FileResponse:
        repo = get_file_repo()
        file_record: FileRecord | None = await repo.get(file_id)
        if file_record is None:
            raise HTTPException(status_code=404, detail="Файл не найден.")

        if not file_record.is_public:
            from core.context import get_context
            ctx = get_context()
            company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
            if company_id != file_record.company_id:
                raise HTTPException(status_code=403, detail="Нет доступа к файлу.")

        return FileResponse.from_record(file_record)

    return router
