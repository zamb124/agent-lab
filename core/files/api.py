"""
Единый файловый API для всех сервисов платформы.

Подключается автоматически в create_service_app — никакого кода на уровне сервиса.
Предоставляет три эндпоинта:
  POST   /                      — загрузка файла
  GET    /download/{file_id}    — стриминг содержимого
  GET    /{file_id}             — метаданные файла
"""

import mimetypes
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from urllib.parse import urlparse

import httpx
from botocore.exceptions import ClientError
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from core.config import get_settings
from core.context import require_active_company, require_context
from core.files.audio_transcode import AudioTranscodeError
from core.files.checksum import compute_content_checksum_sha256
from core.files.http_range import RangeNotSatisfiableError
from core.files.models import FileReadPreviewResponse, FileRecord, FileResponse
from core.files.processors import FileProcessor
from core.files.reader.exceptions import FileReadError
from core.files.s3_client import S3ClientFactory
from core.files.streaming import stream_s3_file
from core.http import get_httpx_client
from core.logging import get_logger

from .read_preview import build_stored_file_text_preview

if TYPE_CHECKING:
    from core.files.file_repository import FileRepository

logger = get_logger(__name__)
_DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024  # 1 MB


async def _read_upload_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    """
    Читает UploadFile чанками с early-abort при превышении max_bytes.

    Без этого `await file.read()` тянет весь multipart-тело в RAM до
    любой проверки размера: при 100 параллельных uploads по 500MB —
    50GB RAM до выброса 413. Здесь же limit проверяется на каждом chunk.
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes должен быть больше 0")
    parts: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Файл превышает {max_bytes} байт.",
            )
        parts.append(chunk)
    return b"".join(parts)


def _safe_original_name(raw: str | None) -> str:
    if raw is None or raw == "":
        return "file"
    name = Path(raw).name.strip()
    return name[:255] if name and name != "." else "file"


def _is_http_url(url: str) -> bool:
    if url == "":
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https")


def _ensure_file_record_access(file_record: FileRecord) -> None:
    if file_record.is_public:
        return
    active_company = require_active_company()
    if file_record.company_id is None:
        raise HTTPException(status_code=403, detail="Нет доступа к файлу.")
    if active_company.company_id != file_record.company_id:
        raise HTTPException(status_code=403, detail="Нет доступа к файлу.")


def build_file_api_router(
    get_file_repo: Callable[[], "FileRepository"],
    service_api_prefix: str,
    max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES,
) -> APIRouter:
    """
    Строит полный файловый APIRouter для сервиса.

    Аргументы:
        get_file_repo: Callable, возвращающий FileRepository (core, shared DB).
                       Вызывается при каждом запросе (lazy).
        service_api_prefix: Префикс API сервиса, например "/sync/api/v1".
                            Используется для формирования download_url в FileRecord.
        max_upload_bytes: Максимальный размер загружаемого файла.
    """
    router = APIRouter(tags=["files"])
    download_url_prefix = f"{service_api_prefix}/files/download"

    async def upload_file(
        file: Annotated[UploadFile, File()],
        public: Annotated[str | None, Form()] = None,
    ) -> FileResponse:
        settings = get_settings()
        if not settings.s3.enabled or not settings.s3.default_bucket:
            raise HTTPException(
                status_code=503,
                detail="Загрузка файлов недоступна: S3 не настроен.",
            )

        data = await _read_upload_with_limit(file, max_upload_bytes)
        if len(data) == 0:
            raise HTTPException(status_code=400, detail="Пустой файл.")

        original_name = _safe_original_name(file.filename)
        guessed, _ = mimetypes.guess_type(original_name)
        raw_ct = file.content_type
        if isinstance(raw_ct, str) and raw_ct.strip():
            content_type = raw_ct.split(";")[0].strip()
        elif guessed:
            content_type = guessed
        else:
            content_type = "application/octet-stream"

        context = require_context()
        company_id = require_active_company().company_id
        user_id = context.user.user_id

        checksum = compute_content_checksum_sha256(data)
        is_public = True
        if isinstance(public, str) and public.strip():
            is_public = public.strip().lower() in {"1", "true", "yes", "on"}

        repo = get_file_repo()
        processor = FileProcessor(file_repository=repo)
        try:
            file_record = await processor.persist_uploaded_file(
                data=data,
                original_name=original_name,
                content_type=content_type,
                uploaded_by=user_id,
                company_id=company_id,
                public=is_public,
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

    async def download_file(file_id: str, request: Request) -> StreamingResponse | Response:
        repo = get_file_repo()
        file_record = await repo.get(file_id)
        if file_record is None:
            raise HTTPException(status_code=404, detail="Файл не найден.")

        _ensure_file_record_access(file_record)

        s3_bucket = file_record.s3_bucket
        s3_key = file_record.s3_key
        content_type = file_record.content_type
        if s3_bucket != "" and s3_key != "":
            if content_type == "":
                raise HTTPException(status_code=500, detail="MIME тип файла не задан.")
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
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                status = exc.response["ResponseMetadata"]["HTTPStatusCode"]
                not_found = code in ("404", "NoSuchKey", "NotFound") or status == 404
                if not_found:
                    raise HTTPException(
                        status_code=404,
                        detail="Файл не найден в хранилище.",
                    ) from exc
                logger.exception(
                    "files.download_s3_failed",
                    file_id=file_id,
                    bucket=s3_bucket,
                    **{"attributes.s3_error_code": str(code)},
                )
                raise HTTPException(
                    status_code=502,
                    detail="Не удалось получить файл из хранилища.",
                ) from exc

        storage_url = file_record.storage_url
        if storage_url is None or storage_url == "":
            raise HTTPException(status_code=404, detail="Источник файла не задан.")
        if not _is_http_url(storage_url):
            raise HTTPException(status_code=404, detail="Источник файла не поддерживается для скачивания.")

        try:
            async with get_httpx_client(timeout=120.0) as client:
                upstream_response = await client.get(storage_url)
            _ = upstream_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            st = exc.response.status_code
            if st == 404:
                raise HTTPException(status_code=404, detail="Файл не найден по ссылке хранения.") from exc
            logger.exception(
                "files.download_http_upstream_failed",
                file_id=file_id,
                **{"http.status_code": st},
            )
            raise HTTPException(
                status_code=502,
                detail="Не удалось получить файл по внешней ссылке.",
            ) from exc
        except httpx.HTTPError as exc:
            logger.exception("files.download_http_upstream_failed", file_id=file_id)
            raise HTTPException(
                status_code=502,
                detail="Не удалось получить файл по внешней ссылке.",
            ) from exc
        if "content-type" not in upstream_response.headers:
            raise HTTPException(status_code=502, detail="Источник файла не вернул content-type.")
        response_content_type = upstream_response.headers["content-type"]
        if response_content_type == "":
            raise HTTPException(status_code=502, detail="Источник файла вернул пустой content-type.")
        return StreamingResponse(
            content=iter([upstream_response.content]),
            media_type=response_content_type,
        )

    async def get_file_text_preview(file_id: str) -> FileReadPreviewResponse:
        repo = get_file_repo()
        file_record = await repo.get(file_id)
        if file_record is None:
            raise HTTPException(status_code=404, detail="Файл не найден.")

        _ensure_file_record_access(file_record)
        try:
            return await build_stored_file_text_preview(
                file_id=file_id,
                original_name=file_record.original_name,
            )
        except FileReadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def get_file_metadata(file_id: str) -> FileResponse:
        repo = get_file_repo()
        file_record = await repo.get(file_id)
        if file_record is None:
            raise HTTPException(status_code=404, detail="Файл не найден.")

        _ensure_file_record_access(file_record)
        return FileResponse.from_record(file_record)

    router.add_api_route(
        "/",
        endpoint=upload_file,
        methods=["POST"],
        response_model=FileResponse,
        summary="Загрузить файл",
    )
    router.add_api_route(
        "/download/{file_id}",
        endpoint=download_file,
        methods=["GET"],
        response_class=StreamingResponse,
        summary="Скачать файл",
        response_model=None,
    )
    router.add_api_route(
        "/{file_id}/preview",
        endpoint=get_file_text_preview,
        methods=["GET"],
        response_model=FileReadPreviewResponse,
        summary="Превью извлечённого текста файла",
    )
    router.add_api_route(
        "/{file_id}",
        endpoint=get_file_metadata,
        methods=["GET"],
        response_model=FileResponse,
        summary="Метаданные файла",
    )
    return router
