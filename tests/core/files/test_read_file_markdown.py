"""Unit: page_to_markdown / data URI export."""

from __future__ import annotations

import base64

from core.files.reader.markdown import markdown_with_data_uris, page_to_markdown
from core.files.reader.models import (
    ContentMode,
    ExtractBlock,
    ExtractBlockKind,
    NestedContent,
    ReadAssetKind,
    UniversalPage,
)


def test_page_to_markdown_image_and_other_anchors() -> None:
    page = UniversalPage(
        index=0,
        label="page_1",
        text="Hello body",
        content_mode=ContentMode.FULL,
        blocks=[ExtractBlock(kind=ExtractBlockKind.PARAGRAPH, text="Hello body")],
    )
    nested = [
        NestedContent(
            anchor="p0_n1",
            original_name="doc.pdf#p0_n1",
            content_type="image/png",
            kind=ReadAssetKind.EMBEDDED_IMAGE,
            checksum="a" * 64,
            page_index=0,
            bytes_b64=base64.b64encode(b"png").decode("ascii"),
        ),
        NestedContent(
            anchor="p0_n2",
            original_name="doc.pdf#p0_n2",
            content_type="application/pdf",
            kind=ReadAssetKind.ATTACHMENT,
            checksum="b" * 64,
            page_index=0,
        ),
    ]
    md = page_to_markdown(page, nested=nested)
    assert "Hello body" in md
    assert "![p0_n1]" in md
    assert "[p0_n2](nested:doc.pdf#p0_n2)" in md
    assert "data:" not in md

    exported = markdown_with_data_uris(md, nested)
    assert "data:image/png;base64," in exported
    assert "[p0_n2](nested:doc.pdf#p0_n2)" in exported
