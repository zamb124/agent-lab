"""Crop нормализованного региона изображения и PDF-страницы."""

from __future__ import annotations

import io

import pymupdf
import pytest
from PIL import Image

from core.files.image_region import (
    NormalizedRect,
    _require_norm_coord,
    crop_image_bytes,
    pixel_box,
    raster_pdf_page,
    safe_crop_filename,
)


def _quadrant_collage() -> bytes:
    """2x2: красный | зелёный / синий | жёлтый, 200x200."""
    image = Image.new("RGB", (200, 200), (0, 0, 0))
    image.paste(Image.new("RGB", (100, 100), (200, 20, 20)), (0, 0))
    image.paste(Image.new("RGB", (100, 100), (20, 200, 20)), (100, 0))
    image.paste(Image.new("RGB", (100, 100), (20, 20, 200)), (0, 100))
    image.paste(Image.new("RGB", (100, 100), (220, 220, 20)), (100, 100))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _center_color(jpeg: bytes) -> tuple[int, int, int]:
    with Image.open(io.BytesIO(jpeg)) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        return rgb.getpixel((width // 2, height // 2))


class TestRequireNormCoord:
    def test_accepts_int_and_float(self) -> None:
        assert _require_norm_coord(0, field="photo.x0") == 0.0
        assert _require_norm_coord(0.25, field="photo.x0") == 0.25

    def test_rejects_bool_and_str(self) -> None:
        with pytest.raises(ValueError, match="must be a number"):
            _require_norm_coord(True, field="photo.x0")
        with pytest.raises(ValueError, match="must be a number"):
            _require_norm_coord("0.1", field="photo.x0")


class TestNormalizedRect:
    def test_rejects_unordered(self) -> None:
        with pytest.raises(ValueError):
            NormalizedRect(x0=0.5, y0=0.1, x1=0.2, y1=0.4)


class TestPixelBox:
    def test_clamp_and_min_size(self) -> None:
        box = pixel_box(
            NormalizedRect(x0=0.0, y0=0.0, x1=0.5, y1=0.5),
            width=200,
            height=200,
        )
        assert box == (0, 0, 100, 100)

    def test_too_small_raises(self) -> None:
        with pytest.raises(ValueError, match="smaller than"):
            pixel_box(
                NormalizedRect(x0=0.0, y0=0.0, x1=0.01, y1=0.01),
                width=100,
                height=100,
            )


class TestCropImageBytes:
    def test_collage_quadrants(self) -> None:
        raw = _quadrant_collage()
        red = crop_image_bytes(
            raw, NormalizedRect(x0=0.0, y0=0.0, x1=0.5, y1=0.5)
        )
        green = crop_image_bytes(
            raw, NormalizedRect(x0=0.5, y0=0.0, x1=1.0, y1=0.5)
        )
        blue = crop_image_bytes(
            raw, NormalizedRect(x0=0.0, y0=0.5, x1=0.5, y1=1.0)
        )
        yellow = crop_image_bytes(
            raw, NormalizedRect(x0=0.5, y0=0.5, x1=1.0, y1=1.0)
        )
        assert _center_color(red)[0] > 150
        assert _center_color(green)[1] > 150
        assert _center_color(blue)[2] > 150
        assert _center_color(yellow)[0] > 150 and _center_color(yellow)[1] > 150

    def test_undecodable_raises(self) -> None:
        with pytest.raises(ValueError, match="not a decodable image"):
            crop_image_bytes(b"not-an-image", NormalizedRect(x0=0, y0=0, x1=1, y1=1))


class TestRasterPdfPage:
    def test_raster_and_crop_known_region(self) -> None:
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=200)
        # красный прямоугольник в левом верхнем квадранте (PyMuPDF: y вниз)
        shape = page.new_shape()
        shape.draw_rect(pymupdf.Rect(0, 0, 100, 100))
        shape.finish(color=(1, 0, 0), fill=(1, 0, 0))
        shape.commit()
        pdf_bytes = doc.tobytes()
        doc.close()

        raster = raster_pdf_page(pdf_bytes, 0)
        with Image.open(io.BytesIO(raster)) as img:
            assert img.size[0] == 400
            assert img.size[1] == 400

        cropped = crop_image_bytes(
            raster, NormalizedRect(x0=0.0, y0=0.0, x1=0.5, y1=0.5)
        )
        r, g, b = _center_color(cropped)
        assert r > 150
        assert g < 80
        assert b < 80

    def test_page_out_of_range(self) -> None:
        doc = pymupdf.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        with pytest.raises(ValueError, match="out of range"):
            raster_pdf_page(pdf_bytes, 3)


class TestSafeCropFilename:
    def test_slugifies(self) -> None:
        assert safe_crop_filename("Caesar Salad") == "caesar-salad-crop.jpg"
        assert safe_crop_filename("Soup #1!") == "soup-1-crop.jpg"
        assert safe_crop_filename("   ") == "dish-crop.jpg"
        assert safe_crop_filename("Борщ").endswith("-crop.jpg")
