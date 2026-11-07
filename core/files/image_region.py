"""Нормализованный crop региона изображения или PDF-страницы."""

from __future__ import annotations

import math
import re
from io import BytesIO
from typing import Protocol

import pymupdf
from PIL import Image
from pydantic import Field, model_validator

from core.context import require_active_company
from core.files.create_spec import FileSourceKind, FileSourceRef
from core.files.file_ref import FileRef, stored_file_ref
from core.files.models import FileRecord
from core.files.reader.service import read_stored_file_by_id
from core.files.registry import build_file_create_spec
from core.files.service import FilesService
from core.imports import module_sdk
from core.logging import get_logger
from core.models.base import StrictBaseModel
from core.types import JsonArray, JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)

_MIN_CROP_PX = 8
_JPEG_QUALITY = 90
_PDF_RASTER_SCALE = 2.0
_PDF_MIME = "application/pdf"
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _require_norm_coord(raw: JsonValue, *, field: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"{field} must be a number")
    return float(raw)


class _PdfMatrix(Protocol): ...


class _PdfPixmap(Protocol):
    width: int
    height: int

    def tobytes(self, output: str) -> bytes: ...


class _PdfPage(Protocol):
    def get_pixmap(self, *, matrix: _PdfMatrix) -> _PdfPixmap: ...


class _PdfDocument(Protocol):
    page_count: int

    def load_page(self, page_id: int) -> _PdfPage: ...

    def close(self) -> None: ...


class _FitzModule(Protocol):
    def open(self, *, stream: bytes, filetype: str) -> _PdfDocument: ...

    def Matrix(self, zoom_x: float, zoom_y: float) -> _PdfMatrix: ...


class NormalizedRect(StrictBaseModel):
    """Рамка в долях ширины и высоты растра от левого верхнего угла."""

    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> NormalizedRect:
        if self.x0 >= self.x1 or self.y0 >= self.y1:
            raise ValueError("NormalizedRect requires x0 < x1 and y0 < y1")
        return self


def pixel_box(
    rect: NormalizedRect, *, width: int, height: int
) -> tuple[int, int, int, int]:
    """Доли → пиксельный box (left, top, right, bottom) с clamp."""
    if width < 1 or height < 1:
        raise ValueError("image size must be positive")
    left = max(0, min(width, math.floor(rect.x0 * width)))
    top = max(0, min(height, math.floor(rect.y0 * height)))
    right = max(0, min(width, math.ceil(rect.x1 * width)))
    bottom = max(0, min(height, math.ceil(rect.y1 * height)))
    if right - left < _MIN_CROP_PX or bottom - top < _MIN_CROP_PX:
        detail = f"({right - left}x{bottom - top})"
        raise ValueError(
            f"crop region smaller than {_MIN_CROP_PX}px after clamp {detail}"
        )
    return left, top, right, bottom


def crop_image_bytes(raw: bytes, rect: NormalizedRect) -> bytes:
    """PIL crop → JPEG RGB."""
    try:
        image = Image.open(BytesIO(raw))
    except Image.UnidentifiedImageError as exc:
        raise ValueError("file content is not a decodable image") from exc
    rgb = image.convert("RGB")
    width, height = rgb.size
    box = pixel_box(rect, width=width, height=height)
    cropped = rgb.crop(box)
    buffer = BytesIO()
    cropped.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return buffer.getvalue()


def raster_pdf_page(raw: bytes, page_index: int) -> bytes:
    """Pixmap страницы PDF с Matrix(2,2) → PNG bytes (тот же scale, что FileReader)."""
    if page_index < 0:
        raise ValueError("page_index must be >= 0")
    fitz = module_sdk(pymupdf, _FitzModule)
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        if page_index >= doc.page_count:
            raise ValueError(
                f"PDF page {page_index} out of range (page_count={doc.page_count})"
            )
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(_PDF_RASTER_SCALE, _PDF_RASTER_SCALE))
        return pix.tobytes("png")
    finally:
        doc.close()


def safe_crop_filename(name: str) -> str:
    stripped = name.strip().lower().replace(" ", "-")
    cleaned = _SAFE_NAME_RE.sub("-", stripped)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-._")
    if cleaned == "":
        cleaned = "dish"
    return f"{cleaned[:80]}-crop.jpg"


def _is_pdf(*, content_type: str, original_name: str) -> bool:
    mime = content_type.lower().split(";", 1)[0].strip()
    if mime == _PDF_MIME:
        return True
    return original_name.lower().endswith(".pdf")


def _is_image(*, content_type: str) -> bool:
    mime = content_type.lower().split(";", 1)[0].strip()
    return mime.startswith("image/")


async def load_page_raster_bytes(
    *,
    file_id: str,
    page: int,
    content_type: str,
    original_name: str,
) -> bytes:
    """Байты растра страницы/картинки для crop (без записи в Files)."""
    raw, _stored_name = await read_stored_file_by_id(file_id)
    if _is_pdf(content_type=content_type, original_name=original_name):
        return raster_pdf_page(raw, page)
    if page != 0:
        raise ValueError("page must be 0 for image/* sources")
    if not _is_image(content_type=content_type):
        raise ValueError(f"unsupported content_type for crop: {content_type}")
    return raw


