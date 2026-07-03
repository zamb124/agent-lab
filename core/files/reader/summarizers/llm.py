"""Default LLM-суммаризатор с батч-паковкой страниц в контекстное окно модели."""

from __future__ import annotations

from collections.abc import Sequence

from core.ai.providers import AICapability, split_provider_prefixed_model
from core.ai.requirements import AISelection
from core.ai.resolver import resolve_ai_model
from core.files.reader.models import UniversalPage
from core.logging import get_logger
from core.text_transforms.service import TextTransformService

logger = get_logger(__name__)

_DEFAULT_SUMMARY_CONTEXT_TOKENS: int = 32_000
_CHARS_PER_TOKEN: int = 3
_BATCH_SAFETY_FRACTION: float = 0.5
_MIN_BATCH_CHARS: int = 4_000
_PAGE_MARKER_PREFIX: str = "===PAGE "
_SEGMENT_INSTRUCTION: str = (
    "You summarize document pages. The input contains several pages, each starting with a "
    "marker line of the form ===PAGE n===. For every page return exactly one marker line "
    "===PAGE n=== followed by a concise summary of that page in its original language. "
    "Do not merge pages. Output only the marker lines and summaries."
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


def _pack_batches(
    pages: Sequence[UniversalPage], *, batch_chars: int
) -> list[list[UniversalPage]]:
    batches: list[list[UniversalPage]] = []
    current: list[UniversalPage] = []
    current_len = 0
    for page in pages:
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


async def summarize_llm_pages(
    pages: Sequence[UniversalPage], *, prompt: str, model: str
) -> list[str]:
    if not pages:
        return []
    batch_chars = _resolve_context_chars(model)
    service = TextTransformService()
    instruction = _SEGMENT_INSTRUCTION
    if prompt.strip():
        instruction = f"{_SEGMENT_INSTRUCTION}\nAdditional focus: {prompt.strip()}"

    results: dict[int, str] = {}
    for batch in _pack_batches(pages, batch_chars=batch_chars):
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
