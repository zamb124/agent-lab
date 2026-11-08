"""Нормализованный crop региона изображения или PDF-страницы; NanoBanana crop по source page."""

from __future__ import annotations

import base64
import math
import re
from io import BytesIO
from typing import Literal, Protocol

from PIL import Image
from pydantic import Field, model_validator

from core.context import require_active_company
from core.files.create_spec import FileSourceKind, FileSourceRef
from core.files.file_ref import FileRef, stored_file_ref
from core.files.models import FileRecord
from core.files.reader.models import FileReadKind
from core.files.reader.nested import read_page_raster_bytes
from core.files.reader.service import FileReader, iter_pdf_read_pages, read_stored_file_by_id
from core.files.registry import build_file_create_spec
from core.files.service import FilesService
from core.logging import get_logger
from core.models.base import StrictBaseModel
from core.types import JsonArray, JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)

_MIN_CROP_PX = 8
_JPEG_QUALITY = 90
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
# Рамка ≥ этой доли площади кадра — не crop блюда (обложка / вся страница).
_LOOSE_PHOTO_AREA = 0.85
_IMAGE_EDIT_MAX_EDGE = 2000


class ImageEditCropper(Protocol):
    """Image-edit (NanoBanana) → file_id кропа; prompt целиком задаёт caller."""

    async def generate_images(
        self,
        prompt: str,
        reference_file_ids: list[str] | None = None,
        num_images: int = 1,
        is_editing: bool = False,
        editing_mode: Literal["product_placement", "crop"] = "product_placement",
    ) -> list[str]: ...


def _require_norm_coord(raw: JsonValue, *, field: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"{field} must be a number")
    return float(raw)


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


def safe_crop_filename(name: str) -> str:
    stripped = name.strip().lower().replace(" ", "-")
    cleaned = _SAFE_NAME_RE.sub("-", stripped)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-._")
    if cleaned == "":
        cleaned = "dish"
    return f"{cleaned[:80]}-crop.jpg"


async def page_raster_bytes(*, file_id: str, page: int) -> bytes:
    """Байты растра страницы через канон FileReader (PDF force_raster / image raw)."""
    if page < 0:
        raise ValueError("page must be >= 0")
    raw, original_name = await read_stored_file_by_id(file_id)
    info = FileReader().recognize_file_type(file_name=original_name, head=raw[:8192])
    if info.detected_kind is FileReadKind.PDF:
        warnings: list[str] = []
        pages = list(
            iter_pdf_read_pages(
                raw,
                original_name,
                page_indices={page},
                force_raster=True,
                warnings=warnings,
            )
        )
        if not pages:
            raise ValueError(f"PDF page {page} out of range")
        return read_page_raster_bytes(pages[0])
    if info.detected_kind is FileReadKind.IMAGE:
        if page != 0:
            raise ValueError("page must be 0 for image/* sources")
        return raw
    raise ValueError(f"unsupported kind for page raster: {info.detected_kind.value}")


def jpeg_thumbnail_bytes(raw: bytes, *, max_edge: int = _IMAGE_EDIT_MAX_EDGE) -> bytes:
    """RGB JPEG с длинной стороной ≤ ``max_edge`` (вход NanoBanana crop)."""
    if max_edge < 1:
        raise ValueError("max_edge must be >= 1")
    try:
        image = Image.open(BytesIO(raw))
    except Image.UnidentifiedImageError as exc:
        raise ValueError("file content is not a decodable image") from exc
    rgb = image.convert("RGB")
    thumb = rgb.copy()
    thumb.thumbnail((max_edge, max_edge))
    buffer = BytesIO()
    thumb.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return buffer.getvalue()


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
    raster = await page_raster_bytes(file_id=file_id, page=page)
    cropped = crop_image_bytes(raster, rect)
    return await persist_cropped_image(
        files_service,
        cropped_jpeg=cropped,
        dish_name=dish_name,
        source_file_id=file_id,
        page=page,
    )


