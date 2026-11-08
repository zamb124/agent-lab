"""Crop нормализованного региона изображения и PDF-страницы."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from core.files.image_region import (
    NormalizedRect,
    crop_image_bytes,
    jpeg_thumbnail_bytes,
    photo_bbox_area,
    photo_needs_image_edit,
    photo_needs_locate,
    pixel_box,
    safe_crop_filename,
)
from core.files.reader.models import (
    ContentMode,
    FileExtract,
    FileReadKind,
    NestedContent,
    PageLayout,
    PageLayoutKind,
    ReadAssetKind,
    ReadLane,
    UniversalPage,
)
from core.files.reader.nested import page_raster_bytes_from_extract, read_page_raster_bytes
from core.files.reader.service import iter_pdf_read_pages
from core.types import JsonObject
from tests.core.files.golden.bytes import pdf_printed_page


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
        pixel = rgb.getpixel((width // 2, height // 2))
        if not isinstance(pixel, tuple) or len(pixel) < 3:
            raise AssertionError(f"expected RGB pixel, got {pixel!r}")
        return int(pixel[0]), int(pixel[1]), int(pixel[2])


class TestNormalizedRect:
    def test_rejects_unordered(self) -> None:
        with pytest.raises(ValueError):
            _ = NormalizedRect(x0=0.5, y0=0.1, x1=0.2, y1=0.4)


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
            _ = pixel_box(
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
            _ = crop_image_bytes(b"not-an-image", NormalizedRect(x0=0, y0=0, x1=1, y1=1))


class TestFileReaderPageRaster:
    def test_force_raster_decodable(self) -> None:
        pdf_bytes = pdf_printed_page("PAGE_RASTER_MARKER", width=200, height=200)
        warnings: list[str] = []
        pages = list(
            iter_pdf_read_pages(
                pdf_bytes,
                "marker.pdf",
                page_indices={0},
                force_raster=True,
                warnings=warnings,
            )
        )
        assert len(pages) == 1
        assert any(asset.kind is ReadAssetKind.PAGE_RASTER for asset in pages[0].assets)
        raster = read_page_raster_bytes(pages[0])
        with Image.open(io.BytesIO(raster)) as img:
            assert img.format == "PNG"
            assert img.size[0] > 0 and img.size[1] > 0

    def test_page_out_of_range_empty(self) -> None:
        pdf_bytes = pdf_printed_page("ONE", width=100, height=100)
        warnings: list[str] = []
        pages = list(
            iter_pdf_read_pages(
                pdf_bytes,
                "one.pdf",
                page_indices={3},
                force_raster=True,
                warnings=warnings,
            )
        )
        assert pages == []

    def test_page_raster_bytes_from_extract(self) -> None:
        png = _quadrant_collage()
        nested = NestedContent(
            anchor="p0_n1",
            original_name="menu.pdf#p0_n1.png",
            content_type="image/png",
            kind=ReadAssetKind.PAGE_RASTER,
            checksum="abc",
            page_index=0,
            bytes_b64=base64.b64encode(png).decode("utf-8"),
        )
        extract = FileExtract(
            file_name="menu.pdf",
            kind=FileReadKind.PDF,
            mime_type="application/pdf",
            read_lane=ReadLane.VISION,
            page_layout=PageLayout(
                kind=PageLayoutKind.NATIVE, pages_total=1, page_size=0
            ),
            pages=[
                UniversalPage(
                    index=0,
                    label="1",
                    text="",
                    content_mode=ContentMode.VISION,
                    nested=[nested],
                )
            ],
        )
        assert page_raster_bytes_from_extract(extract, page=0) == png
        with pytest.raises(ValueError, match="not in extract"):
            _ = page_raster_bytes_from_extract(extract, page=1)


class TestSafeCropFilename:
    def test_slugifies(self) -> None:
        assert safe_crop_filename("Caesar Salad") == "caesar-salad-crop.jpg"
        assert safe_crop_filename("Soup #1!") == "soup-1-crop.jpg"
        assert safe_crop_filename("   ") == "dish-crop.jpg"
        assert safe_crop_filename("Борщ").endswith("-crop.jpg")


class TestPhotoNeedsLocate:
    def test_null_and_file_id_only(self) -> None:
        assert photo_needs_locate(None) is True
        assert photo_needs_locate({"file_id": "file_abc"}) is True
        assert photo_needs_image_edit(None) is False
        assert photo_needs_image_edit({"file_id": "file_abc"}) is False

    def test_source_page_needs_image_edit(self) -> None:
        photo: JsonObject = {"file_id": "file_abc", "page": 2}
        assert photo_needs_image_edit(photo) is True
        assert photo_needs_locate(photo) is True

    def test_already_cropped_skips_edit(self) -> None:
        photo: JsonObject = {
            "file_id": "file_crop",
            "page": 0,
            "already_cropped": True,
        }
        assert photo_needs_image_edit(photo) is False

    def test_tight_bbox_area(self) -> None:
        photo: JsonObject = {
            "file_id": "file_abc",
            "page": 1,
            "x0": 0.1,
            "y0": 0.2,
            "x1": 0.4,
            "y1": 0.5,
        }
        assert photo_bbox_area(photo) == pytest.approx(0.09)
        assert photo_needs_locate(photo) is False

    def test_full_frame_needs_locate(self) -> None:
        photo: JsonObject = {
            "file_id": "file_abc",
            "page": 0,
            "x0": 0.0,
            "y0": 0.0,
            "x1": 1.0,
            "y1": 1.0,
        }
        assert photo_needs_locate(photo) is True


class TestJpegThumbnailBytes:
    def test_shrinks_long_edge(self) -> None:
        image = Image.new("RGB", (3000, 1000), (10, 20, 30))
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        jpeg = jpeg_thumbnail_bytes(buf.getvalue(), max_edge=2000)
        with Image.open(io.BytesIO(jpeg)) as out:
            assert max(out.size) == 2000
            assert out.format == "JPEG"
