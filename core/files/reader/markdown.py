"""Lossy markdown view страницы FileExtract / NestedContent."""

from __future__ import annotations

from core.files.reader.models import (
    NESTED_OMITTED_STUB,
    ExtractBlock,
    ExtractBlockKind,
    NestedContent,
    UniversalPage,
)


def nested_anchor(*, page_index: int, nest_index: int) -> str:
    if page_index < 0 or nest_index < 1:
        raise ValueError("page_index must be >= 0 and nest_index must be >= 1")
    return f"p{page_index}_n{nest_index}"


def nested_original_name(*, parent_name: str, anchor: str) -> str:
    parent = parent_name.strip()
    if not parent:
        raise ValueError("parent_name is required")
    return f"{parent}#{anchor}"


def nested_markdown_ref(item: NestedContent, *, omitted: bool = False) -> str:
    if omitted:
        return f"![{item.anchor}]({NESTED_OMITTED_STUB})"
    if item.content_type.startswith("image/"):
        return f"![{item.anchor}]"
    return f"[{item.anchor}](nested:{item.original_name})"


def _block_to_markdown(block: ExtractBlock) -> str:
    text = block.text.strip()
    if not text:
        return ""
    if block.kind is ExtractBlockKind.HEADING:
        level = block.level if block.level is not None else 1
        hashes = "#" * min(max(level, 1), 6)
        return f"{hashes} {text}"
    if block.kind is ExtractBlockKind.CODE:
        return f"```\n{text}\n```"
    if block.kind is ExtractBlockKind.FIGURE:
        return ""
    return text


def page_to_markdown(
    page: UniversalPage,
    *,
    nested: list[NestedContent],
    recursive_texts: dict[str, str] | None = None,
    omitted_anchors: set[str] | None = None,
) -> str:
    """Markdown страницы: блоки + якоря nested (+ optional recursive OCR под якорем)."""
    parts: list[str] = []
    for block in page.blocks:
        if block.kind is ExtractBlockKind.FIGURE:
            continue
        rendered = _block_to_markdown(block)
        if rendered:
            parts.append(rendered)

    body = "\n\n".join(parts).strip()
    if not body and page.text.strip():
        body = page.text.strip()

    nested_parts: list[str] = []
    ocr_by_anchor = recursive_texts if recursive_texts is not None else {}
    omitted: set[str] = omitted_anchors if omitted_anchors is not None else set()
    for item in nested:
        if item.page_index != page.index:
            continue
        nested_parts.append(nested_markdown_ref(item, omitted=item.anchor in omitted))
        ocr = ocr_by_anchor.get(item.anchor)
        if ocr is not None and ocr.strip():
            nested_parts.append(f"[nested {item.anchor}]\n{ocr.strip()}")

    chunks: list[str] = []
    if body:
        chunks.append(body)
    if nested_parts:
        chunks.append("\n\n".join(nested_parts))
    return "\n\n".join(chunks)


def strip_nested_bytes(items: list[NestedContent]) -> list[NestedContent]:
    return [item.model_copy(update={"bytes_b64": None}) for item in items]


def markdown_with_data_uris(markdown: str, nested: list[NestedContent]) -> str:
    """Optional export: `![anchor]` → `![anchor](data:<type>;base64,…)` для FileWriter."""
    result = markdown
    for item in nested:
        if item.bytes_b64 is None or not item.bytes_b64.strip():
            continue
        if not item.content_type.startswith("image/"):
            continue
        bare = f"![{item.anchor}]"
        with_uri = f"![{item.anchor}](data:{item.content_type};base64,{item.bytes_b64})"
        if bare in result:
            result = result.replace(bare, with_uri)
    return result


__all__ = [
    "markdown_with_data_uris",
    "nested_anchor",
    "nested_markdown_ref",
    "nested_original_name",
    "page_to_markdown",
    "strip_nested_bytes",
]
