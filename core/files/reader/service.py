"""Оркестратор чтения файлов: единая точка входа FileReader.read -> FileReadResult."""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import shutil
import subprocess
import tempfile
import uuid
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from botocore.exceptions import ClientError

from core.billing import get_billing_service
from core.billing.service import BALANCE_BLOCK_OPERATION_VISION
from core.context import get_context
from core.files.checksum import compute_content_checksum_sha256
from core.files.file_ref import FileRef, file_id_from_download_url, normalize_file_ref
from core.files.models import FileRecord, FileResponse
from core.files.reader.exceptions import FileReadError
from core.files.reader.models import (
    FileReadKind,
    FileReadResult,
    FileTypeInfo,
    ReadAsset,
    ReadAssetKind,
    ReadOptions,
    ReadPage,
    merge_file_ref_read_options,
)
from core.files.types import FileCategory, extensions_for

SourceInput = Union[Path, str, bytes]


def _is_file_ref_source(source: object) -> bool:
    if isinstance(source, (FileRecord, FileResponse)):
        return True
    if isinstance(source, Mapping) and not isinstance(source, (str, bytes, bytearray)):
        path_v = source.get("path")
        fid_v = source.get("file_id")
        url_v = source.get("url")
        if (isinstance(path_v, str) and path_v.strip()) or (
            isinstance(fid_v, str) and fid_v.strip()
        ) or (isinstance(url_v, str) and url_v.strip()):
            return True
        raise TypeError(
            "Если source — словарь, укажите непустой path, file_id или url (запись вложения)."
        )
    return False


async def _read_local_file_bytes(path: Path) -> bytes:
    def _read() -> bytes:
        return path.read_bytes()

    return await asyncio.to_thread(_read)


async def _read_http_bytes(url: str) -> bytes:
    from core.http import get_httpx_client

    async with get_httpx_client(timeout=120.0) as client:
        response = await client.get(url)
    response.raise_for_status()
    return response.content


async def _read_stored_file_by_id(file_id: str) -> tuple[bytes, str]:
    from core.files.processors import get_default_file_processor
    from core.files.s3_client import S3ClientFactory

    proc = await get_default_file_processor()
    record = await proc.get_file_record(file_id)
    if record is None:
        raise FileReadError(f"Файл не найден в хранилище: {file_id}")
    s3_bucket = getattr(record, "s3_bucket", None)
    s3_key = getattr(record, "s3_key", None)
    if isinstance(s3_bucket, str) and s3_bucket != "" and isinstance(s3_key, str) and s3_key != "":
        s3_client = S3ClientFactory.create_client_for_bucket(s3_bucket)
        try:
            try:
                raw = await s3_client.download_bytes(s3_key)
            except ClientError as exc:
                err = exc.response.get("Error", {}) if exc.response else {}
                code = err.get("Code", "") if isinstance(err, dict) else ""
                if code in ("NoSuchKey", "404", "NotFound"):
                    raise FileReadError(
                        "Файл не найден в хранилище: метаданные есть, объект отсутствует "
                        f"(очистка бакета, смена окружения или устаревший идентификатор). file_id={file_id}"
                    ) from exc
                raise FileReadError(
                    f"Ошибка объектного хранилища при чтении файла (код {code}): {file_id}"
                ) from exc
            return raw, record.original_name
        finally:
            await s3_client.close()
    storage_url = getattr(record, "storage_url", None)
    if isinstance(storage_url, str) and storage_url.startswith(("http://", "https://")):
        raw = await _read_http_bytes(storage_url)
        return raw, record.original_name
    raise FileReadError(f"Источник файла не настроен: {file_id}")


_TEXT_EXTENSIONS = extensions_for(FileCategory.TEXT)
_SPREADSHEET_EXTENSIONS = extensions_for(FileCategory.SPREADSHEET)
_OFFICE_EXTENSIONS = extensions_for(
    FileCategory.OFFICE_DOC, FileCategory.PRESENTATION, FileCategory.EMAIL, FileCategory.EBOOK,
)
_IMAGE_EXTENSIONS = extensions_for(FileCategory.IMAGE)
_AUDIO_EXTENSIONS = extensions_for(FileCategory.AUDIO)
_VIDEO_EXTENSIONS = extensions_for(FileCategory.VIDEO)

