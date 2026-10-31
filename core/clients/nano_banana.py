"""Клиент генерации изображений через platform LLM capability."""

import re
from typing import Protocol

from a2a.helpers.proto_helpers import get_message_text
from a2a.types import Message, Part, Role

from core.ai.providers import AICapability
from core.ai.resolver import resolve_ai_model
from core.ai.runtime import create_llm_client_from_ai_model
from core.clients.llm.messages import build_a2a_message
from core.config import get_settings
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.logging import get_logger

logger = get_logger(__name__)


class _ChatLLM(Protocol):
    async def chat(self, messages: list[Message]) -> Message:
        ...


class NanoBananaClient:
    """
    Клиент для генерации изображений через platform LLM capability.
    """

    def __init__(self) -> None:
        self._llm: _ChatLLM | None = None

    def _create_image_generation_client(self) -> _ChatLLM:
        """Resolve and cache the image generation LLM client."""
        if self._llm is None:
            resolved = resolve_ai_model(
                AICapability.IMAGE_GEN,
                include_platform_default=True,
            )
            if resolved is not None:
                self._llm = create_llm_client_from_ai_model(resolved)
            else:
                raise ValueError(
                    "NanoBananaClient: platform default for capability=image_gen is not configured"
                )
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

        Аргументы:
            prompt: Текстовое описание для генерации
            reference_file_ids: ID файлов-референсов
            num_images: Количество изображений
            is_editing: Режим редактирования

        Возвращает:
            Список file_id сгенерированных изображений
        """
        logger.info("image.generate.started", num_images=num_images, prompt_preview=prompt[:50])

        parts: list[Part] = []

        if is_editing and reference_file_ids:
            parts.append(Part(text="""CRITICAL: PHOTO EDITING TASK - ABSOLUTE PROHIBITION ON GENERATION

**YOU ARE FORBIDDEN FROM:**
- Generating a NEW person (different face, body, identity, gender)
- Creating a NEW background or scene
- Generating a NEW image from scratch

**YOU MUST:**
- EDIT the EXISTING BASE IMAGE (Image #1) ONLY
- PRESERVE the EXACT person, face, body, pose, background
- ADD the product to the EXISTING person in the BASE IMAGE"""))

        if reference_file_ids:
            logger.info("image.generate.references", count=len(reference_file_ids))

            for idx, file_id in enumerate(reference_file_ids):
                file_record = await FileRecord.get(file_id)

                if file_record is None:
                    logger.warning("image.generate.file_missing", file_id=file_id)
                    continue

                if file_record.company_id is None or file_record.company_id == "":
                    logger.warning("image.generate.file_missing_company", file_id=file_id)
                    continue
                handle = await FileGate().open_record(
                    file_record,
                    SystemPrincipal(company_id=file_record.company_id),
                )
                file_bytes = await handle.read_bytes()

                if file_bytes:
                    if is_editing and idx == 0:
                        parts.append(Part(text="""BASE IMAGE TO EDIT (Image #1) - DO NOT GENERATE NEW IMAGE

**THIS IS THE EXISTING PHOTOGRAPH - YOU MUST EDIT IT, NOT REPLACE IT**"""))

                    parts.append(
                        Part(
                            raw=file_bytes,
                            media_type=file_record.content_type,
                            filename=file_id,
                        )
                    )

                    logger.info("image.generate.reference_added", file_id=file_id, index=idx)

        parts.append(Part(text=prompt))

        llm = self._create_image_generation_client()

        response = await llm.chat(
            [
                build_a2a_message(
                    role=Role.ROLE_USER,
                    parts=parts,
                )
            ]
        )

        file_pattern: re.Pattern[str] = re.compile(r"file_([a-f0-9]{12})")
        file_ids: list[str] = []
        for file_match in file_pattern.finditer(get_message_text(response)):
            file_ids.append(f"file_{file_match.group(1)}")

        if file_ids:
            logger.info("image.generate.completed", file_ids=file_ids, count=len(file_ids))
        else:
            logger.warning("clients.file_id.llm")

        return file_ids

class NanoBananaClientFactory:
    """Фабрика для создания Nano Banana клиентов"""

    @staticmethod
    def create_client() -> NanoBananaClient:
        """Создает клиент на основе конфигурации"""
        settings = get_settings()

        if not settings.nano_banana.enabled:
            raise ValueError("Nano Banana is not configured")

        return NanoBananaClient()
