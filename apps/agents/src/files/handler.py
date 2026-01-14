"""
Обработчик файлов из A2A сообщений.
Извлекает FilePart, сохраняет в tmp, формирует информацию для state.files.
"""

import base64
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from a2a.types import FilePart, FileWithBytes, FileWithUri, Message

from apps.agents.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


def get_temp_dir() -> Path:
    """Возвращает путь к директории для временных файлов из конфига."""
    return Path(settings.files.temp_dir)


def get_file_parts(message: Message) -> List[FilePart]:
    """Извлекает все FilePart из Message."""
    file_parts: List[FilePart] = []
    for part in message.parts:
        if isinstance(part.root, FilePart):
            file_parts.append(part.root)
        elif hasattr(part.root, "kind") and part.root.kind == "file":
            file_parts.append(part.root)
    return file_parts


@dataclass
class FileInfo:
    """Информация о сохраненном файле."""

    name: str
    path: str
    mime_type: Optional[str]
    size: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "mime_type": self.mime_type,
            "size": self.size,
        }


class FileHandler:
    """Обработчик файлов из A2A сообщений."""

    def __init__(self, temp_dir: Optional[Path] = None):
        self.temp_dir = temp_dir or get_temp_dir()
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def extract_and_save(self, message: Message) -> List[FileInfo]:
        """
        Извлекает файлы из Message и сохраняет в tmp.

        Args:
            message: A2A Message с возможными FilePart

        Returns:
            Список FileInfo сохраненных файлов
        """
        file_parts = get_file_parts(message)
        if not file_parts:
            return []

        saved_files: List[FileInfo] = []
        for file_part in file_parts:
            file_info = self._save_file_part(file_part)
            if file_info:
                saved_files.append(file_info)

        return saved_files

    def _save_file_part(self, file_part: FilePart) -> Optional[FileInfo]:
        """Сохраняет один FilePart и возвращает FileInfo."""
        file_data = file_part.file

        if isinstance(file_data, FileWithBytes):
            return self._save_bytes_file(file_data)
        elif isinstance(file_data, FileWithUri):
            return self._save_uri_file(file_data)

        logger.warning(f"Unknown file type: {type(file_data)}")
        return None

    def _save_bytes_file(self, file_data: FileWithBytes) -> FileInfo:
        """Сохраняет файл из base64 bytes."""
        file_bytes = base64.b64decode(file_data.bytes)

        name = file_data.name or f"file_{uuid.uuid4().hex[:8]}"
        ext = self._get_extension(file_data.mime_type, name)
        if not name.endswith(ext):
            name = f"{name}{ext}"

        unique_name = f"{uuid.uuid4().hex}_{name}"
        file_path = self.temp_dir / unique_name

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        logger.info(f"Saved file: {file_path}")

        return FileInfo(
            name=name,
            path=str(file_path.absolute()),
            mime_type=file_data.mime_type,
            size=len(file_bytes),
        )

    def _save_uri_file(self, file_data: FileWithUri) -> FileInfo:
        """Создает FileInfo для файла по URI (без скачивания)."""
        name = file_data.name or Path(file_data.uri).name or f"file_{uuid.uuid4().hex[:8]}"

        return FileInfo(
            name=name,
            path=file_data.uri,
            mime_type=file_data.mime_type,
            size=0,
        )

    def _get_extension(self, mime_type: Optional[str], name: str) -> str:
        """Определяет расширение файла."""
        if "." in name:
            return ""

        mime_to_ext = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "application/pdf": ".pdf",
            "text/plain": ".txt",
            "application/json": ".json",
        }

        if mime_type:
            return mime_to_ext.get(mime_type, "")
        return ""

    @staticmethod
    def format_files_for_content(files: List[FileInfo]) -> str:
        """
        Форматирует информацию о файлах для добавления в content сообщения.

        Returns:
            Строка с [FILE]...[/FILE] тегами
        """
        if not files:
            return ""

        parts = []
        for f in files:
            parts.append(
                f"\n[FILE]\nname: {f.name}\npath: {f.path}\nmime_type: {f.mime_type or 'unknown'}\n[/FILE]"
            )

        return "".join(parts)

    @staticmethod
    def files_to_state(files: List[FileInfo]) -> List[Dict[str, Any]]:
        """Конвертирует список FileInfo в формат для state.files."""
        return [f.to_dict() for f in files]