_DEFAULT_IMAGE_VISION_PROMPT = (
    "Извлеки весь видимый текст с изображения. "
    "Если текста нет, кратко опиши содержимое одним абзацем."
)


def _normalize_extension(file_name: str) -> str:
    return Path(file_name).suffix.lower()


def _guess_mime(file_name: str) -> Optional[str]:
    mime, _ = mimetypes.guess_type(file_name)
    return mime


def _sniff_pdf(raw: bytes) -> bool:
    return len(raw) >= 5 and raw[:5] == b"%PDF-"


_OLE_COMPOUND_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _is_msword_ole_compound(raw: bytes) -> bool:
    """Бинарный Word 97–2003 (Compound File), ожидаемый antiword."""
    return len(raw) >= len(_OLE_COMPOUND_MAGIC) and raw[: len(_OLE_COMPOUND_MAGIC)] == _OLE_COMPOUND_MAGIC


def _is_zip_local_header_magic(raw: bytes) -> bool:
    """ZIP local file header (DOCX/XLSX и др. — OOXML под неверным расширением .doc)."""
    return len(raw) >= 4 and raw[:4] == b"PK\x03\x04"


def _kind_from_extension(ext: str) -> FileReadKind:
    if ext == ".pdf":
        return FileReadKind.PDF
    if ext in (".html", ".htm"):
        return FileReadKind.HTML
    if ext in _TEXT_EXTENSIONS:
        return FileReadKind.TEXT
    if ext in _SPREADSHEET_EXTENSIONS:
        return FileReadKind.SPREADSHEET
    if ext in _OFFICE_EXTENSIONS:
        return FileReadKind.OFFICE
    if ext in _IMAGE_EXTENSIONS:
        return FileReadKind.IMAGE
    if ext in _AUDIO_EXTENSIONS:
        return FileReadKind.AUDIO
    if ext in _VIDEO_EXTENSIONS:
        return FileReadKind.VIDEO
    return FileReadKind.UNKNOWN


