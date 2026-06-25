"""Audio processing and file message parsing helpers."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from core.context import require_active_company
from core.files.default_storage import initialize_default_storage
from core.files.media.transcriber import MediaTranscriber
from core.files.models import (
    AudioRecord,
    AudioTranscriptionStatus,
    FileStatus,
)
from core.files.s3_client import S3Client, S3ClientFactory
from core.logging import get_logger
from core.types import JsonObject

if TYPE_CHECKING:
    from core.files.file_repository import FileRepository

logger = get_logger(__name__)
FILE_MESSAGE_RE = re.compile(
    r"\[FILE\][\s\n]*📎?\s*Файл:\s*([^\(]+)\s*"
    + r"\(ID:\s*([^,]+),\s*URL:\s*([^,]+),\s*тип:\s*([^,]+),\s*"
    + r"размер:\s*([^)]+)\)[\s\n]*\[/FILE\]",
    re.MULTILINE,
)

_default_audio_processor: "AudioProcessor | None" = None
_default_file_repository: FileRepository | None = None


def _to_ascii_s3_metadata(metadata: JsonObject) -> dict[str, str]:
    from urllib.parse import quote

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


def format_file_message(file_record: object) -> str:
    from core.files.models import FileRecord

    if not isinstance(file_record, FileRecord):
        raise TypeError("file_record must be FileRecord")
    size_mb = file_record.file_size / (1024 * 1024)
    size_str = (
        f"{size_mb:.2f} MB" if size_mb >= 1 else f"{file_record.file_size} байт"
    )
    url = file_record.url
    return (
        f"[FILE] "
        f"Файл: {file_record.original_name} "
        f"(ID: {file_record.file_id}, "
        f"URL: {url}, "
        f"тип: {file_record.content_type}, "
        f"размер: {size_str}) "
        f"[/FILE]"
    )


def extract_file_info_from_message(message_content: str) -> list[JsonObject]:
    file_info_list: list[JsonObject] = []
    for match in FILE_MESSAGE_RE.finditer(message_content):
        file_info_list.append({
            "original_name": match.group(1).strip(),
            "file_id": match.group(2).strip(),
            "url": match.group(3).strip(),
            "content_type": match.group(4).strip(),
            "file_size": match.group(5).strip(),
        })
    return file_info_list


class AudioProcessor:
    def __init__(
        self,
        file_repository: FileRepository,
        bucket_name: str | None = None,
    ) -> None:
        self.file_repository: FileRepository = file_repository
        self.bucket_name: str | None = bucket_name
        self._s3_client: S3Client | None = None

    async def get_s3_client(self) -> S3Client:
        if self._s3_client is None:
            if self.bucket_name:
                self._s3_client = S3ClientFactory.create_client_for_bucket(self.bucket_name)
            else:
                self._s3_client = S3ClientFactory.create_default_client()
        return self._s3_client

    async def close(self) -> None:
        if self._s3_client:
            await self._s3_client.close()
            self._s3_client = None

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
    ) -> AudioRecord:
        logger.info("Обработка аудио: %s, размер=%s байт", original_name, len(data))

        file_id = f"file_{uuid.uuid4().hex[:12]}"
        file_hash = hashlib.sha256(data).hexdigest()[:16]
        extension = Path(original_name).suffix or ".wav"
        s3_key = f"audio/{file_id}_{file_hash}{extension}"

        s3_client = await self.get_s3_client()

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
            company_id = require_active_company().company_id
            if company_id == "":
                raise ValueError(
                    "process_audio_from_bytes: active company required for auto_recognize."
                )
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

        audio_record = AudioRecord(
            file_id=file_id,
            provider=s3_client.provider_name,
            original_name=original_name,
            content_type=content_type,
            file_size=len(data),
            s3_bucket=s3_client.require_bucket_config_key(),
            s3_key=s3_key,
            s3_endpoint=s3_client.endpoint_url,
            uploaded_by=uploaded_by,
            status=FileStatus.READY,
            metadata=metadata or {},
            tags=tags or [],
            transcription_status=transcription_status,
            transcription_text=transcription_text,
            transcription_error=transcription_error,
            transcription_provider=transcription_provider,
        )

        _ = await self.file_repository.set(audio_record)
        logger.info("Аудио обработано: %s", file_id)
        return audio_record

    async def get_audio_record(self, audio_id: str) -> AudioRecord | None:
        record = await self.file_repository.get(audio_id)
        if record is None:
            return None
        if isinstance(record, AudioRecord):
            return record
        return AudioRecord.model_validate(record.model_dump(mode="json"))


def initialize_default_processors(file_repository: FileRepository) -> None:
    global _default_file_repository, _default_audio_processor
    _default_file_repository = file_repository
    _default_audio_processor = None
    initialize_default_storage(file_repository)


async def get_default_audio_processor() -> AudioProcessor:
    global _default_audio_processor
    if _default_audio_processor is None:
        if _default_file_repository is None:
            raise RuntimeError(
                "Processors not initialized. Call initialize_default_processors at startup."
            )
        _default_audio_processor = AudioProcessor(file_repository=_default_file_repository)
    return _default_audio_processor


async def close_default_audio_processor() -> None:
    global _default_audio_processor
    if _default_audio_processor:
        await _default_audio_processor.close()
        _default_audio_processor = None
