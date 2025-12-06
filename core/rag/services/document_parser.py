"""
Парсер документов на базе Unstructured.
Поддерживает PDF, DOCX, XLSX, PPTX, HTML, TXT, Markdown и другие форматы.
"""

import logging
from pathlib import Path
from typing import List, Optional
from io import BytesIO

logger = logging.getLogger(__name__)


class DocumentParser:
    """
    Обертка над Unstructured для парсинга документов.
    Извлекает текст из различных форматов файлов.
    """
    
    SUPPORTED_EXTENSIONS = {
        ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
        ".html", ".htm", ".txt", ".md", ".rst", ".rtf", ".odt",
        ".csv", ".tsv", ".eml", ".msg", ".epub",
        ".jpg", ".jpeg", ".png", ".tiff", ".bmp",
    }
    
    def __init__(self):
        pass
    
    def parse_file(self, file_path: str) -> str:
        """
        Парсит файл и возвращает извлеченный текст.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Извлеченный текст из документа
        """
        from unstructured.partition.auto import partition
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            logger.warning(f"Формат {ext} может не поддерживаться полностью")
        
        elements = partition(filename=str(path), languages=["rus", "eng"])
        text = self._elements_to_text(elements)
        
        logger.info(f"Распарсен файл {path.name}: {len(text)} символов")
        return text
    
    def parse_bytes(self, data: bytes, filename: str) -> str:
        """
        Парсит байты и возвращает извлеченный текст.
        
        Args:
            data: Содержимое файла в байтах
            filename: Имя файла (для определения типа)
            
        Returns:
            Извлеченный текст из документа
        """
        from unstructured.partition.auto import partition
        
        ext = Path(filename).suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            logger.warning(f"Формат {ext} может не поддерживаться полностью")
        
        file_obj = BytesIO(data)
        elements = partition(file=file_obj, metadata_filename=filename, languages=["rus", "eng"])
        text = self._elements_to_text(elements)
        
        logger.info(f"Распарсен файл {filename}: {len(text)} символов")
        return text
    
    def _elements_to_text(self, elements: List) -> str:
        """
        Конвертирует элементы Unstructured в текст.
        
        Args:
            elements: Список элементов от Unstructured
            
        Returns:
            Объединенный текст
        """
        texts = []
        for element in elements:
            text = str(element).strip()
            if text:
                texts.append(text)
        
        return "\n\n".join(texts)
    
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

