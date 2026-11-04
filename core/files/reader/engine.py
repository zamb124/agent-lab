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
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.files.reader.asset_persist import persist_extract_asset
from core.files.reader.exceptions import FileReadError
from core.files.reader.extract_cache import (
    load_file_extract,
    load_vision_image,
    load_vision_page,
    store_file_extract,
    store_vision_image,
    store_vision_page,
)
from core.files.reader.markdown import strip_nested_bytes
from core.files.reader.models import (
    DEFAULT_VIRTUAL_PAGE_SIZE,
    VISION_FULL_READ_MAX_PAGES,
    CompressionMode,
    ContentMode,
    Continuation,
    ExtractBlock,
    ExtractBlockKind,
    FileExtract,
    FileReadKind,
    FileResult,
    NestedContent,
    NestedMode,
    PageLayout,
    PageLayoutKind,
    ReadAsset,
    ReadFileArgs,
    ReadFileEnvelope,
    ReadLane,
    ReadOptions,
    ReadPage,
    StopReason,
    UniversalPage,
    merge_file_ref_read_options,
    resolved_page_label,
)
from core.files.reader.nested import (
    compress_nested_image,
    nested_bytes,
    nested_from_page_assets,
    persist_nested_content,
)
from core.files.reader.render import render_file_result
from core.files.reader.service import (
    FileReader,
    SourceInput,
    guess_mime,
    is_file_ref_source,
    iter_pdf_read_pages,
    page_text_for_merge,
    page_text_usable,
    pdf_page_count,
    run_vision_on_image_bytes,
)
from core.files.reader.universal import (
    page_layout_kind_for_result,
    read_lane_for_kind,
    read_pages_for_layout,
)
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


def cached_extract_is_stale(extract: FileExtract) -> bool:
    """Пустой TEXT-кэш PDF до hybrid: страницы без текста и без vision."""
    if extract.kind != FileReadKind.PDF:
        return False
    if extract.read_lane != ReadLane.TEXT:
        return False
    if not extract.pages:
        return True
    total_text = sum(len(page.text.strip()) for page in extract.pages)
    return total_text == 0


def _lazy_native_indices(pages_total: int, args: ReadFileArgs) -> tuple[set[int], bool]:
    """Окно native-страниц. lazy=True только если извлечено не всё (нельзя класть в полный кэш)."""
    all_indices = set(range(pages_total))
    if pages_total <= VISION_FULL_READ_MAX_PAGES:
        return all_indices, False
    start = args.page_start
    end = pages_total - 1 if args.page_end == -1 else min(args.page_end, pages_total - 1)
    target = set(range(start, end + 1))
    return target, target != all_indices


def _merge_page_text(*, base_text: str, image_ocr_blocks: list[str]) -> str:
    parts: list[str] = []
    if base_text:
        parts.append(base_text)
    parts.extend(image_ocr_blocks)
    return "\n\n".join(parts)


def _require_asset_content_type(content_type: str | None) -> str:
    if content_type is None or not content_type.strip():
        raise FileReadError("asset has no content_type")
    return content_type


def _asset_extension(content_type: str) -> str:
    if content_type == "image/png":
        return "png"
    if content_type in {"image/jpeg", "image/jpg"}:
        return "jpg"
    if content_type == "image/webp":
        return "webp"
    if content_type == "image/gif":
        return "gif"
    raise FileReadError(f"unknown asset content_type: {content_type}")


def _asset_bytes(asset: ReadAsset, *, file_name: str, page_index: int) -> bytes:
    if not asset.bytes_b64:
        raise FileReadError(
            f"asset has no bytes at {file_name}#p{page_index + 1} ({asset.kind.value})"
        )
    return base64.b64decode(asset.bytes_b64)


