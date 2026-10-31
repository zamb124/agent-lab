"""AI-функции shop: все операции — ветки компанийского flow ``shop`` по A2A.

Промпты и схемы живут в bundle ``apps/flows/bundles/shop`` и редактируются на
компанию во flow-редакторе — в коде промптов нет. Сервис передаёт только
структурированные variables (A2A metadata) и файлы (Part.raw → state.files):
``describe_photo`` — vision-описание по фото, ``enhance_photo`` и
``generate_photo`` — image_gen ноды (референсы из state.files, ответ
``{"file_ids": [...]}``).
"""

from __future__ import annotations

import base64
import re

from pydantic import TypeAdapter

from apps.shop.config import ShopSettings
from apps.shop.models.api import ShopAiOptionSuggestion
from core.clients.a2a_client import A2AClient, A2AClientError, A2ATaskResult
from core.config import get_settings
from core.errors.boundary import PlatformNotFoundError, PlatformUnavailableError
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.logging import get_logger
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_FLOW_ID = "shop"
_BRANCH_DESCRIBE = "describe"
_BRANCH_DESCRIBE_PHOTO = "describe_photo"
_BRANCH_SUGGEST_OPTIONS = "suggest_options"
_BRANCH_ENHANCE_PHOTO = "enhance_photo"
_BRANCH_GENERATE_PHOTO = "generate_photo"
_BRANCH_DESCRIBE_SHOP = "describe_shop"
_BRANCH_GENERATE_COVER = "generate_cover"