class FileReader:
    """Чтение файлов в каноническую структуру FileReadResult."""

    def recognize_file_type(self, *, file_name: str, head: Optional[bytes] = None) -> FileTypeInfo:
        ext = _normalize_extension(file_name)
        mime = _guess_mime(file_name)
        kind = _kind_from_extension(ext)
        if head is not None and _sniff_pdf(head):
            kind = FileReadKind.PDF
            if mime is None:
                mime = "application/pdf"
        if kind == FileReadKind.UNKNOWN and mime:
            if mime.startswith("image/"):
                kind = FileReadKind.IMAGE
            elif mime.startswith("audio/"):
                kind = FileReadKind.AUDIO
            elif mime.startswith("video/"):
                kind = FileReadKind.VIDEO
            elif mime == "application/pdf":
                kind = FileReadKind.PDF
            elif mime == "text/html":
                kind = FileReadKind.HTML
            elif mime in ("text/plain", "text/markdown", "text/csv"):
                kind = FileReadKind.TEXT
        return FileTypeInfo(detected_kind=kind, mime_type=mime, extension=ext)

    async def _resolve_source(
        self,
        source: SourceInput,
        file_name: Optional[str],
        opts: ReadOptions,
    ) -> tuple[bytes, str]:
        if isinstance(source, bytes):
            if not file_name or not str(file_name).strip():
                raise ValueError("file_name обязателен при source=bytes")
            return source, str(file_name)

        path = source if isinstance(source, Path) else Path(str(source).strip())
        if path.is_file():
            data = await _read_local_file_bytes(path)
            name = file_name if file_name else path.name
            return data, name

        s = str(source).strip()
        if s.startswith(("http://", "https://")):
            data = await _read_http_bytes(s)
            tail = s.rsplit("/", 1)[-1]
            guessed = tail.split("?")[0] if tail else "file"
            name = file_name if file_name else (guessed or "file")
            return data, name

        fid: Optional[str] = None
        if isinstance(opts.source_file_id, str) and opts.source_file_id.strip():
            fid = opts.source_file_id.strip()
        if not fid:
            fid = file_id_from_download_url(s)
        if fid:
            data, default_name = await _read_stored_file_by_id(fid)
            name = file_name if file_name else default_name
            return data, name

        raise FileReadError(f"Файл не найден: {s}")

    async def _read_resolved(
        self,
        raw: bytes,
        name: str,
        opts: ReadOptions,
    ) -> FileReadResult:
        source_checksum = opts.source_checksum or compute_content_checksum_sha256(raw)
        info = self.recognize_file_type(file_name=name, head=raw[:8192])
        mime = info.mime_type or _guess_mime(name)

        if info.detected_kind == FileReadKind.PDF or _sniff_pdf(raw):
            result = await asyncio.to_thread(_read_pdf_sync, raw, name, mime, opts)
        elif info.detected_kind == FileReadKind.IMAGE:
            result = await _read_image_impl(raw, name, mime or "application/octet-stream", opts)
        elif info.detected_kind == FileReadKind.AUDIO:
            result = await _read_audio_impl(raw, name, mime or "audio/mpeg", opts)
        elif info.detected_kind == FileReadKind.VIDEO:
            result = await _read_video_impl(raw, name, mime or "video/mp4", opts)
        elif info.detected_kind == FileReadKind.HTML:
            result = await asyncio.to_thread(_read_html_sync, raw, name, mime, opts)
        elif info.detected_kind == FileReadKind.TEXT:
            result = await asyncio.to_thread(_read_plain_text_sync, raw, name, mime, opts)
        elif info.detected_kind == FileReadKind.SPREADSHEET and info.extension == ".xls":
            result = await asyncio.to_thread(_read_xls_sync, raw, name, mime, opts)
        elif info.detected_kind == FileReadKind.OFFICE and info.extension == ".doc":
            result = await asyncio.to_thread(_read_doc_choosing_backend_sync, raw, name, mime, opts)
        elif info.detected_kind in (FileReadKind.OFFICE, FileReadKind.SPREADSHEET):
            result = await asyncio.to_thread(_read_unstructured_sync, raw, name, mime, info.detected_kind, opts)
        elif info.detected_kind == FileReadKind.UNKNOWN:
            result = await asyncio.to_thread(_read_unstructured_sync, raw, name, mime, FileReadKind.UNKNOWN, opts)
        else:
            raise FileReadError(f"Неподдерживаемый тип: {info.detected_kind}")

        result = result.model_copy(
            update={
                "source_file_id": opts.source_file_id,
                "source_checksum": source_checksum,
            }
        )
        if result.page_count != len(result.pages):
            raise RuntimeError("инвариант FileReadResult: page_count должен совпадать с len(pages)")
        return result

    async def _raw_from_file_ref(
        self,
        finfo: dict[str, Any],
        opts: ReadOptions,
    ) -> tuple[bytes, str]:
        display_name = (finfo.get("name") or finfo.get("original_name") or "").strip() or None

        path_str = finfo.get("path")
        if isinstance(path_str, str) and path_str.strip():
            p = Path(path_str.strip())
            if p.is_file():
                return await self._resolve_source(p, display_name, opts)

        url_val = finfo.get("url")
        if isinstance(url_val, str) and url_val.strip().startswith(("http://", "https://")):
            return await self._resolve_source(url_val.strip(), display_name, opts)

        source: SourceInput = ""
        if isinstance(url_val, str) and url_val.strip():
            source = url_val.strip()

        return await self._resolve_source(source, display_name, opts)

    async def read(
        self,
        source: Union[SourceInput, FileRef],
        *,
        file_name: Optional[str] = None,
        include_asset_bytes: bool = False,
        source_file_id: Optional[str] = None,
        source_checksum: Optional[str] = None,
        vision_model: str = "google/gemini-2.5-flash-preview",
        vision_prompt: Optional[str] = None,
        transcription_company_id: Optional[str] = None,
    ) -> FileReadResult:
        opts = ReadOptions(
            include_asset_bytes=include_asset_bytes,
            source_file_id=source_file_id,
            source_checksum=source_checksum,
            vision_model=vision_model,
            vision_prompt=vision_prompt,
            transcription_company_id=transcription_company_id,
        )
        if _is_file_ref_source(source):
            finfo = normalize_file_ref(source)
            opts = merge_file_ref_read_options(finfo, opts)
            raw, resolved_name = await self._raw_from_file_ref(finfo, opts)
            name = (file_name.strip() if isinstance(file_name, str) and file_name.strip() else None) or resolved_name
        else:
            raw, name = await self._resolve_source(source, file_name, opts)
        return await self._read_resolved(raw, name, opts)


