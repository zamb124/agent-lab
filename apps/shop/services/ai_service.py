"""AI-функции shop поверх канонического AI-рантайма платформы.

Никаких собственных LLM-клиентов: описания — `chat_for_capability`
(`LLM_VISION` при наличии фото, иначе `LLM_CHAT`), улучшение и генерация
фото — `NanoBananaClient` (capability `IMAGE_GEN`). Биллинг и pre-flight
баланса живут внутри platform-клиентов.
"""

from __future__ import annotations

from a2a.helpers.proto_helpers import get_message_text
from a2a.types import Part, Role

from core.ai.providers import AICapability
from core.ai.runtime import chat_for_capability
from core.clients.llm.messages import build_a2a_message
from core.clients.nano_banana import NanoBananaClient
from core.db.storage import SharedStorage
from core.errors.boundary import PlatformNotFoundError
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.logging import get_logger

logger = get_logger(__name__)

_DESCRIBE_PROMPT = """Ты копирайтер ресторанного меню. Напиши аппетитное описание блюда
«{name}»{category_hint} на русском языке.

Требования:
- 1-2 предложения, до 160 символов
- подчёркивает вкус и подачу, без канцелярита
- без цены, без эмодзи, без кавычек
- только текст описания, ничего больше"""

_ENHANCE_PROMPT = """Enhance this food/product photo for a restaurant menu storefront:
improve lighting, color grading and sharpness, make the dish look appetising.
Keep the exact same dish, plating and composition. Photorealistic, menu-grade."""

_GENERATE_PROMPT = """Professional menu photograph of «{name}»{desc_hint}:
appetising, well-lit, shallow depth of field, restaurant-grade food styling,
clean background, photorealistic, square composition."""


class ShopAiService:
    """AI-операции магазина: описания и фото товаров."""

    def __init__(self, shared_storage: SharedStorage) -> None:
        self._storage: SharedStorage = shared_storage
        self._images: NanoBananaClient = NanoBananaClient(storage=shared_storage)

    async def _read_file_part(self, file_id: str) -> Part:
        raw = await self._storage.get(f"file:{file_id}")
        if not raw:
            raise PlatformNotFoundError(
                "file not found", error_code="file_not_found"
            )
        record = FileRecord.model_validate_json(raw)
        handle = await FileGate().open_record(
            record, SystemPrincipal(company_id=record.company_id or "")
        )
        data = await handle.read_bytes()
        if not data:
            raise PlatformNotFoundError(
                "file empty", error_code="file_not_found"
            )
        return Part(raw=data, media_type=record.content_type, filename=file_id)

    async def describe_product(
        self,
        *,
        name: str,
        category_name: str | None = None,
        photo_file_id: str | None = None,
    ) -> str:
        """Описание блюда: по названию, а при наличии фото — vision по снимку."""
        category_hint = f" в категории «{category_name}»" if category_name else ""
        prompt = _DESCRIBE_PROMPT.format(name=name, category_hint=category_hint)
        parts: list[Part] = [Part(text=prompt)]
        capability = AICapability.LLM_CHAT
        if photo_file_id:
            parts.append(await self._read_file_part(photo_file_id))
            capability = AICapability.LLM_VISION
        response = await chat_for_capability(
            capability,
            [build_a2a_message(role=Role.ROLE_USER, parts=parts)],
        )
        text = get_message_text(response).strip().strip('"').strip()
        if not text:
            raise PlatformNotFoundError(
                "ai returned empty description", error_code="ai_empty_result"
            )
        return text[:500]

    async def enhance_product_photo(self, *, file_id: str) -> str:
        """Улучшение фото блюда через image_gen — возвращает новый file_id."""
        file_ids = await self._images.generate_images(
            prompt=_ENHANCE_PROMPT,
            reference_file_ids=[file_id],
            num_images=1,
            is_editing=True,
        )
        if not file_ids:
            raise PlatformNotFoundError(
                "ai returned no image", error_code="ai_empty_result"
            )
        return file_ids[0]

    async def generate_product_photo(
        self, *, name: str, description: str = ""
    ) -> str:
        """Генерация фото товара с нуля — возвращает file_id."""
        desc_hint = f" — {description}" if description else ""
        file_ids = await self._images.generate_images(
            prompt=_GENERATE_PROMPT.format(name=name, desc_hint=desc_hint),
            num_images=1,
        )
        if not file_ids:
            raise PlatformNotFoundError(
                "ai returned no image", error_code="ai_empty_result"
            )
        return file_ids[0]
