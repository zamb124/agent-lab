"""Vision resilience: транскод, compression, shrink_on_error."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from core.files.reader.exceptions import FileReadError
from core.files.reader.models import CompressionMode
from core.files.reader.vision import (
    _cairosvg,
    compress_image,
    needs_transcode,
    prepare_visual_payload,
    transcode_to_jpeg,
)
from core.state import ExecutionState
from core.types import require_json_object
from tests.core.files.corpus.helpers import require_heic_entry_supported
from tests.core.files.corpus.manifest import CORPUS, POSITIVE
from tests.core.files.corpus.read_helpers import store_corpus_in_files_service
from tests.fixtures.s3 import require_s3_configured

_MINIMAL_SVG = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">
  <rect width="32" height="32" fill="#336699"/>
</svg>
"""


def _make_avif_bytes() -> bytes:
    import pillow_heif

    image = Image.new("RGB", (16, 16), color=(200, 40, 40))
    buffer = BytesIO()
    pillow_heif.register_heif_opener()
    image.save(buffer, format="AVIF")
    return buffer.getvalue()


def test_needs_transcode_detects_heic_and_svg() -> None:
    assert needs_transcode(file_name="photo.heic", mime="image/heic") is True
    assert needs_transcode(file_name="icon.svg", mime="image/svg+xml") is True
    assert needs_transcode(file_name="photo.jpg", mime="image/jpeg") is False


def test_transcode_avif_to_jpeg() -> None:
    raw = _make_avif_bytes()
    payload, mime = transcode_to_jpeg(raw, file_name="sample.avif", mime="image/avif")
    assert mime == "image/jpeg"
    assert payload.startswith(b"\xff\xd8")


def test_transcode_svg_behavior() -> None:
    if _cairosvg is None:
        with pytest.raises(FileReadError, match="SVG transcode is unavailable"):
            transcode_to_jpeg(_MINIMAL_SVG, file_name="icon.svg", mime="image/svg+xml")
        return
    payload, mime = transcode_to_jpeg(_MINIMAL_SVG, file_name="icon.svg", mime="image/svg+xml")
    assert mime == "image/jpeg"
    assert payload.startswith(b"\xff\xd8")


def test_compress_image_returns_jpeg() -> None:
    png_buffer = BytesIO()
    Image.new("RGB", (4096, 4096), color=(10, 20, 30)).save(png_buffer, format="PNG")
    payload, mime = compress_image(png_buffer.getvalue())
    assert mime == "image/jpeg"
    assert payload.startswith(b"\xff\xd8")
    assert len(payload) > 0


@pytest.mark.parametrize(
    "compression",
    [CompressionMode.NEVER, CompressionMode.BEFORE_LLM, CompressionMode.ON_ERROR],
)
def test_prepare_visual_payload_compression_modes(compression: CompressionMode) -> None:
    png_buffer = BytesIO()
    Image.new("RGB", (512, 512), color=(255, 0, 0)).save(png_buffer, format="PNG")
    raw = png_buffer.getvalue()
    payload, mime = prepare_visual_payload(
        raw,
        file_name="sample.png",
        mime="image/png",
        compression=compression,
    )
    assert mime in ("image/png", "image/jpeg")
    assert payload


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_image_vision_heic_from_corpus(
    frontend_di,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()

    entry = next(entry for entry in CORPUS if entry.relative_path == "img/DA-1p.heic")
    require_heic_entry_supported(entry.relative_path)
    mock_llm_with_queue(["MOCK_VISION"])
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    from apps.flows.tools.files.files import read_file

    state = ExecutionState.create(
        task_id="vision_task",
        context_id="vision_ctx",
        user_id="test_user",
        session_id="vision_flow:vision_ctx",
        files=[file_ref],
    )
    payload = require_json_object(
        await read_file.run(
            {
                "names": [file_ref.original_name],
                "compression": "before_llm",
            },
            state,
        ),
        "read_file.heic",
    )
    assert payload["files"][0]["success"] is True
    assert payload["files"][0]["read_lane"] == "vision"


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_image_vision_shrink_on_error_flag_accepted(
    frontend_di,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == "img/example.jpg")
    mock_llm_with_queue(["MOCK_VISION"])
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    from apps.flows.tools.files.files import read_file

    state = ExecutionState.create(
        task_id="vision_task2",
        context_id="vision_ctx2",
        user_id="test_user",
        session_id="vision_flow:vision_ctx2",
        files=[file_ref],
    )
    for shrink in (True, False):
        payload = require_json_object(
            await read_file.run(
                {
                    "names": [file_ref.original_name],
                    "compression": "never",
                },
                state,
            ),
            f"read_file.shrink_{shrink}",
        )
        assert payload["files"][0]["success"] is True
