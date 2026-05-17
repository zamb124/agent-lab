"""
Nano Banana клиент для генерации изображений через OpenRouter.
Использует LLM с multimodal support вместо прямого обращения к Google.

АДАПТИРОВАНО: убраны зависимости от app/*, используется только core/*
"""

import base64
import json
import re
import uuid
from typing import TYPE_CHECKING, Protocol

from a2a.types import FilePart, FileWithBytes, Message, Part, Role, TextPart
from a2a.utils.message import get_message_text

from core.clients.llm.factory import get_llm
from core.config import get_settings
from core.files.s3_client import S3ClientFactory
from core.logging import get_logger

if TYPE_CHECKING:
    from core.db.storage import Storage

logger = get_logger(__name__)


class _ChatLLM(Protocol):
    async def chat(self, messages: list[Message]) -> Message:
        ...


class NanoBananaClient:
    """
    Клиент для генерации изображений через OpenRouter.
    Использует LLM с multimodal support.
    """

    def __init__(
        self,
        storage: "Storage",
        model_name: str = "google/gemini-2.5-flash-preview-image",
        timeout: int = 60,
    ):
        """
        Args:
            storage: Storage для работы с БД
            model_name: Имя модели для генерации
            timeout: Таймаут запросов
        """
        self._storage = storage
        self._model_name = model_name
        self._timeout = timeout
        self._llm: _ChatLLM | None = None

    def _get_llm(self) -> _ChatLLM:
        """Получает LLM с multimodal support"""
        if self._llm is None:
            self._llm = get_llm(model_name=self._model_name)
        return self._llm

    async def generate_images(
        self,
        prompt: str,
        reference_file_ids: list[str] | None = None,
        num_images: int = 1,
        is_editing: bool = False,
    ) -> list[str]:
        """
        Генерирует изображения через LLM с multimodal output.

        Args:
            prompt: Текстовое описание для генерации
            reference_file_ids: ID файлов-референсов
            num_images: Количество изображений
            is_editing: Режим редактирования

        Returns:
            Список file_id сгенерированных изображений
        """
        logger.info(f"Генерация {num_images} изображений через LLM: {prompt[:50]}...")

        parts: list[Part] = []

        if is_editing and reference_file_ids:
            parts.append(Part(root=TextPart(text="""CRITICAL: PHOTO EDITING TASK - ABSOLUTE PROHIBITION ON GENERATION

**YOU ARE FORBIDDEN FROM:**
- Generating a NEW person (different face, body, identity, gender)
- Creating a NEW background or scene
- Generating a NEW image from scratch

**YOU MUST:**
- EDIT the EXISTING BASE IMAGE (Image #1) ONLY
- PRESERVE the EXACT person, face, body, pose, background
- ADD the product to the EXISTING person in the BASE IMAGE""")))

        if reference_file_ids:
            logger.info(f"Добавляем {len(reference_file_ids)} референсных изображений")

            for idx, file_id in enumerate(reference_file_ids):
                file_key = f"file:{file_id}"
                file_data_json = await self._storage.get(file_key)

                if not file_data_json:
                    logger.warning(f"Файл {file_id} не найден")
                    continue

                file_data = json.loads(file_data_json)
                if not isinstance(file_data, dict):
                    raise ValueError(f"Файл {file_id}: metadata must be JSON object")
                s3_bucket = file_data.get("s3_bucket")
                s3_key = file_data.get("s3_key")
                content_type = file_data.get("content_type")
                if not isinstance(s3_bucket, str) or not isinstance(s3_key, str):
                    raise ValueError(f"Файл {file_id}: некорректные S3 metadata")
                if not isinstance(content_type, str) or not content_type:
                    content_type = "image/png"

                s3_client = S3ClientFactory.create_client_for_bucket(s3_bucket)
                try:
                    file_bytes = await s3_client.download_bytes(s3_key)
                finally:
                    await s3_client.close()

                if file_bytes:
                    base64_data = base64.b64encode(file_bytes).decode('utf-8')

                    if is_editing and idx == 0:
                        parts.append(Part(root=TextPart(text="""BASE IMAGE TO EDIT (Image #1) - DO NOT GENERATE NEW IMAGE

**THIS IS THE EXISTING PHOTOGRAPH - YOU MUST EDIT IT, NOT REPLACE IT**""")))

                    parts.append(Part(root=FilePart(file=FileWithBytes(
                        bytes=base64_data,
                        mime_type=content_type,
                        name=file_id,
                    ))))

                    logger.info(f"Добавлено изображение {file_id} (индекс {idx})")

        parts.append(Part(root=TextPart(text=prompt)))

        llm = self._get_llm()

        response = await llm.chat([
            Message(
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=parts,
            )
        ])

        file_pattern = r'file_([a-f0-9]{12})'
        file_ids = re.findall(file_pattern, get_message_text(response))
        file_ids = [f"file_{fid}" for fid in file_ids]

        if file_ids:
            logger.info(f"Сгенерировано {len(file_ids)} изображений: {file_ids}")
        else:
            logger.warning("Не удалось найти file_id в ответе LLM")

        return file_ids

class NanoBananaClientFactory:
    """Фабрика для создания Nano Banana клиентов"""

    @staticmethod
    def create_client(storage: "Storage") -> NanoBananaClient:
        """Создает клиент на основе конфигурации"""
        settings = get_settings()

        if not settings.nano_banana.enabled:
            raise ValueError("Nano Banana не настроен в конфигурации")

        return NanoBananaClient(
            storage=storage,
            model_name=settings.nano_banana.model_name,
            timeout=settings.nano_banana.timeout,
        )