async def _read_image_impl(
    raw: bytes,
    file_name: str,
    mime: str,
    opts: ReadOptions,
) -> FileReadResult:
    from a2a.types import FilePart, FileWithBytes, Message, Part, Role, TextPart

    from core.clients.llm.factory import get_vision_llm
    from core.models.billing_models import UsageType
    from core.tracing.operation_span import traced_operation

    b64 = base64.b64encode(raw).decode("utf-8")
    if opts.vision_prompt is not None:
        stripped = opts.vision_prompt.strip()
        if not stripped:
            raise ValueError("ReadOptions.vision_prompt задан пустой строкой")
        prompt = stripped
    else:
        prompt = _DEFAULT_IMAGE_VISION_PROMPT
    message = Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[
            Part(root=TextPart(text=prompt)),
            Part(
                root=FilePart(
                    file=FileWithBytes(
                        bytes=b64,
                        mime_type=mime,
                        name=file_name,
                    )
                )
            ),
        ],
    )
    llm = get_vision_llm(model_name=opts.vision_model)
    actx = get_context()
    if actx is None or actx.active_company is None:
        raise ValueError("Контекст с active_company обязателен для vision-чтения изображения")
    if actx.user is None or not str(actx.user.user_id).strip():
        raise ValueError("Контекст с user обязателен для vision-чтения изображения (биллинг и уведомления)")
    await get_billing_service().require_balance_for_billable_operation(
        actx.active_company.company_id,
        str(actx.user.user_id).strip(),
        operation_code=BALANCE_BLOCK_OPERATION_VISION,
        notification_service="frontend",
    )
    async with traced_operation(
        "core.files.reader.image",
        event_type="llm.vision",
        operation_category="llm",
        billing_usage_type=UsageType.LLM_REQUEST.value,
        billing_resource_name=f"llm:{opts.vision_model}",
        billing_quantity=1,
        billing_pending_settlement=True,
    ):
        vision_result = await llm.invoke([message], json_output=False)
    text = str(vision_result) if vision_result is not None else ""
    page = ReadPage(index=0, text=text, assets=[], label=None)
    return FileReadResult(
        file_name=file_name,
        mime_type=mime,
        detected_kind=FileReadKind.IMAGE,
        page_count=1,
        pages=[page],
        warnings=[],
    )


def _read_html_sync(
    raw: bytes,
    file_name: str,
    mime: Optional[str],
    opts: ReadOptions,
) -> FileReadResult:
    del opts
    import trafilatura

    html = raw.decode("utf-8", errors="replace")
    try:
        extracted = trafilatura.extract(
            html,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            include_images=False,
            favor_recall=True,
        )
    except Exception as exc:
        raise FileReadError(f"Ошибка trafilatura при разборе HTML: {file_name}") from exc
    if extracted is None or extracted.strip() == "":
        raise FileReadError(f"trafilatura не извлекла текст из HTML: {file_name}")
    page = ReadPage(index=0, text=extracted, assets=[], label=None)
    return FileReadResult(
        file_name=file_name,
        mime_type=mime or "text/html",
        detected_kind=FileReadKind.HTML,
        page_count=1,
        pages=[page],
        warnings=[],
    )


def _read_plain_text_sync(
    raw: bytes,
    file_name: str,
    mime: Optional[str],
    opts: ReadOptions,
) -> FileReadResult:
    del opts
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    page = ReadPage(index=0, text=text, assets=[], label=None)
    return FileReadResult(
        file_name=file_name,
        mime_type=mime or "text/plain",
        detected_kind=FileReadKind.TEXT,
        page_count=1,
        pages=[page],
        warnings=[],
    )


