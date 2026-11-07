"""Default LLM-суммаризатор с батч-паковкой страниц в контекстное окно модели.

При nested image на странице (bytes_b64) суммаризация multimodal: текст страницы
+ interleaved Image {anchor}: / Part(raw). Маршрут — llm_vision; без картинок —
llm_summarize. При ``schema`` — по одной странице через forced tool
``submit_page_summary``; result — JSON arguments.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence

from a2a.types import Part

from core.ai.providers import AICapability, split_provider_prefixed_model
from core.ai.requirements import AISelection
from core.ai.resolver import resolve_ai_model
from core.files.reader.models import CompressionMode, NestedContent, UniversalPage
from core.files.reader.nested import nested_bytes
from core.files.reader.parts import nested_image_label, nested_to_raw_part
from core.files.reader.service import FileReader
from core.files.reader.vision import prepare_visual_payload
from core.types import JsonObject

_DEFAULT_SUMMARY_CONTEXT_TOKENS: int = 32_000
_CHARS_PER_TOKEN: int = 3
_BATCH_SAFETY_FRACTION: float = 0.5
_MIN_BATCH_CHARS: int = 4_000
_PAGE_MARKER_PREFIX: str = "===PAGE "
_SEGMENT_INSTRUCTION: str = (
    "You summarize document pages. The input contains several pages, each starting with a "
    "marker line of the form ===PAGE n===. Images that belong to a page follow that page's "
    "text as Image {anchor}: labels and image parts. For every page return exactly one marker "
    "line ===PAGE n=== followed by a concise summary of that page in its original language, "
    "using both the text and the images. Do not merge pages. Output only the marker lines "
    "and summaries."
)


def _resolve_context_chars(model_override: str) -> int:
    provider, model = split_provider_prefixed_model(None, model_override or None)
    selection = AISelection(provider=provider, model=model) if (provider or model) else None
    resolved = resolve_ai_model(
        AICapability.LLM_SUMMARIZE, selection=selection, include_platform_default=True
    )
    context_tokens = _DEFAULT_SUMMARY_CONTEXT_TOKENS
    if resolved is not None and resolved.model_record is not None:
        record_ctx = resolved.model_record.context_length
        if record_ctx is not None and record_ctx > 0:
            context_tokens = record_ctx
    budget_chars = int(context_tokens * _CHARS_PER_TOKEN * _BATCH_SAFETY_FRACTION)
    return max(budget_chars, _MIN_BATCH_CHARS)


def _page_image_items(page: UniversalPage) -> list[NestedContent]:
    items: list[NestedContent] = []
    for item in page.nested:
        if not item.content_type.startswith("image/"):
            continue
        if item.bytes_b64 is None or not item.bytes_b64.strip():
            continue
        items.append(item)
    return items


def _pack_batches(
    pages: Sequence[UniversalPage], *, batch_chars: int
) -> list[list[UniversalPage]]:
    """Текст пакуется по символам; страница с nested images — отдельный батч."""
    batches: list[list[UniversalPage]] = []
    current: list[UniversalPage] = []
    current_len = 0
    for page in pages:
        if _page_image_items(page):
            if current:
                batches.append(current)
                current = []
                current_len = 0
            batches.append([page])
            continue
        page_len = len(page.text) + len(_PAGE_MARKER_PREFIX) + 8
        if current and current_len + page_len > batch_chars:
            batches.append(current)
            current = []
            current_len = 0
        current.append(page)
        current_len += page_len
    if current:
        batches.append(current)
    return batches


def _parse_segments(response: str, indices: list[int]) -> dict[int, str]:
    segments: dict[int, str] = {}
    current_index: int | None = None
    buffer: list[str] = []
    for line in response.splitlines():
        stripped = line.strip()
        if stripped.startswith(_PAGE_MARKER_PREFIX):
            if current_index is not None:
                segments[current_index] = "\n".join(buffer).strip()
            digits = stripped[len(_PAGE_MARKER_PREFIX) :].rstrip("=").strip()
            current_index = int(digits) if digits.isdigit() else None
            buffer = []
        elif current_index is not None:
            buffer.append(line)
    if current_index is not None:
        segments[current_index] = "\n".join(buffer).strip()
    return {idx: segments[idx] for idx in indices if idx in segments}


def _fallback_split(response: str, count: int) -> list[str]:
    text = response.strip()
    if count <= 1:
        return [text]
    step = max(len(text) // count, 1)
    return [text[i * step : (i + 1) * step] if i < count - 1 else text[i * step :] for i in range(count)]


def _prepared_image_part(
    item: NestedContent, *, compression: CompressionMode
) -> Part:
    raw = nested_bytes(item)
    payload, payload_mime = prepare_visual_payload(
        raw,
        file_name=item.original_name,
        mime=item.content_type,
        compression=compression,
    )
    prepared = item.model_copy(
        update={
            "bytes_b64": base64.b64encode(payload).decode("utf-8"),
            "content_type": payload_mime,
        }
    )
    return nested_to_raw_part(prepared)


def _batch_media_parts(
    batch: Sequence[UniversalPage], *, compression: CompressionMode
) -> list[Part]:
    """Interleaved text markers + Image {anchor}: + raw для страниц батча."""
    parts: list[Part] = []
    for page in batch:
        page_text = f"{_PAGE_MARKER_PREFIX}{page.index}===\n{page.text}"
        parts.append(Part(text=page_text))
        for item in _page_image_items(page):
            parts.append(Part(text=nested_image_label(item.anchor)))
            parts.append(_prepared_image_part(item, compression=compression))
    return parts


async def summarize_llm_pages(
    pages: Sequence[UniversalPage],
    *,
    prompt: str,
    model: str,
    compression: CompressionMode = CompressionMode.NEVER,
    schema: JsonObject | None = None,
) -> list[str]:
    if not pages:
        return []
    if schema is not None:
        return await _summarize_structured_pages(
            pages,
            prompt=prompt,
            model=model,
            compression=compression,
            schema=schema,
        )
    batch_chars = _resolve_context_chars(model)
    service = FileReader.require_text_transform()
    instruction = _SEGMENT_INSTRUCTION
    if prompt.strip():
        instruction = f"{_SEGMENT_INSTRUCTION}\nAdditional focus: {prompt.strip()}"

    results: dict[int, str] = {}
    for batch in _pack_batches(pages, batch_chars=batch_chars):
        has_images = any(_page_image_items(page) for page in batch)
        if has_images:
            media_parts = _batch_media_parts(batch, compression=compression)
            # Первый Part — marker+text первой страницы; instruction передаём отдельно.
            response = await service.summarize(
                "",
                instruction=instruction,
                model=model or None,
                media_parts=media_parts,
            )
        else:
            marked_parts = [f"{_PAGE_MARKER_PREFIX}{page.index}===\n{page.text}" for page in batch]
            marked = "\n\n".join(marked_parts)
            response = await service.summarize(
                marked,
                instruction=instruction,
                model=model or None,
            )
        indices = [page.index for page in batch]
        parsed = _parse_segments(response, indices)
        if len(parsed) == len(batch):
            results.update(parsed)
        else:
            fallback = _fallback_split(response, len(batch))
            for page, chunk in zip(batch, fallback, strict=True):
                results[page.index] = chunk

    return [results.get(page.index, "") for page in pages]


async def _summarize_structured_pages(
    pages: Sequence[UniversalPage],
    *,
    prompt: str,
    model: str,
    compression: CompressionMode,
    schema: JsonObject,
) -> list[str]:
    """Одна страница — один forced tool call; result — JSON arguments."""
    service = FileReader.require_text_transform()
    focus = prompt.strip()
    out: list[str] = []
    for page in pages:
        page_text = f"{_PAGE_MARKER_PREFIX}{page.index}===\n{page.text}"
        images = _page_image_items(page)
        if images:
            media_parts: list[Part] = [Part(text=page_text)]
            for item in images:
                media_parts.append(Part(text=nested_image_label(item.anchor)))
                media_parts.append(_prepared_image_part(item, compression=compression))
            payload = await service.summarize_structured(
                "",
                schema=schema,
                instruction=focus or None,
                model=model or None,
                media_parts=media_parts,
            )
        else:
            payload = await service.summarize_structured(
                page_text,
                schema=schema,
                instruction=focus or None,
                model=model or None,
            )
        out.append(json.dumps(payload, ensure_ascii=False))
    return out
