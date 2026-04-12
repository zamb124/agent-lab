"""
Парсер документов на базе Unstructured (совместимость: строка на выходе).

Контракт ParsedDocument — `core.rag.parsing.unstructured_adapter`.
"""

import logging
from pathlib import Path

from core.rag.parsing.unstructured_adapter import parse_unstructured_bytes, parse_unstructured_file

logger = logging.getLogger(__name__)


class DocumentParser:
    """
    Обертка над Unstructured для парсинга документов.
    Извлекает текст из различных форматов файлов.
    """

    SUPPORTED_EXTENSIONS = {
        ".pdf",
        ".docx",
        ".doc",
        ".xlsx",
        ".xls",
        ".pptx",
        ".ppt",
        ".html",
        ".htm",
        ".txt",
        ".md",
        ".rst",
        ".rtf",
        ".odt",
        ".csv",
        ".tsv",
        ".eml",
        ".msg",
        ".epub",
        ".jpg",
        ".jpeg",
        ".png",
        ".tiff",
        ".bmp",
    }

    def __init__(self, languages: list[str] | None = None) -> None:
        self._languages = languages if languages is not None else ["rus", "eng"]

    def parse_file(self, file_path: str) -> str:
        """
        Парсит файл и возвращает извлеченный текст.

        Args:
            file_path: Путь к файлу

        Returns:
            Извлеченный текст из документа
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            logger.warning("Формат %s может не поддерживаться полностью", ext)

        doc = parse_unstructured_file(file_path, languages=self._languages)
        return doc.canonical_text

    def parse_bytes(self, data: bytes, filename: str) -> str:
        """
        Парсит байты и возвращает извлеченный текст.

        Args:
            data: Содержимое файла в байтах
            filename: Имя файла (для определения типа)

        Returns:
            Извлеченный текст из документа
        """
        ext = Path(filename).suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            logger.warning("Формат %s может не поддерживаться полностью", ext)

        doc = parse_unstructured_bytes(data, filename, languages=self._languages)
        return doc.canonical_text

    def get_file_type(self, filename: str) -> str:
        """
        Определяет тип файла по расширению.

        Args:
            filename: Имя файла

        Returns:
            Тип файла (pdf, docx, xlsx, etc.)
        """
        ext = Path(filename).suffix.lower()
        return ext.lstrip(".")

    def is_supported(self, filename: str) -> bool:
        """
        Проверяет, поддерживается ли формат файла.

        Args:
            filename: Имя файла

        Returns:
            True если формат поддерживается
        """
        ext = Path(filename).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

