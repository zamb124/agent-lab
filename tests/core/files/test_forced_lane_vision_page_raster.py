"""forced_lane=VISION отдаёт page_raster nested с bytes."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from core.files.file_ref import FileRef
from core.files.reader import FileReader, NestedMode, ReadLane
from core.files.reader.models import ReadAssetKind, ReadFileArgs
from core.files.reader.nested import page_raster_bytes_from_extract
from tests.core.files.golden.bytes import pdf_text_and_embedded_image

_MOCK_VISION = "MOCK_VISION"
_TEXT_MARKER = "VISION_PAGE_RASTER_MARKER"


def _temp_file_ref(raw: bytes, name: str, content_type: str) -> FileRef:
    path = Path(tempfile.mkdtemp()) / name
    _ = path.write_bytes(raw)
    return FileRef(
        original_name=name,
        url=str(path),
        content_type=content_type,
        file_size=len(raw),
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_forced_lane_vision_pdf_page_raster_bytes(
    mock_llm_with_queue: Callable[[list[str]], None],
) -> None:
    file_ref = _temp_file_ref(
        pdf_text_and_embedded_image(_TEXT_MARKER),
        "vision_page.pdf",
        "application/pdf",
    )
    mock_llm_with_queue([_MOCK_VISION, _MOCK_VISION])
    if file_ref.url is None:
        raise AssertionError("temp file_ref.url is required")
    path = Path(file_ref.url)
    extract = await FileReader().read(
        path,
        ReadFileArgs(
            page_start=0,
            page_end=0,
            forced_lane=ReadLane.VISION,
            recursive=False,
            nested_mode=NestedMode.REFS,
        ),
        file_name=file_ref.original_name,
    )
    assert extract.read_lane is ReadLane.VISION
    assert extract.pages
    kinds = [item.kind for item in extract.pages[0].nested]
    assert ReadAssetKind.PAGE_RASTER in kinds
    raster = page_raster_bytes_from_extract(extract, page=0)
    assert len(raster) > 32
    assert _MOCK_VISION in extract.pages[0].text
