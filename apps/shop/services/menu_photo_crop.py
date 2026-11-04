"""Вырезание фото блюда из вложения меню: изображение или страница PDF → JPEG."""

from __future__ import annotations

from io import BytesIO
from typing import Protocol

import pymupdf
from PIL import Image, ImageOps

from apps.shop.models.import_api import ShopMenuPhotoCrop
from core.errors.boundary import PlatformConflictError
from core.imports import module_sdk

_PDF_SIGNATURE = b"%PDF"
_PDF_RENDER_ZOOM = 3
_MAX_SIDE_PX = 1600
_JPEG_QUALITY = 88
MENU_PHOTO_CONTENT_TYPE = "image/jpeg"


class _PdfMatrix(Protocol):
    """Матрица масштаба страницы PDF."""


class _PdfPixmap(Protocol):
    def tobytes(self, output: str) -> bytes: ...


class _PdfPage(Protocol):
    def get_pixmap(self, *, matrix: _PdfMatrix) -> _PdfPixmap: ...


class _PdfDocument(Protocol):
    page_count: int

    def __getitem__(self, index: int) -> _PdfPage: ...
    def close(self) -> None: ...


class _FitzModule(Protocol):
    def open(self, *, stream: bytes, filetype: str) -> _PdfDocument: ...
    def Matrix(self, zoom_x: int, zoom_y: int) -> _PdfMatrix: ...


def _pdf_page_png(data: bytes, page_index: int) -> bytes:
    fitz = module_sdk(pymupdf, _FitzModule)
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if page_index >= doc.page_count:
            raise PlatformConflictError(
                f"PDF has {doc.page_count} pages, crop page {page_index}",
                error_code="shop_menu_photo_page_missing",
            )
        pixmap = doc[page_index].get_pixmap(matrix=fitz.Matrix(_PDF_RENDER_ZOOM, _PDF_RENDER_ZOOM))
        return pixmap.tobytes("png")
    finally:
        doc.close()


def crop_menu_photo(data: bytes, crop: ShopMenuPhotoCrop) -> bytes:
    """JPEG прямоугольника ``crop`` (доли страницы) не больше ``_MAX_SIDE_PX`` по стороне."""
    if data.startswith(_PDF_SIGNATURE):
        source = Image.open(BytesIO(_pdf_page_png(data, crop.page)))
    else:
        if crop.page != 0:
            raise PlatformConflictError(
                "image attachment has a single page", error_code="shop_menu_photo_page_missing"
            )
        source = ImageOps.exif_transpose(Image.open(BytesIO(data)))
    width, height = source.size
    box = (
        round(crop.x0 * width),
        round(crop.y0 * height),
        round(crop.x1 * width),
        round(crop.y1 * height),
    )
    if box[2] - box[0] < 1 or box[3] - box[1] < 1:
        raise PlatformConflictError("crop box is empty", error_code="shop_menu_photo_crop_empty")
    return _jpeg(source.crop(box))


def downloaded_photo_jpeg(data: bytes) -> bytes:
    """Скачанное фото блюда → JPEG не больше ``_MAX_SIDE_PX`` по стороне."""
    return _jpeg(ImageOps.exif_transpose(Image.open(BytesIO(data))))


def _jpeg(image: Image.Image) -> bytes:
    rgb = image.convert("RGB")
    rgb.thumbnail((_MAX_SIDE_PX, _MAX_SIDE_PX))
    out = BytesIO()
    rgb.save(out, format="JPEG", quality=_JPEG_QUALITY)
    return out.getvalue()