def photo_bbox_area(photo: JsonObject) -> float | None:
    """Площадь нормализованного bbox или None, если координат нет/невалидны."""
    try:
        rect = NormalizedRect(
            x0=_require_norm_coord(photo["x0"], field="photo.x0"),
            y0=_require_norm_coord(photo["y0"], field="photo.y0"),
            x1=_require_norm_coord(photo["x1"], field="photo.x1"),
            y1=_require_norm_coord(photo["y1"], field="photo.y1"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    return (rect.x1 - rect.x0) * (rect.y1 - rect.y0)


def photo_needs_image_edit(photo: JsonValue) -> bool:
    """True, если нужен NanoBanana crop: source page без tight bbox, ещё не вырезан."""
    if not isinstance(photo, dict):
        return False
    if photo.get("already_cropped") is True:
        return False
    file_id = photo.get("file_id")
    page = photo.get("page")
    if not isinstance(file_id, str) or file_id.strip() == "":
        return False
    if not isinstance(page, int) or page < 0:
        return False
    area = photo_bbox_area(photo)
    if area is not None and area < _LOOSE_PHOTO_AREA:
        return False
    return True


def photo_needs_locate(photo: JsonValue) -> bool:
    """True для null/loose bbox или source page без tight bbox (нужен crop)."""
    if photo is None:
        return True
    if not isinstance(photo, dict):
        return True
    if photo.get("already_cropped") is True:
        return False
    if photo_needs_image_edit(photo):
        return True
    area = photo_bbox_area(photo)
    if area is None:
        return True
    return area >= _LOOSE_PHOTO_AREA


def _format_prompt(
    template: str,
    *,
    name: str,
    page: int,
    ingredients: list[str],
) -> str:
    ingredients_text = "; ".join(ingredients) if ingredients else ""
    return (
        template.replace("{name}", name)
        .replace("{page}", str(page))
        .replace("{ingredients}", ingredients_text)
    )


def _item_ingredients(item: JsonObject) -> list[str]:
    raw = item.get("ingredients")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, str) and entry.strip():
            out.append(entry.strip())
    return out


async def _photo_with_bytes(
    *,
    file_id: str,
    content_type: str,
    include_bytes_b64: bool,
) -> JsonObject:
    photo: JsonObject = {
        "file_id": file_id,
        "content_type": content_type,
        "already_cropped": True,
    }
    if not include_bytes_b64:
        return photo
    raw, _name = await read_stored_file_by_id(file_id)
    photo["bytes_b64"] = base64.b64encode(raw).decode("ascii")
    return photo


async def _persist_page_reference(
    files_service: FilesService,
    *,
    source_file_id: str,
    page: int,
    company_id: str,
    record_cache: dict[str, FileRecord],
    page_ref_cache: dict[tuple[str, int], str],
) -> str:
    """Растр source page → ephemeral JPEG ≤2000px для NanoBanana reference."""
    cache_key = (source_file_id, page)
    cached = page_ref_cache.get(cache_key)
    if cached is not None:
        return cached
    record = await _cached_record(source_file_id, company_id, record_cache)
    if record is None:
        raise ValueError(f"file not found: {source_file_id}")
    raster = await page_raster_bytes(file_id=source_file_id, page=page)
    jpeg = jpeg_thumbnail_bytes(raster)
    original_name = f"{source_file_id}-p{page}.jpg"
    spec = build_file_create_spec(
        source_kind=FileSourceKind.GENERATED_EPHEMERAL,
        source_ref=FileSourceRef(entity_id=source_file_id),
        metadata={"raster_of": source_file_id, "page": page},
    )
    created = await files_service.create(
        spec,
        jpeg,
        original_name=original_name,
        content_type="image/jpeg",
    )
    ref = stored_file_ref(created)
    if ref.file_id is None or not ref.file_id.strip():
        raise ValueError("persist page raster returned empty file_id")
    page_ref = ref.file_id.strip()
    page_ref_cache[cache_key] = page_ref
    return page_ref


async def locate_image_regions(
    image_edit: ImageEditCropper,
    *,
    sections: JsonArray,
    crop_prompt_template: str,
    files_service: FilesService,
    studio_prompt_template: str = "",
    include_bytes_b64: bool = False,
) -> JsonArray:
    """NanoBanana crop по ``photo.file_id`` + ``photo.page``; prompt — шаблон caller'а.

    ``photo=null`` — блюда без фото, пропускается. Vision/bbox-псевдокроп нет.
    Плейсхолдеры шаблона: ``{name}``, ``{page}``, ``{ingredients}``.
    """
    if crop_prompt_template.strip() == "":
        raise ValueError("crop_prompt_template must be non-empty")
    company_id = require_active_company().company_id
    record_cache: dict[str, FileRecord] = {}
    page_ref_cache: dict[tuple[str, int], str] = {}
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
                await _crop_item_photo(
                    image_edit=image_edit,
                    files_service=files_service,
                    company_id=company_id,
                    item=item,
                    crop_prompt_template=crop_prompt_template,
                    studio_prompt_template=studio_prompt_template,
                    include_bytes_b64=include_bytes_b64,
                    record_cache=record_cache,
                    page_ref_cache=page_ref_cache,
                )
            )
        out_sections.append({**section, "items": new_items})
    return out_sections


