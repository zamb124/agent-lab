"""Варианты изображений: parse `?v=`, рендер Pillow, e2e materialize по download."""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest
from PIL import Image

from core.files.image_variants.render import render_variant
from core.files.image_variants.variants import (
    IMAGE_VARIANT_SIZES,
    parse_variant_param,
    variant_entry,
    variant_family_keys,
    variant_object_key,
)
from core.files.models import FileRecord
from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
    platform_auxiliary_upload_spec_json,
)


def _png_bytes(width: int, height: int, color: tuple[int, int, int] = (200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _webp_size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as img:
        assert img.format == "WEBP"
        return img.size


def _record(**overrides: object) -> FileRecord:
    now = datetime.now(UTC)
    base = {
        "file_id": "file_x",
        "company_id": "company_x",
        "storage_id": "platform",
        "s3_key": "company_x/file_x/abc/original.png",
        "original_name": "original.png",
        "content_type": "image/png",
        "file_size": 100,
        "checksum": "a" * 64,
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }
    return FileRecord.model_validate({**base, **overrides})


class TestParseVariantParam:
    def test_sizes(self) -> None:
        for size in IMAGE_VARIANT_SIZES:
            req = parse_variant_param(size)
            assert req.size == size
            assert req.square is False
            assert req.name == size

    def test_square_mode(self) -> None:
        req = parse_variant_param("md!sq")
        assert req.size == "md"
        assert req.square is True
        assert req.name == "md_sq"

    def test_case_and_space_normalized(self) -> None:
        assert parse_variant_param(" LG ").name == "lg"

    @pytest.mark.parametrize("raw", ["", "xs", "sm!", "sm!crop", "sm!sq!x", "!sq", "xlg"])
    def test_invalid(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_variant_param(raw)


class TestRenderVariant:
    def test_contain_keeps_aspect_no_upscale(self) -> None:
        rendered = render_variant(
            _png_bytes(480, 240), name="lg", size_px=1200, square=False
        )
        assert _webp_size(rendered.data) == (480, 240)
        assert rendered.width == 480

    def test_contain_downscales(self) -> None:
        rendered = render_variant(
            _png_bytes(2000, 1000), name="md", size_px=480, square=False
        )
        assert _webp_size(rendered.data) == (480, 240)

    def test_square_crops_to_square(self) -> None:
        rendered = render_variant(
            _png_bytes(2000, 1000), name="sm_sq", size_px=160, square=True
        )
        assert _webp_size(rendered.data) == (160, 160)

    def test_non_image_bytes_rejected(self) -> None:
        with pytest.raises(ValueError):
            render_variant(b"not an image", name="sm", size_px=160, square=False)


class TestVariantKeys:
    def test_object_key_deterministic_and_versioned(self) -> None:
        record = _record()
        key = variant_object_key(record, "sm_sq")
        assert key.endswith("v_sm_sq.webp")
        assert key == variant_object_key(record, "sm_sq")
        changed = _record(checksum="b" * 64)
        assert variant_object_key(changed, "sm_sq") != key

    def test_family_keys_only_derived(self) -> None:
        record = _record(
            metadata={
                "image_variants": {
                    "sm": {"key": "company_x/file_x/a/v_sm.webp"},
                    "broken": {"no_key": 1},
                    "other": "garbage",
                }
            }
        )
        assert variant_family_keys(record) == ["company_x/file_x/a/v_sm.webp"]
        assert variant_entry(record, "sm") is not None
        assert variant_entry(record, "broken") is None


@pytest.mark.asyncio
async def test_download_variant_materializes_and_caches(
    frontend_client_with_auth, unique_id: str
):
    """Первый `?v=` рендерит вариант из оригинала, второй — отдаёт материализованный."""
    content = _png_bytes(2000, 1000)
    upload = await chunked_upload_file(
        frontend_client_with_auth,
        {},
        content=content,
        original_name=f"img-{unique_id}.png",
        content_type="image/png",
        spec_json=platform_auxiliary_upload_spec_json(is_public=True),
        files_api_prefix="/frontend/api/v1/files",
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file_id"]

    base = f"/frontend/api/v1/files/download/{file_id}"
    original = await frontend_client_with_auth.get(base)
    assert original.status_code == 200
    assert original.content == content

    first = await frontend_client_with_auth.get(f"{base}?v=sm!sq")
    assert first.status_code == 200, first.text
    assert first.headers["content-type"] == "image/webp"
    assert _webp_size(first.content) == (160, 160)

    second = await frontend_client_with_auth.get(f"{base}?v=sm!sq")
    assert second.status_code == 200
    assert second.content == first.content

    contain = await frontend_client_with_auth.get(f"{base}?v=md")
    assert contain.status_code == 200
    assert _webp_size(contain.content) == (480, 240)


@pytest.mark.asyncio
async def test_download_variant_rejects_invalid_and_non_image(
    frontend_client_with_auth, unique_id: str
):
    upload = await chunked_upload_file(
        frontend_client_with_auth,
        {},
        content=_png_bytes(64, 64),
        original_name=f"img-{unique_id}.png",
        content_type="image/png",
        spec_json=platform_auxiliary_upload_spec_json(is_public=True),
        files_api_prefix="/frontend/api/v1/files",
    )
    file_id = upload.json()["file_id"]
    base = f"/frontend/api/v1/files/download/{file_id}"

    bad = await frontend_client_with_auth.get(f"{base}?v=bogus")
    assert bad.status_code == 404
    empty = await frontend_client_with_auth.get(f"{base}?v=")
    assert empty.status_code == 400

    text = await chunked_upload_file(
        frontend_client_with_auth,
        {},
        content=b"plain text, not an image",
        original_name=f"doc-{unique_id}.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(is_public=True),
        files_api_prefix="/frontend/api/v1/files",
    )
    text_id = text.json()["file_id"]
    unsupported = await frontend_client_with_auth.get(
        f"/frontend/api/v1/files/download/{text_id}?v=sm"
    )
    assert unsupported.status_code == 404
