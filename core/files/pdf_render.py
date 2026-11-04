"""Рендер страниц PDF в PNG для vision и превью."""

from __future__ import annotations

from typing import Protocol

import pymupdf

from core.imports import module_sdk

_PDF_RENDER_ZOOM = 2
_DEFAULT_MAX_PAGES = 8


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


def pdf_page_pngs(data: bytes, *, max_pages: int = _DEFAULT_MAX_PAGES) -> list[bytes]:
    """PNG первых ``max_pages`` страниц PDF; пустой PDF — пустой список."""
    if max_pages < 1:
        raise ValueError("pdf_page_pngs: max_pages must be >= 1")
    fitz = module_sdk(pymupdf, _FitzModule)
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        limit = min(doc.page_count, max_pages)
        matrix = fitz.Matrix(_PDF_RENDER_ZOOM, _PDF_RENDER_ZOOM)
        return [doc[index].get_pixmap(matrix=matrix).tobytes("png") for index in range(limit)]
    finally:
        doc.close()


__all__ = ["pdf_page_pngs"]
