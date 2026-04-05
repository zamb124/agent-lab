"""
Files - работа с файлами и S3.
"""

from core.files.checksum import compute_content_checksum_sha256
from core.files.reader import (
    FileReadError,
    FileReader,
    FileReadResult,
    ReadOptions,
    ReadPage,
)
from core.files.s3_client import S3Client, S3ClientFactory, get_default_s3_client, close_default_s3_client
from core.files.models import (
    FileRecord,
    FileResponse,
    AudioRecord,
    AudioAttachmentContent,
    VideoAttachmentContent,
    AudioTranscriptionStatus,
    FileStatus,
    FileMetadata,
    AudioMetadata,
)
from core.files.processors import (
    FileProcessor,
    AudioProcessor,
    initialize_default_processors,
    get_default_file_processor,
    get_default_audio_processor,
    close_default_file_processor,
    close_default_audio_processor,
)
from core.files.api import build_file_api_router
from core.files.streaming import stream_s3_file

__all__ = [
    "compute_content_checksum_sha256",
    "FileReadError",
    "FileReader",
    "FileReadResult",
    "ReadOptions",
    "ReadPage",
    "S3Client",
    "S3ClientFactory",
    "get_default_s3_client",
    "close_default_s3_client",
    "FileRecord",
    "FileResponse",
    "AudioRecord",
    "AudioAttachmentContent",
    "VideoAttachmentContent",
    "AudioTranscriptionStatus",
    "FileStatus",
    "FileMetadata",
    "AudioMetadata",
    "FileProcessor",
    "AudioProcessor",
    "initialize_default_processors",
    "get_default_file_processor",
    "get_default_audio_processor",
    "close_default_file_processor",
    "close_default_audio_processor",
    "build_file_api_router",
    "stream_s3_file",
]
