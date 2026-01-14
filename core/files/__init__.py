"""
Files - работа с файлами и S3.
"""

from core.files.s3_client import S3Client, S3ClientFactory, get_default_s3_client, close_default_s3_client
from core.files.models import (
    FileRecord,
    AudioRecord,
    FileStatus,
    CloudVoiceTokenConfig,
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

__all__ = [
    "S3Client",
    "S3ClientFactory",
    "get_default_s3_client",
    "close_default_s3_client",
    "FileRecord",
    "AudioRecord",
    "FileStatus",
    "CloudVoiceTokenConfig",
    "FileMetadata",
    "AudioMetadata",
    "FileProcessor",
    "AudioProcessor",
    "initialize_default_processors",
    "get_default_file_processor",
    "get_default_audio_processor",
    "close_default_file_processor",
    "close_default_audio_processor",
]
