"""Оркестратор read_file: resolve FileRef -> extract-cache -> render -> единый envelope.

Разделение: extract (дорого, кэшируется в Redis) vs render (дёшево, per-call срез страниц).
Первый read полностью извлекает файл в Universal Pages и кладёт в Redis; повторные read
— дешёвый render из кэша. Cache miss = перечитать из S3 и переположить, не падать.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from pathlib import Path

from core.files.checksum import compute_content_checksum_sha256
from core.files.file_ref import FileRef, FileRefSource, file_id_from_download_url
from core.files.reader.exceptions import FileReadError
from core.files.reader.extract_cache import (
    load_file_extract,
    load_vision_image,
    load_vision_page,
    store_file_extract,
    store_vision_image,
    store_vision_page,
)
from core.files.reader.models import (
    VISION_FULL_READ_MAX_PAGES,
    CompressionMode,
    ContentMode,
    Continuation,
    FileExtract,
    FileReadKind,
    FileResult,
    PageLayout,
    PageLayoutKind,
    ReadAssetKind,
    ReadFileArgs,
    ReadFileEnvelope,
    ReadLane,
    ReadOptions,
    ReadPage,
    StopReason,
    UniversalPage,
    merge_file_ref_read_options,
)
from core.files.reader.render import render_file_result
from core.files.reader.service import (
    FileReader,
    SourceInput,
    guess_mime,
    is_file_ref_source,
    pdf_page_text_for_merge,
    pdf_page_text_usable,
    run_vision_on_image_bytes,
)
from core.files.reader.universal import build_file_extract
from core.files.types import ext_to_mime
from core.logging import get_logger

logger = get_logger(__name__)


def _file_ref_identity_for_source(
    source: SourceInput,
    *,
    raw: bytes,
    resolved_file_id: str | None,
) -> tuple[str | None, str | None]:
    if isinstance(resolved_file_id, str) and resolved_file_id.strip():
        return resolved_file_id.strip(), None

    if isinstance(source, Path):
        return None, source.resolve().as_uri()

    if isinstance(source, str):
        stripped = source.strip()
        if stripped.startswith(("http://", "https://")):
            return None, stripped
        parsed_file_id = file_id_from_download_url(stripped)
        if parsed_file_id is not None:
            return parsed_file_id, None
        path = Path(stripped)
        if path.is_file():
            return None, path.resolve().as_uri()

    checksum = compute_content_checksum_sha256(raw)
    return None, f"inline://sha256/{checksum}"


def read_options_from_args(
    args: ReadFileArgs,
    *,
    source_file_id: str | None = None,
    include_asset_bytes: bool = False,
) -> ReadOptions:
    vision_prompt = args.vision_prompt.strip() if args.vision_prompt.strip() else None
    return ReadOptions(
        include_asset_bytes=include_asset_bytes,
        source_file_id=source_file_id,
        vision_model=args.vision_model,
        vision_prompt=vision_prompt,
        transcription_company_id=args.transcription_company_id,
    )


async def file_ref_from_source(
    reader: FileReader,
    source: SourceInput | FileRef,
    *,
    file_name: str | None = None,
    file_id: str | None = None,
) -> tuple[FileRef, bytes, str]:
    normalized_file_id = file_id.strip() if isinstance(file_id, str) and file_id.strip() else None
    if isinstance(source, FileRef):
        file_ref = source
        if normalized_file_id is not None and file_ref.file_id is None:
            file_ref = file_ref.model_copy(update={"file_id": normalized_file_id})
        opts = ReadOptions(source_file_id=normalized_file_id or file_ref.file_id)
        opts = merge_file_ref_read_options(file_ref, opts)
        raw, resolved_name = await reader.raw_from_file_ref(file_ref, opts)
        display_name = (
            file_name.strip() if isinstance(file_name, str) and file_name.strip() else None
        ) or resolved_name
        return file_ref.model_copy(update={"original_name": display_name}), raw, display_name

    opts = ReadOptions(source_file_id=normalized_file_id)
    raw, resolved_name = await reader.resolve_source(source, file_name, opts)
    display_name = resolved_name
    resolved_id = normalized_file_id or opts.source_file_id
    file_type = reader.recognize_file_type(file_name=display_name, head=raw[:8192])
    content_type = file_type.content_type or guess_mime(display_name)
    if content_type is None or not content_type.strip():
        content_type = ext_to_mime(Path(display_name).suffix.lower())
    ref_file_id, ref_url = _file_ref_identity_for_source(
        source,
        raw=raw,
        resolved_file_id=resolved_id,
    )
    file_ref = FileRef(
        original_name=display_name,
        file_id=ref_file_id,
        url=ref_url,
        file_size=len(raw),
        content_type=content_type,
    )
    return file_ref, raw, display_name


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


def cached_pdf_extract_is_stale(extract: FileExtract) -> bool:
    """Старый TEXT-кэш до hybrid-OCR: пустые страницы PDF без vision."""
    if extract.kind != FileReadKind.PDF:
        return False
    if extract.read_lane != ReadLane.TEXT:
        return False
    if not extract.pages:
        return True
    total_text = sum(len(page.text.strip()) for page in extract.pages)
    return total_text == 0


def _pdf_lazy_target_indices(pages_total: int, args: ReadFileArgs) -> tuple[set[int], bool]:
    lazy = pages_total > VISION_FULL_READ_MAX_PAGES
    if lazy:
        start = args.page_start
        end = pages_total - 1 if args.page_end == -1 else min(args.page_end, pages_total - 1)
        return set(range(start, end + 1)), True
    return set(range(pages_total)), False


def _merge_pdf_page_hybrid_text(
    *,
    base_text: str,
    image_ocr_blocks: list[str],
    raster_ocr_text: str,
) -> str:
    parts: list[str] = []
    if base_text:
        parts.append(base_text)
    parts.extend(image_ocr_blocks)
    if raster_ocr_text:
        parts.append(raster_ocr_text)
    return "\n\n".join(parts)


async def _vision_ocr_pdf_asset(
    asset_bytes_b64: str,
    *,
    file_name: str,
    mime: str,
    prompt: str,
    vision_model: str | None,
    compression: CompressionMode,
    file_id: str | None,
    checksum: str | None,
    page_index: int,
    image_checksum: str | None,
) -> str:
    if image_checksum is not None:
        cached = await load_vision_image(
            file_id=file_id,
            checksum=checksum,
            page=page_index,
            image_checksum=image_checksum,
        )
        if cached is not None:
            return cached
    else:
        cached = await load_vision_page(file_id=file_id, checksum=checksum, page=page_index)
        if cached is not None:
            return cached

    vision_text = await run_vision_on_image_bytes(
        base64.b64decode(asset_bytes_b64),
        file_name=file_name,
        mime=mime,
        prompt=prompt,
        vision_model=vision_model,
        compression=compression,
        trace_name="core.files.reader.pdf_vision",
    )
    if image_checksum is not None:
        await store_vision_image(
            file_id=file_id,
            checksum=checksum,
            page=page_index,
            image_checksum=image_checksum,
            text=vision_text,
        )
    else:
        await store_vision_page(
            file_id=file_id,
            checksum=checksum,
            page=page_index,
            text=vision_text,
        )
    return vision_text


async def _build_pdf_hybrid_page_text(
    page: ReadPage,
    *,
    file_name: str,
    prompt: str,
    vision_model: str | None,
    compression: CompressionMode,
    file_id: str | None,
    checksum: str | None,
) -> tuple[str, bool, ContentMode]:
    merge_text = pdf_page_text_for_merge(page.text)
    image_ocr_blocks: list[str] = []
    raster_ocr_text = ""
    vision_used = False

    embedded_assets = [
        asset
        for asset in page.assets
        if asset.kind == ReadAssetKind.EMBEDDED_IMAGE and asset.bytes_b64 is not None
    ]
    for image_index, asset in enumerate(embedded_assets, start=1):
        asset_bytes_b64 = asset.bytes_b64
        if asset_bytes_b64 is None:
            raise FileReadError(
                f"PDF embedded image без bytes_b64: {file_name}#p{page.index + 1}:img{image_index}"
            )
        ocr_text = await _vision_ocr_pdf_asset(
            asset_bytes_b64,
            file_name=f"{file_name}#p{page.index + 1}:img{image_index}",
            mime=asset.content_type or "image/png",
            prompt=prompt,
            vision_model=vision_model,
            compression=compression,
            file_id=file_id,
            checksum=checksum,
            page_index=page.index,
            image_checksum=asset.checksum,
        )
        vision_used = True
        image_ocr_blocks.append(f"[image {image_index}]\n{ocr_text}")

    if not embedded_assets:
        raster_asset = next(
            (asset for asset in page.assets if asset.kind == ReadAssetKind.PAGE_RASTER),
            None,
        )
        if raster_asset is not None and raster_asset.bytes_b64 is not None:
            if not pdf_page_text_usable(page.text):
                raster_ocr_text = await _vision_ocr_pdf_asset(
                    raster_asset.bytes_b64,
                    file_name=f"{file_name}#p{page.index + 1}",
                    mime=raster_asset.content_type or "image/png",
                    prompt=prompt,
                    vision_model=vision_model,
                    compression=compression,
                    file_id=file_id,
                    checksum=checksum,
                    page_index=page.index,
                    image_checksum=None,
                )
                vision_used = True

    merged = _merge_pdf_page_hybrid_text(
        base_text=merge_text,
        image_ocr_blocks=image_ocr_blocks,
        raster_ocr_text=raster_ocr_text,
    )
    content_mode = ContentMode.HYBRID if vision_used else ContentMode.FULL
    return merged, vision_used, content_mode


async def _extract_pdf_auto_hybrid(
    file_ref: FileRef,
    args: ReadFileArgs,
    *,
    file_id: str | None,
    resolved_raw: bytes,
    resolved_name: str,
) -> FileExtract:
    reader = FileReader()
    opts = read_options_from_args(
        args,
        source_file_id=file_id,
        include_asset_bytes=True,
    )
    result = await reader.read_raw_bytes(resolved_raw, resolved_name, opts)
    file_name = _display_name(file_ref)
    pages_total = len(result.pages)
    checksum = result.source_checksum
    vision_prompt = args.vision_prompt.strip() if args.vision_prompt.strip() else None
    prompt = vision_prompt or "Опиши содержимое страницы и извлеки весь видимый текст."

    target_indices, lazy = _pdf_lazy_target_indices(pages_total, args)
    universal: list[UniversalPage] = []
    warnings = list(result.warnings)
    any_vision_used = False

    for page in result.pages:
        if page.index not in target_indices:
            continue
        merged, vision_used, content_mode = await _build_pdf_hybrid_page_text(
            page,
            file_name=file_name,
            prompt=prompt,
            vision_model=args.vision_model,
            compression=args.compression,
            file_id=file_id,
            checksum=checksum,
        )
        if vision_used:
            any_vision_used = True
        universal.append(
            UniversalPage(
                index=page.index,
                label=page.label or f"page_{page.index + 1}",
                text=merged,
                content_mode=content_mode,
            )
        )

    if lazy:
        warnings.append(
            f"vision применён только к запрошенным страницам (pages_total={pages_total} "
            + f"> порога {VISION_FULL_READ_MAX_PAGES})"
        )
    content_chars_total = sum(len(page.text) for page in universal)

    read_lane = ReadLane.HYBRID if any_vision_used else ReadLane.TEXT
    extract = FileExtract(
        file_id=file_id,
        file_name=file_name,
        kind=FileReadKind.PDF,
        mime_type=result.content_type or "application/pdf",
        read_lane=read_lane,
        page_layout=PageLayout(kind=PageLayoutKind.NATIVE, pages_total=pages_total, page_size=0),
        pages=universal,
        content_chars_total=content_chars_total,
        warnings=warnings,
        source_checksum=checksum,
    )
    if not lazy:
        await store_file_extract(extract)
    return extract


async def _extract_text_lane(
    file_ref: FileRef,
    args: ReadFileArgs,
    *,
    file_id: str | None,
    resolved_raw: bytes,
    resolved_name: str,
) -> FileExtract:
    reader = FileReader()
    opts = read_options_from_args(args, source_file_id=file_id)
    result = await reader.read_raw_bytes(resolved_raw, resolved_name, opts)
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
    resolved_raw: bytes,
    resolved_name: str,
) -> FileExtract:
    reader = FileReader()
    opts = read_options_from_args(
        args,
        source_file_id=file_id,
        include_asset_bytes=True,
    )
    result = await reader.read_raw_bytes(resolved_raw, resolved_name, opts)
    file_name = _display_name(file_ref)
    pages_total = len(result.pages)
    checksum = result.source_checksum
    content_mode = ContentMode.HYBRID if lane == ReadLane.HYBRID else ContentMode.VISION
    vision_prompt = args.vision_prompt.strip() if args.vision_prompt.strip() else None
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
                    vision_model=args.vision_model,
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
    resolved_raw: bytes,
    resolved_name: str,
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
                file_ref,
                args,
                file_id=file_id,
                lane=forced_lane,
                resolved_raw=resolved_raw,
                resolved_name=resolved_name,
            )
        if info.detected_kind == FileReadKind.IMAGE:
            pass  # обычный vision-путь ниже
        elif forced_lane is ReadLane.HYBRID:
            extract = await _extract_text_lane(
                file_ref,
                args,
                file_id=file_id,
                resolved_raw=resolved_raw,
                resolved_name=resolved_name,
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
    if cached is not None and not cached_pdf_extract_is_stale(cached):
        return cached

    reader = FileReader()
    info = reader.recognize_file_type(file_name=_display_name(file_ref), head=resolved_raw[:8192])
    if info.detected_kind == FileReadKind.PDF:
        return await _extract_pdf_auto_hybrid(
            file_ref,
            args,
            file_id=file_id,
            resolved_raw=resolved_raw,
            resolved_name=resolved_name,
        )

    return await _extract_text_lane(
        file_ref,
        args,
        file_id=file_id,
        resolved_raw=resolved_raw,
        resolved_name=resolved_name,
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
) -> ReadFileEnvelope:
    total_files = len(file_refs)
    per_file_budget = max(args.budget // total_files, 1)
    carryover = 0

    reader = FileReader()
    files: list[FileResult] = []
    for file_ref in file_refs:
        file_budget = per_file_budget + carryover
        try:
            extract = await reader.read(file_ref, args)
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


async def read_file_extract(
    reader: FileReader,
    source: SourceInput | FileRefSource,
    args: ReadFileArgs,
    *,
    file_name: str | None = None,
    file_id: str | None = None,
) -> FileExtract:
    if isinstance(source, FileRef):
        source_input: SourceInput | FileRef = source
    elif is_file_ref_source(source):
        source_input = FileRef.model_validate(source)
    else:
        source_input = source
    file_ref, resolved_raw, resolved_name = await file_ref_from_source(
        reader,
        source_input,
        file_name=file_name,
        file_id=file_id,
    )
    return await _get_or_extract(
        file_ref,
        args,
        forced_lane=args.forced_lane,
        resolved_raw=resolved_raw,
        resolved_name=resolved_name,
    )


setattr(FileReader, "read", read_file_extract)