async def _vision_ocr_image_bytes(
    image_bytes: bytes,
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
        image_bytes,
        file_name=file_name,
        mime=mime,
        prompt=prompt,
        vision_model=vision_model,
        compression=compression,
        trace_name="core.files.reader.page_vision",
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


async def _persist_page_assets(
    assets: list[ReadAsset],
    *,
    persist_namespace: str | None,
    source_file_id: str | None,
    file_name: str,
    page_index: int,
) -> list[FileRef]:
    if persist_namespace is None:
        return []
    if source_file_id is None or not source_file_id.strip():
        raise ValueError("index persist requires source file_id")
    files_service = FileReader.require_files_service()
    refs: list[FileRef] = []
    for image_index, asset in enumerate(assets, start=1):
        content_type = _require_asset_content_type(asset.content_type)
        ext = _asset_extension(content_type)
        original_name = f"{file_name}#p{page_index + 1}_img{image_index}.{ext}"
        refs.append(
            await persist_extract_asset(
                files_service=files_service,
                namespace_id=persist_namespace,
                source_file_id=source_file_id.strip(),
                original_name=original_name,
                content_type=content_type,
                data=_asset_bytes(asset, file_name=file_name, page_index=page_index),
            )
        )
    return refs


async def _materialize_read_page(
    page: ReadPage,
    *,
    kind: FileReadKind,
    file_name: str,
    prompt: str,
    vision_model: str | None,
    compression: CompressionMode,
    file_id: str | None,
    checksum: str | None,
    persist_namespace: str | None,
    force_vision: bool,
    forced_lane: ReadLane | None,
    include_nested: bool,
) -> tuple[UniversalPage, bool]:
    merge_text = page_text_for_merge(page.text)
    text_usable = page_text_usable(page.text)
    files = await _persist_page_assets(
        page.assets,
        persist_namespace=persist_namespace,
        source_file_id=file_id,
        file_name=file_name,
        page_index=page.index,
    )

    vision_used = False
    ocr_blocks: list[str] = []
    # Page-level hybrid: OCR assets only when text unusable or forced vision lane.
    need_vision = bool(page.assets) and (force_vision or not text_usable)
    if need_vision:
        for image_index, asset in enumerate(page.assets, start=1):
            ocr_text = await _vision_ocr_image_bytes(
                _asset_bytes(asset, file_name=file_name, page_index=page.index),
                file_name=f"{file_name}#p{page.index + 1}:img{image_index}",
                mime=_require_asset_content_type(asset.content_type),
                prompt=prompt,
                vision_model=vision_model,
                compression=compression,
                file_id=file_id,
                checksum=checksum,
                page_index=page.index,
                image_checksum=asset.checksum,
            )
            vision_used = True
            ocr_blocks.append(f"[image {image_index}]\n{ocr_text}")

    merged = _merge_page_text(base_text=merge_text, image_ocr_blocks=ocr_blocks)
    text_blocks = list(page.blocks)
    if not text_blocks and merge_text:
        text_blocks = [ExtractBlock(kind=ExtractBlockKind.PARAGRAPH, text=merge_text)]
    if ocr_blocks:
        text_blocks.append(
            ExtractBlock(kind=ExtractBlockKind.PARAGRAPH, text="\n\n".join(ocr_blocks))
        )
    figure_blocks: list[ExtractBlock] = []
    if files:
        for file_ref in files:
            figure_blocks.append(
                ExtractBlock(kind=ExtractBlockKind.FIGURE, text="[figure]", files=[file_ref])
            )
    elif page.assets:
        for _asset in page.assets:
            figure_blocks.append(ExtractBlock(kind=ExtractBlockKind.FIGURE, text="[figure]"))
    blocks = [*text_blocks, *figure_blocks]
    page_text = merged if merged.strip() else "\n\n".join(
        block.text.strip() for block in blocks if block.text.strip()
    )
    if kind == FileReadKind.IMAGE and vision_used:
        content_mode = ContentMode.VISION
    elif forced_lane is ReadLane.VISION and vision_used:
        content_mode = ContentMode.VISION
    elif vision_used:
        content_mode = ContentMode.HYBRID
    else:
        content_mode = ContentMode.FULL
    nested: list[NestedContent] = []
    if include_nested:
        nested = nested_from_page_assets(page, parent_name=file_name)
    return (
        UniversalPage(
            index=page.index,
            label=resolved_page_label(page.index, page.label),
            text=page_text,
            content_mode=content_mode,
            blocks=blocks,
            files=files,
            nested=nested,
        ),
        vision_used,
    )


def _strip_extract_for_cache(extract: FileExtract) -> FileExtract:
    pages = [
        page.model_copy(update={"nested": strip_nested_bytes(page.nested)})
        for page in extract.pages
    ]
    return extract.model_copy(update={"pages": pages})


async def _rehydrate_nested_from_raw(
    extract: FileExtract,
    *,
    raw: bytes,
    args: ReadFileArgs,
    resolved_name: str,
) -> FileExtract:
    """Восстанавливает bytes_b64 nested после cache hit."""
    if args.forced_lane is ReadLane.TEXT:
        return extract
    needs_bytes = any(
        item.bytes_b64 is None for page in extract.pages for item in page.nested
    )
    if not needs_bytes and any(page.nested for page in extract.pages):
        return extract
    if extract.kind != FileReadKind.PDF:
        opts = read_options_from_args(
            args, source_file_id=extract.file_id, include_asset_bytes=True
        )
        reader = FileReader()
        result = await reader.read_raw_bytes(raw, resolved_name, opts)
        source_pages = read_pages_for_layout(result, file_name=extract.file_name)
        by_index = {page.index: page for page in source_pages}
        pages: list[UniversalPage] = []
        for page in extract.pages:
            source = by_index.get(page.index)
            if source is None:
                pages.append(page)
                continue
            nested = nested_from_page_assets(source, parent_name=extract.file_name)
            pages.append(page.model_copy(update={"nested": nested}))
        return extract.model_copy(update={"pages": pages})

    warnings: list[str] = []
    indices = {page.index for page in extract.pages}
    source_pages = list(
        iter_pdf_read_pages(
            raw,
            resolved_name,
            page_indices=indices,
            force_raster=False,
            warnings=warnings,
        )
    )
    by_index = {page.index: page for page in source_pages}
    pages = []
    for page in extract.pages:
        source = by_index.get(page.index)
        if source is None:
            pages.append(page)
            continue
        nested = nested_from_page_assets(source, parent_name=extract.file_name)
        pages.append(page.model_copy(update={"nested": nested}))
    return extract.model_copy(update={"pages": pages})


async def _deliver_nested(
    extract: FileExtract,
    args: ReadFileArgs,
    *,
    prompt: str,
) -> tuple[FileExtract, list[NestedContent], dict[str, str], set[str], list[str]]:
    """Persist/limit/compress nested; optional recursive OCR. Returns window nested for FileResult."""
    warnings: list[str] = list(extract.warnings)
    if args.forced_lane is ReadLane.TEXT:
        cleared = [
            page.model_copy(update={"nested": []}) for page in extract.pages
        ]
        return extract.model_copy(update={"pages": cleared}), [], {}, set(), warnings

    start = args.page_start
    end = (
        extract.page_layout.pages_total - 1
        if args.page_end == -1
        else min(args.page_end, extract.page_layout.pages_total - 1)
    )
    window_nested: list[NestedContent] = []
    for page in extract.pages:
        if start <= page.index <= end:
            window_nested.extend(page.nested)

    omitted: set[str] = set()
    limited = window_nested
    if args.max_nested >= 0 and len(window_nested) > args.max_nested:
        limited = window_nested[: args.max_nested]
        for item in window_nested[args.max_nested :]:
            omitted.add(item.anchor)
        warnings.append(
            f"nested truncated to max_nested={args.max_nested} "
            + f"(had {len(window_nested)})"
        )

    compressed: list[NestedContent] = []
    for item in limited:
        if item.content_type.startswith("image/") and item.bytes_b64:
            compressed.append(compress_nested_image(item))
        else:
            compressed.append(item)

    keep_bytes = args.nested_mode is NestedMode.PARTS
    delivered: list[NestedContent] = []
    try:
        _ = FileReader.require_files_service()
        files_service_ready = True
    except ValueError:
        files_service_ready = False
    if files_service_ready:
        for item in compressed:
            if item.bytes_b64 is None:
                delivered.append(item)
                continue
            delivered.append(
                await persist_nested_content(
                    item,
                    source_file_id=extract.file_id,
                    namespace_id=args.persist_assets_namespace,
                    keep_bytes=keep_bytes,
                )
            )
    else:
        delivered = compressed
        if args.nested_mode is NestedMode.REFS and compressed:
            warnings.append(
                "nested refs not persisted: FileReader.configure_asset_persist was not called"
            )

    recursive_texts: dict[str, str] = {}
    read_lane = extract.read_lane
    if args.recursive:
        for item in delivered:
            if item.anchor in omitted:
                continue
            if not item.content_type.startswith("image/"):
                continue
            raw = nested_bytes(item) if item.bytes_b64 else None
            if raw is None and item.file_id is not None:
                record = await FileRecord.get(item.file_id)
                if record is None:
                    raise FileReadError(f"nested file not found: {item.file_id}")
                handle = await FileGate().open_record(
                    record, SystemPrincipal(company_id=record.company_id or "")
                )
                raw = await handle.read_bytes()
            if raw is None:
                continue
            ocr = await _vision_ocr_image_bytes(
                raw,
                file_name=item.original_name,
                mime=item.content_type,
                prompt=prompt,
                vision_model=args.vision_model,
                compression=args.compression,
                file_id=extract.file_id,
                checksum=extract.source_checksum,
                page_index=item.page_index,
                image_checksum=item.checksum,
            )
            recursive_texts[item.anchor] = ocr
        if recursive_texts:
            read_lane = ReadLane.HYBRID

    delivered_by_anchor = {item.anchor: item for item in delivered}
    display: list[NestedContent] = []
    for item in window_nested:
        updated_item = delivered_by_anchor.get(item.anchor)
        display.append(updated_item if updated_item is not None else item)

    by_page: dict[int, list[NestedContent]] = {}
    for item in display:
        by_page.setdefault(item.page_index, []).append(item)
    pages: list[UniversalPage] = []
    for page in extract.pages:
        page_nested = by_page.get(page.index)
        if page_nested is None:
            pages.append(page)
            continue
        pages.append(page.model_copy(update={"nested": page_nested}))
    updated = extract.model_copy(update={"pages": pages, "read_lane": read_lane})
    return updated, display, recursive_texts, omitted, warnings


async def _extract_document(
    file_ref: FileRef,
    args: ReadFileArgs,
    *,
    file_id: str | None,
    forced_lane: ReadLane | None,
    resolved_raw: bytes,
    resolved_name: str,
) -> FileExtract:
    file_name = _display_name(file_ref)
    reader = FileReader()
    info = reader.recognize_file_type(file_name=file_name, head=resolved_raw[:8192])
    persist_namespace = args.persist_assets_namespace
    if persist_namespace is not None and (file_id is None or not file_id.strip()):
        raise ValueError("index persist requires source file_id")

    vision_prompt = args.vision_prompt.strip() if args.vision_prompt.strip() else None
    prompt = vision_prompt or "Опиши содержимое страницы и извлеки весь видимый текст."
    checksum = compute_content_checksum_sha256(resolved_raw)
    force_vision = forced_lane in (ReadLane.VISION, ReadLane.HYBRID)
    warnings: list[str] = []

    if info.detected_kind == FileReadKind.PDF and forced_lane != ReadLane.TEXT:
        pages_total = pdf_page_count(resolved_raw)
        target_indices, lazy = _lazy_native_indices(pages_total, args)
        source_pages = list(
            iter_pdf_read_pages(
                resolved_raw,
                resolved_name,
                page_indices=target_indices,
                force_raster=force_vision,
                warnings=warnings,
            )
        )
        kind = FileReadKind.PDF
        mime_type = "application/pdf"
        page_layout = PageLayout(
            kind=PageLayoutKind.NATIVE, pages_total=pages_total, page_size=0
        )
        if lazy:
            warnings.append(
                f"vision применён только к запрошенным страницам (pages_total={pages_total} "
                + f"> порога {VISION_FULL_READ_MAX_PAGES})"
            )
    else:
        opts = read_options_from_args(args, source_file_id=file_id, include_asset_bytes=True)
        result = await reader.read_raw_bytes(resolved_raw, resolved_name, opts)
        source_pages = read_pages_for_layout(result, file_name=file_name)
        kind = result.detected_kind
        mime_type = result.content_type or "application/octet-stream"
        layout_kind = page_layout_kind_for_result(result)
        if layout_kind is PageLayoutKind.NATIVE:
            page_layout = PageLayout(
                kind=layout_kind, pages_total=len(source_pages), page_size=0
            )
        else:
            page_layout = PageLayout(
                kind=layout_kind,
                pages_total=len(source_pages),
                page_size=DEFAULT_VIRTUAL_PAGE_SIZE,
            )
        warnings.extend(result.warnings)
        lazy = False

    if force_vision and not any(page.assets for page in source_pages):
        if forced_lane is ReadLane.VISION:
            raise FileReadError(
                "lane=vision requires an image on the page, "
                + f"but type is {kind.value}"
            )
        warnings.append(
            f"hybrid: у {kind.value} нет ассетов на страницах, прочитан только текст"
        )

    include_nested = forced_lane != ReadLane.TEXT
    universal: list[UniversalPage] = []
    any_vision_used = False
    for page in source_pages:
        materialized, vision_used = await _materialize_read_page(
            page,
            kind=kind,
            file_name=file_name,
            prompt=prompt,
            vision_model=args.vision_model,
            compression=args.compression,
            file_id=file_id,
            checksum=checksum,
            persist_namespace=persist_namespace,
            force_vision=force_vision,
            forced_lane=forced_lane,
            include_nested=include_nested,
        )
        if vision_used:
            any_vision_used = True
        universal.append(materialized)

    if forced_lane is ReadLane.VISION:
        read_lane = ReadLane.VISION
    elif kind == FileReadKind.IMAGE and any_vision_used:
        read_lane = ReadLane.VISION
    elif forced_lane is ReadLane.HYBRID or any_vision_used:
        read_lane = ReadLane.HYBRID
    else:
        read_lane = read_lane_for_kind(kind)

    content_chars_total = sum(len(page.text) for page in universal)

    extract = FileExtract(
        file_id=file_id,
        file_name=file_name,
        kind=kind,
        mime_type=mime_type,
        read_lane=read_lane,
        page_layout=page_layout,
        pages=universal,
        content_chars_total=content_chars_total,
        warnings=warnings,
        source_checksum=checksum,
    )
    if not lazy:
        await store_file_extract(_strip_extract_for_cache(extract))
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
                f"text lane is not applicable to type {info.detected_kind.value}; "
                + "use the universal read_file or a vision/stt tool"
            )

    cached = await load_file_extract(file_id=file_id, checksum=None)
    if cached is not None and not cached_extract_is_stale(cached):
        return await _rehydrate_nested_from_raw(
            cached,
            raw=resolved_raw,
            args=args,
            resolved_name=resolved_name,
        )

    return await _extract_document(
        file_ref,
        args,
        file_id=file_id,
        forced_lane=forced_lane,
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
        content_chars_total=0,
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
    vision_prompt = args.vision_prompt.strip() if args.vision_prompt.strip() else None
    prompt = vision_prompt or "Опиши содержимое страницы и извлеки весь видимый текст."
    for file_ref in file_refs:
        file_budget = per_file_budget + carryover
        try:
            extract = await reader.read(file_ref, args)
            extract, nested, recursive_texts, omitted, warn = await _deliver_nested(
                extract, args, prompt=prompt
            )
            file_result = await render_file_result(
                extract,
                args,
                tool_name=tool_name,
                budget=file_budget,
                nested=nested,
                recursive_texts=recursive_texts,
                omitted_anchors=omitted,
            )
            if warn:
                file_result = file_result.model_copy(update={"warnings": warn})
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