async def persist_cropped_image(
    files_service: FilesService,
    *,
    cropped_jpeg: bytes,
    dish_name: str,
    source_file_id: str,
    page: int,
) -> FileRef:
    """Пишет JPEG кропа как GENERATED_EPHEMERAL."""
    original_name = safe_crop_filename(dish_name)
    spec = build_file_create_spec(
        source_kind=FileSourceKind.GENERATED_EPHEMERAL,
        source_ref=FileSourceRef(entity_id=source_file_id),
        metadata={"cropped_from": source_file_id, "page": page},
    )
    created = await files_service.create(
        spec,
        cropped_jpeg,
        original_name=original_name,
        content_type="image/jpeg",
    )
    return stored_file_ref(created)


async def crop_file_region(
    files_service: FilesService,
    *,
    file_id: str,
    page: int,
    rect: NormalizedRect,
    dish_name: str,
    company_id: str,
) -> FileRef:
    """Crop региона вложения → новый FileRef (ephemeral)."""
    record = await FileRecord.by_file_id(file_id, company_id)
    if record is None:
        raise ValueError(f"file not found: {file_id}")
    raster = await load_page_raster_bytes(
        file_id=file_id,
        page=page,
        content_type=record.content_type,
        original_name=record.original_name,
    )
    cropped = crop_image_bytes(raster, rect)
    return await persist_cropped_image(
        files_service,
        cropped_jpeg=cropped,
        dish_name=dish_name,
        source_file_id=file_id,
        page=page,
    )


async def materialize_image_regions(
    files_service: FilesService,
    *,
    sections: JsonArray,
    attachment_file_ids: list[str],
) -> JsonArray:
    """Заменяет photo bbox на `{file_id}` кропа; ошибка одного блюда → photo=null."""
    company_id = require_active_company().company_id
    allowed = set(attachment_file_ids)
    raster_cache: dict[tuple[str, int], bytes] = {}
    record_cache: dict[str, FileRecord] = {}
    out_sections: JsonArray = []
    for section_raw in sections:
        section = require_json_object(section_raw, "menu.section")
        items_raw = section.get("items")
        if not isinstance(items_raw, list):
            out_sections.append(section)
            continue
        new_items: JsonArray = []
        for item_raw in items_raw:
            item = require_json_object(item_raw, "menu.item")
            new_items.append(
                await _materialize_item_photo(
                    files_service=files_service,
                    company_id=company_id,
                    item=item,
                    allowed=allowed,
                    raster_cache=raster_cache,
                    record_cache=record_cache,
                )
            )
        out_sections.append({**section, "items": new_items})
    return out_sections


async def _materialize_item_photo(
    *,
    files_service: FilesService,
    company_id: str,
    item: JsonObject,
    allowed: set[str],
    raster_cache: dict[tuple[str, int], bytes],
    record_cache: dict[str, FileRecord],
) -> JsonObject:
    photo_raw = item.get("photo")
    if photo_raw is None:
        return item
    if not isinstance(photo_raw, dict):
        return {**item, "photo": None}
    file_id_val = photo_raw.get("file_id")
    if not isinstance(file_id_val, str) or file_id_val.strip() == "":
        return {**item, "photo": None}
    file_id = file_id_val.strip()

    has_bbox = all(key in photo_raw for key in ("x0", "y0", "x1", "y1"))
    if not has_bbox:
        if file_id not in allowed:
            return {**item, "photo": None}
        record = await _cached_record(file_id, company_id, record_cache)
        if record is None or not record.content_type.startswith("image/"):
            return {**item, "photo": None}
        return {**item, "photo": {"file_id": file_id}}

    if file_id not in allowed:
        return {**item, "photo": None}
    try:
        page_raw = photo_raw.get("page", 0)
        if not isinstance(page_raw, int) or page_raw < 0:
            raise ValueError("photo.page must be a non-negative int")
        rect = NormalizedRect(
            x0=_require_norm_coord(photo_raw["x0"], field="photo.x0"),
            y0=_require_norm_coord(photo_raw["y0"], field="photo.y0"),
            x1=_require_norm_coord(photo_raw["x1"], field="photo.x1"),
            y1=_require_norm_coord(photo_raw["y1"], field="photo.y1"),
        )
        dish_name_raw = item.get("name")
        dish_name = (
            dish_name_raw
            if isinstance(dish_name_raw, str) and dish_name_raw.strip()
            else "dish"
        )
        cache_key = (file_id, page_raw)
        if cache_key not in raster_cache:
            record = await _cached_record(file_id, company_id, record_cache)
            if record is None:
                raise ValueError(f"file not found: {file_id}")
            raster_cache[cache_key] = await load_page_raster_bytes(
                file_id=file_id,
                page=page_raw,
                content_type=record.content_type,
                original_name=record.original_name,
            )
        cropped = crop_image_bytes(raster_cache[cache_key], rect)
        ref = await persist_cropped_image(
            files_service,
            cropped_jpeg=cropped,
            dish_name=dish_name,
            source_file_id=file_id,
            page=page_raw,
        )
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "files.image_region.crop_failed",
            file_id=file_id,
            error=str(exc),
        )
        return {**item, "photo": None}
    if ref.file_id is None or ref.file_id.strip() == "":
        return {**item, "photo": None}
    return {**item, "photo": {"file_id": ref.file_id}}


async def _cached_record(
    file_id: str,
    company_id: str,
    cache: dict[str, FileRecord],
) -> FileRecord | None:
    if file_id in cache:
        return cache[file_id]
    record = await FileRecord.by_file_id(file_id, company_id)
    if record is not None:
        cache[file_id] = record
    return record


__all__ = [
    "NormalizedRect",
    "crop_file_region",
    "crop_image_bytes",
    "load_page_raster_bytes",
    "materialize_image_regions",
    "persist_cropped_image",
    "pixel_box",
    "raster_pdf_page",
    "safe_crop_filename",
]