def _read_xls_sync(
    raw: bytes,
    file_name: str,
    mime: Optional[str],
    opts: ReadOptions,
) -> FileReadResult:
    del opts
    import xlrd

    book = xlrd.open_workbook(file_contents=raw)
    pages: List[ReadPage] = []
    for sheet_idx in range(book.nsheets):
        sheet = book.sheet_by_index(sheet_idx)
        rows: List[str] = []
        for row_idx in range(sheet.nrows):
            cells = []
            for col_idx in range(sheet.ncols):
                cell = sheet.cell(row_idx, col_idx)
                value = cell.value
                if cell.ctype == xlrd.XL_CELL_EMPTY:
                    cells.append("")
                else:
                    cells.append(str(value).rstrip("0").rstrip(".") if isinstance(value, float) and value == int(value) else str(value))
            row_text = "\t".join(cells).rstrip()
            if row_text:
                rows.append(row_text)
        if rows:
            pages.append(ReadPage(index=sheet_idx, text="\n".join(rows), assets=[], label=sheet.name))
    if not pages:
        raise FileReadError(f"xlrd не извлёк данные: {file_name}")
    return FileReadResult(
        file_name=file_name,
        mime_type=mime or "application/vnd.ms-excel",
        detected_kind=FileReadKind.SPREADSHEET,
        page_count=len(pages),
        pages=pages,
        warnings=[],
    )


def _read_doc_choosing_backend_sync(
    raw: bytes,
    file_name: str,
    mime: Optional[str],
    opts: ReadOptions,
) -> FileReadResult:
    if _is_msword_ole_compound(raw):
        return _read_doc_with_antiword_sync(raw, file_name, mime, opts)
    eff_name = file_name
    eff_mime = mime
    if _is_zip_local_header_magic(raw):
        eff_mime = eff_mime or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if file_name.lower().endswith(".doc"):
            eff_name = f"{file_name[:-4]}.docx"
    return _read_unstructured_sync(raw, eff_name, eff_mime, FileReadKind.OFFICE, opts)


def _read_doc_with_antiword_sync(
    raw: bytes,
    file_name: str,
    mime: Optional[str],
    opts: ReadOptions,
) -> FileReadResult:
    antiword = shutil.which("antiword")
    if antiword is None:
        raise FileReadError(
            "Для чтения .doc файлов требуется antiword. "
            "Установите пакет: apt-get install antiword (Linux) или brew install antiword (Mac)."
        )
    with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            [antiword, tmp_path],
            capture_output=True,
            timeout=60,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise FileReadError(f"antiword не смог прочитать .doc файл: {stderr}")
    text = result.stdout.decode("utf-8", errors="replace").strip()
    if not text:
        raise FileReadError(f"antiword не извлёк текст из файла: {file_name}")
    page = ReadPage(index=0, text=text, assets=[], label=None)
    return FileReadResult(
        file_name=file_name,
        mime_type=mime or "application/msword",
        detected_kind=FileReadKind.OFFICE,
        page_count=1,
        pages=[page],
        warnings=[],
    )


def _read_pdf_sync(
    raw: bytes,
    file_name: str,
    mime: Optional[str],
    opts: ReadOptions,
) -> FileReadResult:
    import fitz

    warnings: List[str] = []
    doc = fitz.open(stream=raw, filetype="pdf")
    pages: List[ReadPage] = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            text = page.get_text() or ""
            assets: List[ReadAsset] = []
            if opts.include_asset_bytes:
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                ch = compute_content_checksum_sha256(img_bytes)
                b64_val: Optional[str] = None
                if opts.include_asset_bytes:
                    b64_val = base64.b64encode(img_bytes).decode("utf-8")
                assets.append(
                    ReadAsset(
                        kind=ReadAssetKind.PAGE_RASTER,
                        mime_type="image/png",
                        checksum=ch,
                        width=pix.width,
                        height=pix.height,
                        bytes_b64=b64_val,
                    )
                )
            pages.append(ReadPage(index=i, text=text, assets=assets, label=f"page_{i + 1}"))
    finally:
        doc.close()
    if not pages:
        warnings.append("PDF не содержит страниц")
    return FileReadResult(
        file_name=file_name,
        mime_type=mime or "application/pdf",
        detected_kind=FileReadKind.PDF,
        page_count=len(pages),
        pages=pages,
        warnings=warnings,
    )


