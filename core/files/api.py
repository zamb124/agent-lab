"""
Единый файловый API для всех сервисов платформы.

Подключается автоматически в create_service_app — никакого кода на уровне сервиса.
Предоставляет три эндпоинта:
  POST   /                      — загрузка файла
  GET    /download/{file_id}    — стриминг содержимого
  GET    /{file_id}             — метаданные файла
"""

import logging
import mimetypes
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from core.files.audio_transcode import AudioTranscodeError
from core.files.http_range import RangeNotSatisfiableError
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


def _is_http_url(url: str) -> bool:
    if not isinstance(url, str) or url == "":
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https")


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
        from core.files.checksum import compute_content_checksum_sha256

        checksum = compute_content_checksum_sha256(data)

        repo = get_file_repo()
        processor = FileProcessor(file_repository=repo)
        try:
            file_record = await processor.persist_uploaded_file(
                data=data,
                original_name=original_name,
                content_type=content_type,
                uploaded_by=user_id,
                company_id=company_id,
                public=True,
                download_url_prefix=download_url_prefix,
                content_sha256_hex=checksum,
            )
        except AudioTranscodeError as exc:
            raise HTTPException(
                status_code=503,
                detail=str(exc),
            ) from exc

        logger.info(f"Файл загружен: {file_record.file_id} ({original_name}, {len(data)} байт)")
        return FileResponse.from_record(file_record)

    @router.get(
        "/download/{file_id}",
        response_class=StreamingResponse,
        summary="Скачать файл",
        response_model=None,
    )
    async def download_file(file_id: str, request: Request) -> StreamingResponse | Response:
        repo = get_file_repo()
        file_record = await repo.get(file_id)
        if file_record is None:
            raise HTTPException(status_code=404, detail="Файл не найден.")

        is_public = getattr(file_record, "is_public", True)
        if not is_public:
            from core.context import get_context
            ctx = get_context()
            company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
            file_company_id = getattr(file_record, "company_id", None)
            if company_id != file_company_id:
                raise HTTPException(status_code=403, detail="Нет доступа к файлу.")

        s3_bucket = getattr(file_record, "s3_bucket", None)
        s3_key = getattr(file_record, "s3_key", None)
        content_type = getattr(file_record, "content_type", None)
        if isinstance(s3_bucket, str) and s3_bucket != "" and isinstance(s3_key, str) and s3_key != "":
            if not isinstance(content_type, str) or content_type == "":
                content_type = "application/octet-stream"
            s3_client = S3ClientFactory.create_client_for_bucket(s3_bucket)
            range_raw = request.headers.get("range")
            range_header = range_raw.strip() if isinstance(range_raw, str) else None
            try:
                return await stream_s3_file(
                    s3_client=s3_client,
                    s3_key=s3_key,
                    content_type=content_type,
                    bucket=None,
                    range_header=range_header,
                )
            except RangeNotSatisfiableError as exc:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{exc.total_size}"},
                )

        storage_url = getattr(file_record, "storage_url", None)
        if not isinstance(storage_url, str) or storage_url == "":
            raise HTTPException(status_code=404, detail="Источник файла не задан.")
        if not _is_http_url(storage_url):
            raise HTTPException(status_code=404, detail="Источник файла не поддерживается для скачивания.")

        from core.http import get_httpx_client

        async with get_httpx_client(timeout=120.0) as client:
            upstream_response = await client.get(storage_url)
        upstream_response.raise_for_status()
        upstream_content_type = upstream_response.headers.get("content-type")
        response_content_type = (
            upstream_content_type
            if isinstance(upstream_content_type, str) and upstream_content_type != ""
            else "application/octet-stream"
        )
        return StreamingResponse(
            content=iter([upstream_response.content]),
            media_type=response_content_type,
        )

    @router.get("/{file_id}", response_model=FileResponse, summary="Метаданные файла")
    async def get_file_metadata(file_id: str) -> FileResponse:
        repo = get_file_repo()
        file_record = await repo.get(file_id)
        if file_record is None:
            raise HTTPException(status_code=404, detail="Файл не найден.")

        is_public = getattr(file_record, "is_public", True)
        if not is_public:
            from core.context import get_context
            ctx = get_context()
            company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
            file_company_id = getattr(file_record, "company_id", None)
            if company_id != file_company_id:
                raise HTTPException(status_code=403, detail="Нет доступа к файлу.")

        if isinstance(file_record, FileRecord):
            return FileResponse.from_record(file_record)
        raise HTTPException(status_code=404, detail="Метаданные файла недоступны.")

    return router