async def _crop_item_photo(
    *,
    image_edit: ImageEditCropper,
    files_service: FilesService,
    company_id: str,
    item: JsonObject,
    crop_prompt_template: str,
    studio_prompt_template: str,
    include_bytes_b64: bool,
    record_cache: dict[str, FileRecord],
    page_ref_cache: dict[tuple[str, int], str],
) -> JsonObject:
    photo_raw = item.get("photo")
    if photo_raw is None:
        return item
    if not isinstance(photo_raw, dict):
        return {**item, "photo": None}
    if photo_raw.get("already_cropped") is True:
        file_id_val = photo_raw.get("file_id")
        if not isinstance(file_id_val, str) or file_id_val.strip() == "":
            return {**item, "photo": None}
        content_type_raw = photo_raw.get("content_type")
        content_type = (
            content_type_raw.strip()
            if isinstance(content_type_raw, str) and content_type_raw.strip()
            else "image/jpeg"
        )
        return {
            **item,
            "photo": await _photo_with_bytes(
                file_id=file_id_val.strip(),
                content_type=content_type,
                include_bytes_b64=include_bytes_b64,
            ),
        }
    if not photo_needs_image_edit(photo_raw):
        # tight bbox → files_materialize_image_regions; иначе без source page.
        return item

    file_id_raw = photo_raw.get("file_id")
    page_raw = photo_raw.get("page")
    if not isinstance(file_id_raw, str) or file_id_raw.strip() == "":
        return {**item, "photo": None}
    if not isinstance(page_raw, int) or page_raw < 0:
        return {**item, "photo": None}
    source_file_id = file_id_raw.strip()
    page = page_raw
    name_raw = item.get("name")
    name = name_raw.strip() if isinstance(name_raw, str) else ""
    if name == "":
        return {**item, "photo": None}

    try:
        page_ref = await _persist_page_reference(
            files_service,
            source_file_id=source_file_id,
            page=page,
            company_id=company_id,
            record_cache=record_cache,
            page_ref_cache=page_ref_cache,
        )
    except ValueError as exc:
        logger.warning(
            "files.image_region.page_raster_failed",
            file_id=source_file_id,
            page=page,
            dish=name,
            error=str(exc),
        )
        return {**item, "photo": None}

    crop_prompt = _format_prompt(
        crop_prompt_template,
        name=name,
        page=page,
        ingredients=_item_ingredients(item),
    )
    try:
        file_ids = await image_edit.generate_images(
            crop_prompt,
            reference_file_ids=[page_ref],
            num_images=1,
            is_editing=True,
            editing_mode="crop",
        )
    except (ValueError, RuntimeError) as exc:
        logger.warning(
            "files.image_region.image_edit_failed",
            dish=name,
            page_ref=page_ref,
            error=str(exc),
        )
        return {**item, "photo": None}
    if not file_ids or not file_ids[0].strip() or file_ids[0].strip() == page_ref:
        return {**item, "photo": None}
    crop_id = file_ids[0].strip()

    studio = studio_prompt_template.strip()
    if studio:
        studio_prompt = _format_prompt(
            studio,
            name=name,
            page=page,
            ingredients=_item_ingredients(item),
        )
        try:
            studio_ids = await image_edit.generate_images(
                studio_prompt,
                reference_file_ids=[crop_id],
                num_images=1,
                is_editing=True,
                editing_mode="crop",
            )
        except (ValueError, RuntimeError) as exc:
            logger.warning(
                "files.image_region.studio_failed",
                dish=name,
                crop_id=crop_id,
                error=str(exc),
            )
            studio_ids = []
        if studio_ids and studio_ids[0].strip() and studio_ids[0].strip() != crop_id:
            crop_id = studio_ids[0].strip()

    record = await _cached_record(crop_id, company_id, record_cache)
    content_type = (
        record.content_type.strip()
        if record is not None and record.content_type.strip()
        else "image/png"
    )
    return {
        **item,
        "photo": await _photo_with_bytes(
            file_id=crop_id,
            content_type=content_type,
            include_bytes_b64=include_bytes_b64,
        ),
    }


async def materialize_image_regions(
    files_service: FilesService,
    *,
    sections: JsonArray,
    attachment_file_ids: list[str],
    include_bytes_b64: bool = False,
) -> JsonArray:
    """Заменяет photo bbox на ``{file_id}`` PIL-кропа; already_cropped — как есть (+b64)."""
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
                    include_bytes_b64=include_bytes_b64,
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
    include_bytes_b64: bool,
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

    if photo_raw.get("already_cropped") is True:
        content_type_raw = photo_raw.get("content_type")
        content_type = (
            content_type_raw.strip()
            if isinstance(content_type_raw, str) and content_type_raw.strip()
            else "image/jpeg"
        )
        return {
            **item,
            "photo": await _photo_with_bytes(
                file_id=file_id,
                content_type=content_type,
                include_bytes_b64=include_bytes_b64,
            ),
        }

    has_bbox = all(key in photo_raw for key in ("x0", "y0", "x1", "y1"))
    if not has_bbox:
        return {**item, "photo": None}

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
        if photo_bbox_area(
            {"x0": rect.x0, "y0": rect.y0, "x1": rect.x1, "y1": rect.y1}
        ) is not None and (rect.x1 - rect.x0) * (rect.y1 - rect.y0) >= _LOOSE_PHOTO_AREA:
            raise ValueError("photo bbox covers almost the entire frame")
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
            raster_cache[cache_key] = await page_raster_bytes(
                file_id=file_id,
                page=page_raw,
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
    return {
        **item,
        "photo": await _photo_with_bytes(
            file_id=ref.file_id.strip(),
            content_type="image/jpeg",
            include_bytes_b64=include_bytes_b64,
        ),
    }


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
    "ImageEditCropper",
    "NormalizedRect",
    "crop_file_region",
    "crop_image_bytes",
    "jpeg_thumbnail_bytes",
    "locate_image_regions",
    "materialize_image_regions",
    "page_raster_bytes",
    "persist_cropped_image",
    "photo_bbox_area",
    "photo_needs_image_edit",
    "photo_needs_locate",
    "pixel_box",
    "safe_crop_filename",
]
