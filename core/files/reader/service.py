"""Оркестратор чтения файлов: единая точка входа FileReader.read -> FileReadResult."""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import uuid
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Union

from core.files.checksum import compute_content_checksum_sha256
from core.files.reader.exceptions import FileReadError
from core.files.reader.models import (
    FileReadKind,
    FileReadResult,
    FileTypeInfo,
    ReadAsset,
    ReadAssetKind,
    ReadOptions,
    ReadPage,
)

SourceInput = Union[Path, str, bytes]

_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".rst",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".log",
    ".ini",
    ".yaml",
    ".yml",
}
_SPREADSHEET_EXTENSIONS = {".xlsx", ".xls"}
_OFFICE_EXTENSIONS = {
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".odt",
    ".rtf",
    ".epub",
    ".msg",
    ".eml",
}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}

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


def _kind_from_extension(ext: str) -> FileReadKind:
    if ext == ".pdf":
        return FileReadKind.PDF
    if ext in _TEXT_EXTENSIONS:
        return FileReadKind.TEXT
    if ext in _SPREADSHEET_EXTENSIONS:
        return FileReadKind.SPREADSHEET
    if ext in _OFFICE_EXTENSIONS:
        return FileReadKind.OFFICE
    if ext in _IMAGE_EXTENSIONS:
        return FileReadKind.IMAGE
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
            elif mime == "application/pdf":
                kind = FileReadKind.PDF
            elif mime in ("text/plain", "text/markdown", "text/html", "text/csv"):
                kind = FileReadKind.TEXT
        return FileTypeInfo(detected_kind=kind, mime_type=mime, extension=ext)

    def _load_raw(self, source: SourceInput, file_name: Optional[str]) -> tuple[bytes, str]:
        if isinstance(source, bytes):
            if not file_name or not str(file_name).strip():
                raise ValueError("file_name обязателен при source=bytes")
            return source, str(file_name)
        path = Path(source)
        if not path.is_file():
            raise FileReadError(f"Файл не найден: {path}")
        data = path.read_bytes()
        name = file_name if file_name else path.name
        return data, name

    async def read(
        self,
        *,
        source: SourceInput,
        file_name: Optional[str] = None,
        options: Optional[ReadOptions] = None,
    ) -> FileReadResult:
        opts = options or ReadOptions()
        raw, name = self._load_raw(source, file_name)
        source_checksum = opts.source_checksum or compute_content_checksum_sha256(raw)
        info = self.recognize_file_type(file_name=name, head=raw[:8192])
        mime = info.mime_type or _guess_mime(name)

        if info.detected_kind == FileReadKind.PDF or _sniff_pdf(raw):
            result = await asyncio.to_thread(_read_pdf_sync, raw, name, mime, opts)
        elif info.detected_kind == FileReadKind.IMAGE:
            result = await _read_image_impl(raw, name, mime or "application/octet-stream", opts)
        elif info.detected_kind == FileReadKind.TEXT:
            result = await asyncio.to_thread(_read_plain_text_sync, raw, name, mime, opts)
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
