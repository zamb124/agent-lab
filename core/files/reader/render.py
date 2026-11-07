"""Render-шаг: FileExtract + ReadFileArgs -> FileResult (markdown, budget, summarization)."""

from __future__ import annotations

from dataclasses import dataclass

from core.files.reader.markdown import page_to_markdown, strip_nested_bytes
from core.files.reader.models import (
    MAX_READ_BUDGET,
    TRUNCATION_MARKER,
    ContentMode,
    Continuation,
    FileExtract,
    FileResult,
    NestedContent,
    NestedMode,
    PageResult,
    ReadFileArgs,
    StopReason,
)
from core.files.reader.summarizers import summarize_pages


@dataclass(frozen=True)
class _Candidate:
    page: int
    label: str
    content_mode: ContentMode
    text: str


def _resolve_window(pages_total: int, page_start: int, page_end: int) -> tuple[int, int]:
    """Возвращает (start, end_inclusive) в границах [0, pages_total-1]; end=-1 = до EOF."""
    start = page_start
    if page_end == -1:
        end = pages_total - 1
    else:
        end = min(page_end, pages_total - 1)
    return start, end


def _apply_budget(candidates: list[_Candidate], budget: int) -> tuple[list[PageResult], bool]:
    """Наполняет budget с усечением последнего фрагмента маркером. Возвращает (results, budget_hit)."""
    results: list[PageResult] = []
    used = 0
    budget_hit = False
    for candidate in candidates:
        remaining = budget - used
        text = candidate.text
        if len(text) <= remaining:
            results.append(
                PageResult(
                    page=candidate.page,
                    label=candidate.label,
                    content_mode=candidate.content_mode,
                    span_chars=len(text),
                    truncated=False,
                    result=text,
                )
            )
            used += len(text)
            continue
        if remaining > len(TRUNCATION_MARKER):
            keep = remaining - len(TRUNCATION_MARKER)
            truncated_text = text[:keep] + TRUNCATION_MARKER
            results.append(
                PageResult(
                    page=candidate.page,
                    label=candidate.label,
                    content_mode=candidate.content_mode,
                    span_chars=len(truncated_text),
                    truncated=True,
                    result=truncated_text,
                )
            )
        budget_hit = True
        break
    return results, budget_hit


async def render_file_result(
    extract: FileExtract,
    args: ReadFileArgs,
    *,
    tool_name: str,
    budget: int,
    nested: list[NestedContent] | None = None,
    recursive_texts: dict[str, str] | None = None,
    omitted_anchors: set[str] | None = None,
) -> FileResult:
    pages = extract.pages
    pages_total = extract.page_layout.pages_total
    warnings = list(extract.warnings)
    file_id = extract.file_id
    nested_items = nested if nested is not None else []
    ocr_map = recursive_texts if recursive_texts is not None else {}
    omitted: set[str] = omitted_anchors if omitted_anchors is not None else set()
    # parts: bytes живут до tool envelope (Part.raw); refs — только метаданные.
    if args.nested_mode is NestedMode.PARTS:
        nested_for_result = list(nested_items)
    else:
        nested_for_result = strip_nested_bytes(nested_items)

    base = FileResult(
        file_name=extract.file_name,
        file_id=file_id,
        success=True,
        error="",
        warnings=warnings,
        kind=extract.kind,
        mime_type=extract.mime_type,
        read_lane=extract.read_lane,
        page_layout=extract.page_layout,
        pages_total=extract.page_layout.pages_total,
        content_chars_total=extract.content_chars_total,
        page_start=args.page_start,
        pages_processed=0,
        complete=False,
        truncated=False,
        stop_reason=StopReason.COMPLETE,
        page_summarizations_used=False,
        results=[],
        continuation=Continuation(file_id=file_id, next_page_start=0, has_more=False, next_actions=[]),
        nested_mode=args.nested_mode,
        recursive=args.recursive,
        nested=nested_for_result,
    )

    if pages_total > 0 and args.page_start >= pages_total:
        warnings.append(
            f"page_start={args.page_start} за пределами pages_total={pages_total}"
        )
        return base.model_copy(
            update={"warnings": warnings, "stop_reason": StopReason.OUT_OF_RANGE, "complete": False}
        )

    start, end = _resolve_window(pages_total, args.page_start, args.page_end)
    if end < start:
        return base.model_copy(
            update={"stop_reason": StopReason.PAGE_END_REACHED, "complete": False}
        )

    selected = [p for p in pages if start <= p.index <= end]

    summarizations_used = False
    if args.page_summarizations:
        summarizations_used = True
        summary_results = await summarize_pages(
            selected,
            kind=extract.kind,
            file_name=extract.file_name,
            prompt=args.summarization_prompt,
            model=args.summarization_model,
            compression=args.compression,
        )
        candidates = [
            _Candidate(
                page=item.page,
                label=item.label,
                content_mode=ContentMode.SUMMARY,
                text=item.result,
            )
            for item in summary_results
        ]
    else:
        candidates = [
            _Candidate(
                page=p.index,
                label=p.label,
                content_mode=p.content_mode,
                text=page_to_markdown(
                    p,
                    nested=nested_items,
                    recursive_texts=ocr_map,
                    omitted_anchors=omitted,
                ),
            )
            for p in selected
        ]

    results, budget_hit = _apply_budget(candidates, budget)
    truncated_any = any(r.truncated for r in results)
    pages_processed = len(results)

    reached_eof = end >= pages_total - 1
    consumed_all_selected = pages_processed == len(selected) and not budget_hit

    if budget_hit or truncated_any:
        stop_reason = StopReason.BUDGET_EXHAUSTED
    elif consumed_all_selected and reached_eof:
        stop_reason = StopReason.COMPLETE
    else:
        stop_reason = StopReason.PAGE_END_REACHED

    complete = stop_reason == StopReason.COMPLETE

    if pages_processed > 0:
        next_page_start = results[-1].page + 1
    else:
        next_page_start = args.page_start
    if next_page_start > pages_total:
        next_page_start = pages_total

    has_more = not complete and (next_page_start < pages_total or budget_hit)
    if pages_processed == 0 and budget_hit:
        has_more = True

    next_actions = _build_next_actions(
        tool_name=tool_name,
        file_name=extract.file_name,
        has_more=has_more,
        next_page_start=next_page_start,
        page_summarizations=args.page_summarizations,
        budget_stalled=(pages_processed == 0 and budget_hit),
        budget=budget,
    )

    return base.model_copy(
        update={
            "warnings": warnings,
            "pages_processed": pages_processed,
            "complete": complete,
            "truncated": truncated_any or budget_hit,
            "stop_reason": stop_reason,
            "page_summarizations_used": summarizations_used,
            "results": results,
            "continuation": Continuation(
                file_id=file_id,
                next_page_start=next_page_start if has_more else 0,
                has_more=has_more,
                next_actions=next_actions,
            ),
            "nested": nested_for_result,
        }
    )


def _build_next_actions(
    *,
    tool_name: str,
    file_name: str,
    has_more: bool,
    next_page_start: int,
    page_summarizations: bool,
    budget_stalled: bool,
    budget: int,
) -> list[str]:
    if not has_more:
        return []
    quoted = f'names=["{file_name}"]'
    actions: list[str] = []
    if budget_stalled:
        bigger = min(budget * 2, MAX_READ_BUDGET)
        actions.append(f"{tool_name}({quoted}, budget={bigger})")
    actions.append(f"{tool_name}({quoted}, page_start={next_page_start})")
    if not page_summarizations:
        actions.append(f"{tool_name}({quoted}, page_summarizations=true)")
    return actions
