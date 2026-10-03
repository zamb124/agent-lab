"""Обработка аудиофайлов."""

from __future__ import annotations

from core.context import require_active_company
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.default_storage import initialize_default_storage
from core.files.media.transcriber import MediaTranscriber
from core.files.models import AudioTranscriptionStatus, FileRecord
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

_default_audio_processor: AudioProcessor | None = None
_processors_ready = False


class AudioProcessor:
    def __init__(self, files_service: FilesService) -> None:
        self._files_service: FilesService = files_service

    async def close(self) -> None:
        return None

    async def process_audio_from_bytes(
        self,
        data: bytes,
        original_name: str,
        content_type: str = "audio/wave",
        uploaded_by: str | None = None,
        auto_recognize: bool = True,
        language: str | None = None,
        metadata: JsonObject | None = None,
        tags: list[str] | None = None,
        public: bool = True,
    ) -> FileRecord:
        _ = uploaded_by
        logger.info("files.event", original_name=original_name, data_count=len(data))

        company_id = require_active_company().company_id
        if company_id == "":
            raise ValueError("process_audio_from_bytes: active company required.")

        audio_record = await self._files_service.create(
            FileCreateSpec(
                source_kind=FileSourceKind.PLATFORM_AUXILIARY,
                source_ref=FileSourceRef(),
                retention=default_retention_for_source(FileSourceKind.PLATFORM_AUXILIARY),
                post_create=FilePostCreate(is_public=public),
                metadata=metadata,
                tags=tags,
            ),
            data,
            original_name=original_name,
            content_type=content_type,
        )

        if auto_recognize:
            transcriber = MediaTranscriber(company_id=company_id)
            transcription_result = await transcriber.transcribe_audio(
                audio_bytes=data,
                file_name=original_name,
                content_type=content_type,
                language=language,
            )
            audio_record = audio_record.model_copy(
                update={
                    "transcription_status": AudioTranscriptionStatus.DONE,
                    "transcription_text": transcription_result.text,
                    "transcription_provider": transcription_result.provider,
                }
            )
            _ = await FileRecord.set(audio_record)

        logger.info("files.event", file_id=audio_record.file_id)
        return audio_record


def initialize_default_processors() -> None:
    global _default_audio_processor, _processors_ready
    _default_audio_processor = None
    _processors_ready = True
    initialize_default_storage()


async def get_default_audio_processor() -> AudioProcessor:
    if not _processors_ready or _default_audio_processor is None:
        raise RuntimeError(
            "AudioProcessor is not configured. Pass FilesService to AudioProcessor."
        )
    return _default_audio_processor


async def close_default_audio_processor() -> None:
    global _default_audio_processor
    if _default_audio_processor:
        await _default_audio_processor.close()
        _default_audio_processor = None