def _read_unstructured_sync(
    raw: bytes,
    file_name: str,
    mime: Optional[str],
    kind: FileReadKind,
    opts: ReadOptions,
) -> FileReadResult:
    del opts
    from unstructured.partition.auto import partition

    warnings: List[str] = []
    file_obj = BytesIO(raw)
    try:
        elements = partition(file=file_obj, metadata_filename=file_name, languages=["rus", "eng"])
    except Exception as exc:
        raise FileReadError(f"Не удалось разобрать файл через Unstructured: {file_name}") from exc
    by_page: Dict[int, List[str]] = defaultdict(list)
    no_page_meta = False
    for el in elements:
        t = str(el).strip()
        if not t:
            continue
        md = getattr(el, "metadata", None)
        pn: Optional[int] = None
        if md is not None:
            pn = getattr(md, "page_number", None)
        if pn is None:
            no_page_meta = True
            pn = 0
        else:
            pn = int(pn) - 1
            if pn < 0:
                pn = 0
        by_page[pn].append(t)
    if not by_page:
        raise FileReadError(f"Unstructured не извлёк текст: {file_name}")
    if no_page_meta and len(by_page) == 1:
        warnings.append("Парсер не вернул номера страниц; весь текст на одной логической странице")
    sorted_keys = sorted(by_page.keys())
    pages: List[ReadPage] = []
    for seq, key in enumerate(sorted_keys):
        body = "\n\n".join(by_page[key])
        label = None if len(sorted_keys) == 1 else f"page_{key + 1}"
        pages.append(ReadPage(index=seq, text=body, assets=[], label=label))
    detected = kind
    if kind == FileReadKind.UNKNOWN:
        detected = FileReadKind.OFFICE
    return FileReadResult(
        file_name=file_name,
        mime_type=mime,
        detected_kind=detected,
        page_count=len(pages),
        pages=pages,
        warnings=warnings,
    )


def _resolve_transcription_company_id(opts: ReadOptions) -> str:
    if opts.transcription_company_id is not None and opts.transcription_company_id.strip() != "":
        return opts.transcription_company_id.strip()
    ctx = get_context()
    company_id = ctx.active_company.company_id
    if company_id == "":
        raise ValueError(
            "Транскрипция audio/video требует ReadOptions.transcription_company_id "
            "или активной компании в контексте платформы."
        )
    return company_id


async def _read_audio_impl(
    raw: bytes,
    file_name: str,
    mime: str,
    opts: ReadOptions,
) -> FileReadResult:
    from core.files.media.transcriber import MediaTranscriber

    company_id = _resolve_transcription_company_id(opts)
    transcriber = MediaTranscriber(company_id=company_id)
    transcription = await transcriber.transcribe_audio(
        audio_bytes=raw,
        file_name=file_name,
        mime_type=mime,
    )
    page = ReadPage(index=0, text=transcription.text, assets=[], label=None)
    return FileReadResult(
        file_name=file_name,
        mime_type=mime,
        detected_kind=FileReadKind.AUDIO,
        page_count=1,
        pages=[page],
        warnings=[],
    )


async def _read_video_impl(
    raw: bytes,
    file_name: str,
    mime: str,
    opts: ReadOptions,
) -> FileReadResult:
    from core.files.media.transcriber import MediaTranscriber

    company_id = _resolve_transcription_company_id(opts)
    transcriber = MediaTranscriber(company_id=company_id)
    transcription = await transcriber.transcribe_video(
        video_bytes=raw,
        file_name=file_name,
    )
    page = ReadPage(index=0, text=transcription.text, assets=[], label=None)
    return FileReadResult(
        file_name=file_name,
        mime_type=mime,
        detected_kind=FileReadKind.VIDEO,
        page_count=1,
        pages=[page],
        warnings=[],
    )
