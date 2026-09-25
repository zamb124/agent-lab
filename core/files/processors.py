"""Обработка аудиофайлов."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import quote

from core.context import require_active_company
from core.files.create_spec import FileSourceKind
from core.files.default_storage import initialize_default_storage
from core.files.media.transcriber import MediaTranscriber
from core.files.models import AudioTranscriptionStatus, FileRecord, FileStatus
from core.files.object_storage import PLATFORM_STORAGE_ID
from core.files.object_store.gate import FileGate
from core.files.object_store.s3_client import S3Client
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

_default_audio_processor: AudioProcessor | None = None
_processors_ready = False


def _to_ascii_s3_metadata(metadata: JsonObject) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_key, raw_value in metadata.items():
        key = raw_key.strip()
        if isinstance(raw_value, Mapping) or (
            isinstance(raw_value, Sequence) and not isinstance(raw_value, str)
        ):
            value = json.dumps(raw_value, ensure_ascii=False, separators=(",", ":"))
        else:
            value = str(raw_value)
        out[key] = value if value.isascii() else quote(value, safe="")
    return out


class AudioProcessor:
    def __init__(self) -> None:
        self._s3_client: S3Client | None = None
        self._storage_id: str | None = None

    async def get_s3_client(self, company_id: str) -> tuple[str, S3Client]:
        if self._s3_client is None or self._storage_id is None:
            resolved, client = await FileGate().client_for_write(
                company_id,
                FileSourceKind.PLATFORM_AUXILIARY,
            )
            self._s3_client = client
            self._storage_id = resolved.storage_id
        return self._storage_id, self._s3_client

    async def close(self) -> None:
        self._s3_client = None
        self._storage_id = None

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
        logger.info("files.event", original_name=original_name, data_count=len(data))

        company_id = require_active_company().company_id
        if company_id == "":
            raise ValueError("process_audio_from_bytes: active company required.")

        file_id = f"file_{uuid.uuid4().hex[:12]}"
        file_hash = hashlib.sha256(data).hexdigest()[:16]
        extension = Path(original_name).suffix or ".wav"
        s3_key = f"audio/{file_id}_{file_hash}{extension}"

        storage_id, s3_client = await self.get_s3_client(company_id)

        _ = await s3_client.upload_bytes(
            data=data,
            key=s3_key,
            metadata=_to_ascii_s3_metadata(metadata or {}),
            content_type=content_type,
            public=public,
        )

        transcription_text = None
        transcription_status = AudioTranscriptionStatus.IDLE
        transcription_error: str | None = None
        transcription_provider: str | None = None

        if auto_recognize:
            transcriber = MediaTranscriber(company_id=company_id)
            transcription_result = await transcriber.transcribe_audio(
                audio_bytes=data,
                file_name=original_name,
                content_type=content_type,
                language=language,
            )
            transcription_text = transcription_result.text
            transcription_status = AudioTranscriptionStatus.DONE
            transcription_provider = transcription_result.provider

        audio_record = FileRecord(
            file_id=file_id,
            original_name=original_name,
            content_type=content_type,
            file_size=len(data),
            storage_id=storage_id if storage_id != "" else PLATFORM_STORAGE_ID,
            s3_key=s3_key,
            uploaded_by=uploaded_by,
            company_id=company_id,
            status=FileStatus.READY,
            metadata=metadata or {},
            tags=tags or [],
            is_public=public,
            transcription_status=transcription_status,
            transcription_text=transcription_text,
            transcription_error=transcription_error,
            transcription_provider=transcription_provider,
        )

        _ = await FileRecord.set(audio_record)
        logger.info("files.event", file_id=file_id)
        return audio_record


def initialize_default_processors() -> None:
    global _default_audio_processor, _processors_ready
    _default_audio_processor = None
    _processors_ready = True
    initialize_default_storage()


async def get_default_audio_processor() -> AudioProcessor:
    global _default_audio_processor
    if not _processors_ready:
        raise RuntimeError(
            "Processors not initialized. Call initialize_default_processors at startup."
        )
    if _default_audio_processor is None:
        _default_audio_processor = AudioProcessor()
    return _default_audio_processor


async def close_default_audio_processor() -> None:
    global _default_audio_processor
    if _default_audio_processor:
        await _default_audio_processor.close()
        _default_audio_processor = None
