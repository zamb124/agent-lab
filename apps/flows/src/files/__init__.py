"""
Модуль для работы с файлами в A2A сообщениях.
"""

from .handler import (
    IncomingA2aFile,
    extract_incoming_a2a_files,
    format_a2a_files_content,
    get_file_parts,
)

__all__ = [
    "IncomingA2aFile",
    "extract_incoming_a2a_files",
    "format_a2a_files_content",
    "get_file_parts",
]