class ShopAiService:
    """AI-операции магазина через ветки компанийского flow ``shop`` по A2A."""

    def __init__(self, settings: ShopSettings) -> None:
        self._a2a: A2AClient = A2AClient(timeout=settings.ai_a2a_timeout_seconds)

    async def _flow_task(
        self,
        branch_id: str,
        *,
        content: str,
        variables: JsonObject,
        parts: list[JsonObject] | None = None,
    ) -> A2ATaskResult:
        """Вызов ветки flow ``shop``: variables через metadata, файлы — Part.raw."""
        flows_base_url = get_settings().server.get_flows_service_url().rstrip("/")
        try:
            return await self._a2a.send_task(
                base_url=f"{flows_base_url}/flows/api/v1/{_FLOW_ID}",
                content=content,
                branch_id=branch_id,
                metadata={"variables": variables},
                timeout=self._a2a.timeout,
                parts=parts,
            )
        except A2AClientError as exc:
            raise PlatformUnavailableError(
                f"ai flow task failed: {exc}", error_code="ai_upstream"
            ) from exc

    async def _flow_text(
        self,
        branch_id: str,
        *,
        content: str,
        variables: JsonObject,
        parts: list[JsonObject] | None = None,
    ) -> str:
        """Вызов ветки flow и извлечение текста ответа."""
        response = await self._flow_task(
            branch_id, content=content, variables=variables, parts=parts
        )
        text = response.response.strip()
        if not text:
            raise PlatformNotFoundError("ai returned empty result", error_code="ai_empty_result")
        return text

    async def _flow_json(
        self,
        branch_id: str,
        *,
        content: str,
        variables: JsonObject,
        parts: list[JsonObject] | None = None,
    ) -> JsonObject:
        """Вызов ветки flow и извлечение structured output: data-парты artifacts/history, затем JSON из текста."""
        response = await self._flow_task(
            branch_id, content=content, variables=variables, parts=parts
        )

        def _data_from_parts(parts_raw: JsonValue) -> list[JsonObject]:
            if not isinstance(parts_raw, list):
                return []
            found: list[JsonObject] = []
            for item in parts_raw:
                if not isinstance(item, dict):
                    continue
                part = require_json_object(item, "a2a.part")
                data = part.get("data")
                if isinstance(data, dict):
                    found.append(TypeAdapter(JsonObject).validate_python(data))
            return found

        candidates: list[JsonObject] = []
        history = response.task.get("history")
        if isinstance(history, list):
            for message in history:
                if isinstance(message, dict):
                    candidates.extend(_data_from_parts(message.get("parts")))
        for artifact in response.artifacts:
            candidates.extend(_data_from_parts(artifact.get("parts")))

        # Data-part {"content": "<json/text>"} — обёртка текстового артефакта:
        # внутренний JSON-объект приоритетнее самой обёртки.
        for candidate in candidates:
            inner = candidate.get("content")
            if isinstance(inner, str):
                match = _JSON_OBJECT_RE.search(inner)
                if match is not None:
                    try:
                        return TypeAdapter(JsonObject).validate_json(match.group(0))
                    except Exception:
                        continue
        if candidates:
            return candidates[0]
        text = response.response.strip()
        match = _JSON_OBJECT_RE.search(text)
        if match is not None:
            return TypeAdapter(JsonObject).validate_json(match.group(0))
        raise PlatformNotFoundError(
            "ai returned no structured payload", error_code="ai_empty_result"
        )

    async def _read_file_part(self, file_id: str) -> JsonObject:
        """Байты файла как A2A Part.raw (base64 на проводе) для передачи в flow."""
        record = await FileRecord.get(file_id)
        if record is None:
            raise PlatformNotFoundError("file not found", error_code="file_not_found")
        handle = await FileGate().open_record(
            record, SystemPrincipal(company_id=record.company_id or "")
        )
        data = await handle.read_bytes()
        if not data:
            raise PlatformNotFoundError("file empty", error_code="file_not_found")
        return {
            "raw": base64.b64encode(data).decode("ascii"),
            "mediaType": record.content_type,
            "filename": file_id,
        }

    async def describe_product(
        self,
        *,
        name: str,
        category_name: str | None = None,
        photo_file_id: str | None = None,
    ) -> str:
        """Описание блюда: ветка ``describe``; по фото — vision-ветка ``describe_photo``."""
        variables: JsonObject = {"product_name": name}
        if category_name:
            variables["category_name"] = category_name
        if photo_file_id:
            text = await self._flow_text(
                _BRANCH_DESCRIBE_PHOTO,
                content=f"Опиши блюдо «{name}» по фотографии",
                variables=variables,
                parts=[
                    {"text": f"Опиши блюдо «{name}» по фотографии"},
                    await self._read_file_part(photo_file_id),
                ],
            )
        else:
            text = await self._flow_text(
                _BRANCH_DESCRIBE,
                content=f"Опиши блюдо «{name}»",
                variables=variables,
            )
        return text.strip('"').strip()[:500]

    async def suggest_options(
        self, *, product_name: str, group_name: str | None = None
    ) -> list[ShopAiOptionSuggestion]:
        """Опции-модификаторы к блюду: ветка ``suggest_options`` (structured output)."""
        variables: JsonObject = {"product_name": product_name}
        if group_name:
            variables["group_name"] = group_name
        payload = await self._flow_json(
            _BRANCH_SUGGEST_OPTIONS,
            content=f"Предложи опции к блюду «{product_name}»",
            variables=variables,
        )
        items_raw = payload.get("options")
        if not isinstance(items_raw, list) or not items_raw:
            raise PlatformNotFoundError("ai returned empty options", error_code="ai_empty_result")
        return TypeAdapter(list[ShopAiOptionSuggestion]).validate_python(items_raw)[:20]

    async def _flow_file_id(
        self,
        branch_id: str,
        *,
        content: str,
        variables: JsonObject,
        parts: list[JsonObject] | None = None,
    ) -> str:
        """Ветка image_gen: разбор ``{"file_ids": [...]}`` из structured/text ответа."""
        payload = await self._flow_json(
            branch_id, content=content, variables=variables, parts=parts
        )
        file_ids_raw = payload.get("file_ids")
        if not isinstance(file_ids_raw, list) or not file_ids_raw:
            raise PlatformNotFoundError("ai returned no image", error_code="ai_empty_result")
        file_id = file_ids_raw[0]
        if not isinstance(file_id, str) or not file_id.strip():
            raise PlatformNotFoundError("ai returned no image", error_code="ai_empty_result")
        return file_id

    async def enhance_product_photo(self, *, file_id: str) -> str:
        """Улучшение фото блюда: ветка ``enhance_photo`` (image_gen с референсом) → file_id."""
        return await self._flow_file_id(
            _BRANCH_ENHANCE_PHOTO,
            content="Улучши фотографию для витрины",
            variables={},
            parts=[
                {"text": "Улучши фотографию для витрины"},
                await self._read_file_part(file_id),
            ],
        )

    async def generate_product_photo(self, *, name: str, description: str = "") -> str:
        """Генерация фото товара с нуля: ветка ``generate_photo`` (image_gen) → file_id."""
        variables: JsonObject = {"product_name": name}
        if description:
            variables["description"] = description
        return await self._flow_file_id(
            _BRANCH_GENERATE_PHOTO,
            content=f"Сгенерируй фотографию «{name}»",
            variables=variables,
        )

    async def describe_shop(
        self, *, name: str, description: str = "", city: str = ""
    ) -> str:
        """Описание магазина для витрины: ветка ``describe_shop``."""
        variables: JsonObject = {"shop_name": name}
        if description:
            variables["description"] = description
        if city:
            variables["city"] = city
        text = await self._flow_text(
            _BRANCH_DESCRIBE_SHOP,
            content=f"Напиши описание магазина «{name}»",
            variables=variables,
        )
        return text.strip('"').strip()[:500]

    async def generate_shop_cover(self, *, name: str, description: str = "") -> str:
        """Генерация обложки витрины: ветка ``generate_cover`` (image_gen) → file_id."""
        variables: JsonObject = {"shop_name": name}
        if description:
            variables["description"] = description
        return await self._flow_file_id(
            _BRANCH_GENERATE_COVER,
            content=f"Сгенерируй обложку витрины «{name}»",
            variables=variables,
        )
