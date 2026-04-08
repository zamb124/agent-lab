"""
Files - работа с файлами и S3.
"""

from core.files.api import build_file_api_router
from core.files.checksum import compute_content_checksum_sha256
from core.files.docx_template import (
    DocxTemplateContextError,
    DocxTemplateError,
    DocxTemplateInvalidError,
    DocxTemplater,
    DocxTemplateSourceError,
    DocxTemplateSyntaxError,
    read_template_bytes_from_file_ref,
    render_docx_template_bytes,
)
from core.files.file_ref import (
    FileRef,
    file_id_from_download_url,
    normalize_file_ref,
)
from core.files.media import (
    MediaTranscriber,
    TranscriptionResult,
    extract_audio_from_video,
    transcribe_audio_with_chunking,
)
from core.files.models import (
    AudioAttachmentContent,
    AudioMetadata,
    AudioRecord,
    AudioTranscriptionStatus,
    FileMetadata,
    FileReadPreviewResponse,
    FileRecord,
    FileResponse,
    FileStatus,
    VideoAttachmentContent,
)
from core.files.processors import (
    AudioProcessor,
    FileProcessor,
    close_default_audio_processor,
    close_default_file_processor,
    get_default_audio_processor,
    get_default_file_processor,
    initialize_default_processors,
)
from core.files.reader import (
    FileReader,
    FileReadError,
    FileReadResult,
    ReadOptions,
    ReadPage,
    merge_file_ref_read_options,
)
from core.files.s3_client import (
    S3Client,
    S3ClientFactory,
    close_default_s3_client,
    get_default_s3_client,
)
from core.files.streaming import stream_s3_file
from core.files.writer import (
    ContentKind,
    FileWriteError,
    FileWriter,
    FileWriteResult,
    WriteOptions,
    classify_content,
    write_bytes_via_processor,
)

__all__ = [
    "compute_content_checksum_sha256",
    "classify_content",
    "ContentKind",
    "FileReadError",
    "FileReader",
    "FileReadResult",
    "ReadOptions",
    "ReadPage",
    "FileWriteError",
    "FileWriteResult",
    "FileWriter",
    "WriteOptions",
    "write_bytes_via_processor",
    "S3Client",
    "S3ClientFactory",
    "get_default_s3_client",
    "close_default_s3_client",
    "FileRecord",
    "FileReadPreviewResponse",
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
    "DocxTemplater",
    "DocxTemplateContextError",
    "DocxTemplateError",
    "DocxTemplateInvalidError",
    "DocxTemplateSourceError",
    "DocxTemplateSyntaxError",
    "FileRef",
    "file_id_from_download_url",
    "merge_file_ref_read_options",
    "normalize_file_ref",
    "read_template_bytes_from_file_ref",
    "render_docx_template_bytes",
    "MediaTranscriber",
    "TranscriptionResult",
    "extract_audio_from_video",
    "transcribe_audio_with_chunking",
]
