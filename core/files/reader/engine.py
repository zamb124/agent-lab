"""Оркестратор read_file: resolve FileRef -> extract-cache -> render -> единый envelope.

Разделение: extract (дорого, кэшируется в Redis) vs render (дёшево, per-call срез страниц).
Первый read полностью извлекает файл в Universal Pages и кладёт в Redis; повторные read
— дешёвый render из кэша. Cache miss = перечитать из S3 и переположить, не падать.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence

from core.files.file_ref import FileRef, file_id_from_download_url
from core.files.reader.exceptions import FileReadError
from core.files.reader.extract_cache import (
    load_file_extract,
    load_vision_page,
    store_file_extract,
    store_vision_page,
)
from core.files.reader.models import (
    VISION_FULL_READ_MAX_PAGES,
    ContentMode,
    Continuation,
    FileExtract,
    FileReadKind,
    FileResult,
    PageLayout,
    PageLayoutKind,
    ReadFileArgs,
    ReadFileEnvelope,
    ReadLane,
    StopReason,
    UniversalPage,
)
from core.files.reader.render import render_file_result
from core.files.reader.service import FileReader, run_vision_on_image_bytes
from core.files.reader.universal import build_file_extract
from core.logging import get_logger

logger = get_logger(__name__)


def _file_id_of(file_ref: FileRef) -> str | None:
    if file_ref.file_id is not None and file_ref.file_id.strip():
        return file_ref.file_id.strip()
    if file_ref.url is not None:
        parsed = file_id_from_download_url(file_ref.url)
        if parsed:
            return parsed
    return None


def _display_name(file_ref: FileRef) -> str:
    return file_ref.original_name


async def _extract_text_lane(
    file_ref: FileRef,
    args: ReadFileArgs,
    *,
    file_id: str | None,
    transcription_company_id: str | None,
) -> FileExtract:
    reader = FileReader()
    result = await reader.read(
        file_ref,
        vision_prompt=args.vision_prompt or None,
        transcription_company_id=transcription_company_id,
    )
    extract = build_file_extract(
        result, file_name=_display_name(file_ref), file_id=file_id
    )
    await store_file_extract(extract)
    return extract


async def _extract_pdf_visual(
    file_ref: FileRef,
    args: ReadFileArgs,
    *,
    file_id: str | None,
    lane: ReadLane,
) -> FileExtract:
    reader = FileReader()
    result = await reader.read(
        file_ref,
        include_asset_bytes=True,
    )
    file_name = _display_name(file_ref)
    pages_total = len(result.pages)
    checksum = result.source_checksum
    content_mode = ContentMode.HYBRID if lane == ReadLane.HYBRID else ContentMode.VISION
    vision_prompt = args.vision_prompt or None
    prompt = vision_prompt or "Опиши содержимое страницы и извлеки весь видимый текст."

    lazy = pages_total > VISION_FULL_READ_MAX_PAGES
    if lazy:
        start = args.page_start
        end = pages_total - 1 if args.page_end == -1 else min(args.page_end, pages_total - 1)
        target_indices = set(range(start, end + 1))
    else:
        target_indices = set(range(pages_total))

    universal: list[UniversalPage] = []
    warnings = list(result.warnings)
    for page in result.pages:
        if page.index not in target_indices:
            continue
        cached = await load_vision_page(file_id=file_id, checksum=checksum, page=page.index)
        if cached is not None:
            vision_text = cached
        else:
            raster_b64 = page.assets[0].bytes_b64 if page.assets else None
            if raster_b64 is None:
                vision_text = ""
            else:
                vision_text = await run_vision_on_image_bytes(
                    base64.b64decode(raster_b64),
                    file_name=f"{file_name}#p{page.index + 1}",
                    mime="image/png",
                    prompt=prompt,
                    vision_model=None,
                    compression=args.compression,
                    trace_name="core.files.reader.pdf_vision",
                )
                await store_vision_page(
                    file_id=file_id, checksum=checksum, page=page.index, text=vision_text
                )
        if lane == ReadLane.HYBRID and page.text.strip():
            merged = f"{page.text}\n\n[vision]\n{vision_text}"
        else:
            merged = vision_text
        universal.append(
            UniversalPage(
                index=page.index, label=page.label or f"page_{page.index + 1}",
                text=merged, content_mode=content_mode,
            )
        )

    if lazy:
        warnings.append(
            f"vision применён только к запрошенным страницам (pages_total={pages_total} "
            + f"> порога {VISION_FULL_READ_MAX_PAGES})"
        )
        content_chars_total = -1
    else:
        content_chars_total = sum(len(p.text) for p in universal)

    extract = FileExtract(
        file_id=file_id,
        file_name=file_name,
        kind=FileReadKind.PDF,
        mime_type=result.content_type or "application/pdf",
        read_lane=lane,
        page_layout=PageLayout(kind=PageLayoutKind.NATIVE, pages_total=pages_total, page_size=0),
        pages=universal,
        content_chars_total=content_chars_total,
        warnings=warnings,
        source_checksum=checksum,
    )
    if not lazy:
        await store_file_extract(extract)
    return extract


async def _get_or_extract(
    file_ref: FileRef,
    args: ReadFileArgs,
    *,
    forced_lane: ReadLane | None,
    transcription_company_id: str | None,
) -> FileExtract:
    file_id = _file_id_of(file_ref)

    if forced_lane == ReadLane.TEXT:
        reader = FileReader()
        info = reader.recognize_file_type(file_name=_display_name(file_ref))
        if info.detected_kind in (FileReadKind.IMAGE, FileReadKind.AUDIO, FileReadKind.VIDEO):
            raise FileReadError(
                f"text lane не применим к типу {info.detected_kind.value}; "
                + "используйте универсальный read_file или vision/stt tool"
            )

    if forced_lane is ReadLane.VISION or forced_lane is ReadLane.HYBRID:
        reader = FileReader()
        info = reader.recognize_file_type(file_name=_display_name(file_ref))
        if info.detected_kind == FileReadKind.PDF:
            return await _extract_pdf_visual(
                file_ref, args, file_id=file_id, lane=forced_lane
            )
        if info.detected_kind == FileReadKind.IMAGE:
            pass  # обычный vision-путь ниже
        elif forced_lane is ReadLane.HYBRID:
            extract = await _extract_text_lane(
                file_ref,
                args,
                file_id=file_id,
                transcription_company_id=transcription_company_id,
            )
            hybrid_warning = (
                f"hybrid недоступен для типа {info.detected_kind.value}: "
                + "встроенные изображения не распознаются, прочитан только текст"
            )
            return extract.model_copy(
                update={"warnings": [*extract.warnings, hybrid_warning]}
            )
        else:
            raise FileReadError(
                "lane=vision поддержан только для PDF и изображений, "
                + f"а тип — {info.detected_kind.value}"
            )

    cached = await load_file_extract(file_id=file_id, checksum=None)
    if cached is not None:
        return cached

    return await _extract_text_lane(
        file_ref, args, file_id=file_id, transcription_company_id=transcription_company_id
    )


def _error_file_result(file_ref: FileRef, message: str) -> FileResult:
    file_id = _file_id_of(file_ref)
    return FileResult(
        file_name=_display_name(file_ref),
        file_id=file_id,
        success=False,
        error=message,
        warnings=[],
        kind=FileReadKind.UNKNOWN,
        mime_type="application/octet-stream",
        read_lane=ReadLane.TEXT,
        page_layout=PageLayout(kind=PageLayoutKind.NATIVE, pages_total=0, page_size=0),
        pages_total=0,
        content_chars_total=-1,
        page_start=0,
        pages_processed=0,
        complete=False,
        truncated=False,
        stop_reason=StopReason.ERROR,
        page_summarizations_used=False,
        results=[],
        continuation=Continuation(file_id=file_id, next_page_start=0, has_more=False, next_actions=[]),
    )


async def read_files_to_envelope(
    file_refs: Sequence[FileRef],
    args: ReadFileArgs,
    *,
    tool_name: str,
    forced_lane: ReadLane | None = None,
    transcription_company_id: str | None = None,
) -> ReadFileEnvelope:
    total_files = len(file_refs)
    per_file_budget = max(args.budget // total_files, 1)
    carryover = 0

    files: list[FileResult] = []
    for file_ref in file_refs:
        file_budget = per_file_budget + carryover
        try:
            extract = await _get_or_extract(
                file_ref,
                args,
                forced_lane=forced_lane,
                transcription_company_id=transcription_company_id,
            )
            file_result = await render_file_result(
                extract, args, tool_name=tool_name, budget=file_budget
            )
        except (FileReadError, ValueError) as exc:
            files.append(_error_file_result(file_ref, str(exc)))
            continue
        used = sum(r.span_chars for r in file_result.results)
        carryover = max(file_budget - used, 0)
        files.append(file_result)

    result_chars_returned = sum(
        r.span_chars for file_result in files for r in file_result.results
    )

    return ReadFileEnvelope(
        success=True,
        tool=tool_name,
        files_processed=len(files),
        names=list(args.names),
        budget=args.budget,
        result_chars_returned=result_chars_returned,
        files=files,
        warnings=[],
    )
