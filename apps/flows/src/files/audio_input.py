"""
Авто-распознавание входящих audio-вложений A2A → текст реплики пользователя.

Применяется в одной точке `_persist_incoming_a2a_files` канала A2A: покрывает
все способы входа во flow (A2A SDK/CLI, embed-chat виджет, наш чат, sync
takeover), потому что embed/chat ходят через те же `/flows/api/v1/.../message/send`
и `/.../message/stream` эндпоинты, что и публичный A2A API.

Контракт:
- На входе — список item-ов формата state.files (`original_name`, `url`,
  `content_type`, `file_size`, опционально `file_id`).
- Для каждого item с категорией AUDIO достаются байты (через `file_processor`
  + S3, по `file_id`; URI без `file_id` пропускаются как «внешний ресурс,
  который скачивать не наша работа»), вызывается `voice_resolver.get_stt_client(...)
  .transcribe_audio(...)` и формируется блок текста для добавления в content.
- Возвращается строка, готовая к конкатенации с пользовательским text-content
  (пустая, если транскрибировать нечего).

Zero-Guess: при отсутствии активной компании в request scope бросаем
`ValueError`. Любая ошибка STT-провайдера прокидывается наверх.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from apps.flows.src.services.flow_speech_resolve import (
    load_flow_speech_layers_from_context_metadata,
    merge_explicit_over_flow_speech_layer,
)
from core.clients.speech_override import SpeechOverride
from core.clients.voice_resolver import get_stt_client
from core.context import get_context
from core.files.file_ref import FileRef
from core.files.types import FileCategory, ext_to_category, mime_to_category
from core.logging import get_logger

if TYPE_CHECKING:
    from apps.flows.src.container_contracts import FlowRuntimeContainer

logger = get_logger(__name__)


def _is_audio_item(item: FileRef) -> bool:
    """Определяет категорию AUDIO по content_type, иначе по расширению `original_name`."""
    content_type = item.content_type.strip()
    cat = mime_to_category(content_type.split(";", 1)[0].strip())
    if cat is FileCategory.AUDIO:
        return True
    ext = Path(item.original_name).suffix.lower()
    if ext and ext_to_category(ext) is FileCategory.AUDIO:
        return True
    return False


async def _read_persisted_audio_bytes(
    *,
    container: "FlowRuntimeContainer",
    file_id: str,
) -> tuple[bytes, str, str]:
    """
    Читает байты persisted-файла из S3 по file_id.

    Возвращает (audio_bytes, original_name, content_type).
    """
    record = await container.file_processor.get_file_record(file_id)
    if record is None:
        raise ValueError(
            f"audio_input: persisted-файл {file_id!r} не найден в FileRepository"
        )
    s3 = await container.file_processor.get_s3_client()
    audio_bytes = await s3.download_bytes(record.s3_key, bucket=record.s3_bucket)
    return audio_bytes, record.original_name, record.content_type


async def transcribe_incoming_audio_files(
    *,
    container: "FlowRuntimeContainer",
    files_data: list[FileRef],
    company_id: str,
    language: str | None = None,
) -> str:
    """
    Возвращает блок текста для конкатенации с content сообщения.

    Формат блока: `\n[AUDIO_TRANSCRIPT original_name=<file>]\n<текст>\n[/AUDIO_TRANSCRIPT]`
    на каждое успешно распознанное аудио. Если входящих audio-вложений нет —
    пустая строка.
    """
    if company_id == "":
        raise ValueError("transcribe_incoming_audio_files: company_id обязателен.")

    audio_items: list[FileRef] = [
        item for item in files_data if _is_audio_item(item)
    ]
    if not audio_items:
        return ""

    ctx = get_context()
    stt_flow, _, _ = load_flow_speech_layers_from_context_metadata(
        ctx.metadata if ctx else None
    )
    merged = merge_explicit_over_flow_speech_layer(SpeechOverride(), stt_flow)
    if language:
        merged = merged.model_copy(update={"language": language})
    elif ctx is not None and merged.language is None:
        merged = merged.model_copy(update={"language": ctx.language.value})
    stt = await get_stt_client(company_id=company_id, override=merged)

    parts: list[str] = []
    for item in audio_items:
        if item.file_id is None:
            logger.info(
                "audio_input.skip_uri_only",
                original_name=item.original_name,
                content_type=item.content_type,
            )
            continue
        audio_bytes, original_name, content_type = await _read_persisted_audio_bytes(
            container=container,
            file_id=item.file_id,
        )
        result = await stt.transcribe_audio(
            audio_bytes=audio_bytes,
            file_name=original_name,
            content_type=content_type,
            language=merged.language,
        )
        text = (result.text or "").strip()
        if text == "":
            logger.info(
                "audio_input.empty_transcript",
                file_id=item.file_id,
                provider=result.provider,
                status=result.status,
            )
            continue
        parts.append(
            f"\n[AUDIO_TRANSCRIPT original_name={original_name}]\n{text}\n[/AUDIO_TRANSCRIPT]"
        )

    return "".join(parts)
