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
import hashlib
import json
import re

from pydantic import TypeAdapter

from apps.idle.tasks.task_names import TASK_A2A_CALL_FINISHED
from apps.shop.config import ShopSettings
from apps.shop.models.api import ShopAiMenuItem, ShopAiOptionSuggestion
from core.a2a.pending_call import PendingCallStatus, PlatformA2APendingCall
from core.a2a.submit import A2ACallPending, a2a_resume_nonce, submit_a2a_call
from core.clients.a2a_client import A2AClient, A2ATaskResult
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
_BRANCH_GENERATE_LOGO = "generate_logo"
_BRANCH_PARSE_MENU = "parse_menu"


class ShopAiService:
    """AI-операции магазина через ветки компанийского flow ``shop`` по A2A."""

    def __init__(self, settings: ShopSettings) -> None:
        self._a2a: A2AClient = A2AClient()
        self._deadline_seconds: float = settings.ai_a2a_deadline_seconds

    async def _flow_task(
        self,
        branch_id: str,
        *,
        company_id: str,
        user_id: str,
        content: str,
        variables: JsonObject,
        parts: list[JsonObject] | None = None,
    ) -> A2ATaskResult:
        """Вызов ветки flow ``shop`` без синхронного ожидания.

        Resolved payload обслуживается из pending-ряда по ``dedup_key`` (re-run
        ``shop_ai_call`` после webhook-resume); нет строки — ``submit_a2a_call``
        регистрирует pending + SendMessage с push config и поднимает
        ``A2ACallPending``. Ожидания/опроса нет никогда.
        """
        nonce = a2a_resume_nonce()
        if nonce is None:
            raise PlatformUnavailableError(
                "ai flow call outside A2A resume context", error_code="ai_upstream"
            )
        fragment = hashlib.sha1(
            json.dumps(
                {
                    "branch": branch_id,
                    "content": content,
                    "variables": variables,
                    "files": [p.get("filename") for p in parts or []],
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:16]
        dedup_key = f"shop:ai:{fragment}:{nonce}"
        row = await PlatformA2APendingCall.latest_by_dedup_key_created_at_desc("shop", dedup_key)
        if row is not None:
            if row.result_payload is not None:
                return self._result_from_stored_payload(row.result_payload)
            if row.status is PendingCallStatus.pending:
                raise A2ACallPending(row.a2a_task_id)
            raise PlatformUnavailableError(
                "ai flow task failed", error_code="ai_upstream"
            )
        flows_base_url = get_settings().server.get_flows_service_url().rstrip("/")
        row = await submit_a2a_call(
            a2a_client=self._a2a,
            service="shop",
            company_id=company_id,
            user_id=user_id,
            base_url=f"{flows_base_url}/flows/api/v1/{_FLOW_ID}",
            content=content,
            branch_id=branch_id,
            continuation=TASK_A2A_CALL_FINISHED,
            continuation_kwargs={},
            deadline_seconds=self._deadline_seconds,
            parts=parts,
            metadata={"variables": variables},
            dedup_key=dedup_key,
        )
        raise A2ACallPending(row.a2a_task_id)

    @staticmethod
    def _result_from_stored_payload(payload: JsonObject) -> A2ATaskResult:
        """A2ATaskResult из stored webhook-результата (status/response/artifacts/task)."""
        status = payload.get("status")
        if status != "completed":
            raise PlatformUnavailableError(
                f"ai flow task ended with status {status!r}",
                error_code="ai_upstream",
            )
        task = payload.get("task")
        artifacts_value = payload.get("artifacts")
        artifacts: list[JsonObject] = (
            [
                require_json_object(item, "a2a.payload.artifacts[]")
                for item in artifacts_value
            ]
            if isinstance(artifacts_value, list)
            else []
        )
        response_text = payload.get("response")
        return A2ATaskResult(
            task=(
                require_json_object(task, "a2a.payload.task")
                if isinstance(task, dict)
                else {}
            ),
            artifacts=artifacts,
            status="completed",
            response=response_text if isinstance(response_text, str) else "",
            raw={},
        )

    async def _flow_text(
        self,
        branch_id: str,
        *,
        company_id: str,
        user_id: str,
        content: str,
        variables: JsonObject,
        parts: list[JsonObject] | None = None,
    ) -> str:
        """Вызов ветки flow и извлечение текста ответа."""
        response = await self._flow_task(
            branch_id,
            company_id=company_id,
            user_id=user_id,
            content=content,
            variables=variables,
            parts=parts,
        )
        text = response.response.strip()
        if not text:
            raise PlatformNotFoundError("ai returned empty result", error_code="ai_empty_result")
        return text

    async def _flow_json(
        self,
        branch_id: str,
        *,
        company_id: str,
        user_id: str,
        content: str,
        variables: JsonObject,
        parts: list[JsonObject] | None = None,
    ) -> JsonObject:
        """Вызов ветки flow и извлечение structured output: data-парты artifacts/history, затем JSON из текста."""
        response = await self._flow_task(
            branch_id,
            company_id=company_id,
            user_id=user_id,
            content=content,
            variables=variables,
            parts=parts,
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
        company_id: str,
        user_id: str,
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
                company_id=company_id,
                user_id=user_id,
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
                company_id=company_id,
                user_id=user_id,
                content=f"Опиши блюдо «{name}»",
                variables=variables,
            )
        return text.strip('"').strip()[:500]

    async def suggest_options(
        self,
        *,
        company_id: str,
        user_id: str,
        product_name: str,
        group_name: str | None = None,
    ) -> list[ShopAiOptionSuggestion]:
        """Опции-модификаторы к блюду: ветка ``suggest_options`` (structured output)."""
        variables: JsonObject = {"product_name": product_name}
        if group_name:
            variables["group_name"] = group_name
        payload = await self._flow_json(
            _BRANCH_SUGGEST_OPTIONS,
            company_id=company_id,
            user_id=user_id,
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
        company_id: str,
        user_id: str,
        content: str,
        variables: JsonObject,
        parts: list[JsonObject] | None = None,
    ) -> str:
        """Ветка image_gen: разбор ``{"file_ids": [...]}`` из structured/text ответа."""
        payload = await self._flow_json(
            branch_id,
            company_id=company_id,
            user_id=user_id,
            content=content,
            variables=variables,
            parts=parts,
        )
        file_ids_raw = payload.get("file_ids")
        if not isinstance(file_ids_raw, list) or not file_ids_raw:
            raise PlatformNotFoundError("ai returned no image", error_code="ai_empty_result")
        file_id = file_ids_raw[0]
        if not isinstance(file_id, str) or not file_id.strip():
            raise PlatformNotFoundError("ai returned no image", error_code="ai_empty_result")
        return file_id

    async def enhance_product_photo(
        self, *, company_id: str, user_id: str, file_id: str
    ) -> str:
        """Улучшение фото блюда: ветка ``enhance_photo`` (image_gen с референсом) → file_id."""
        return await self._flow_file_id(
            _BRANCH_ENHANCE_PHOTO,
            company_id=company_id,
            user_id=user_id,
            content="Улучши фотографию для витрины",
            variables={},
            parts=[
                {"text": "Улучши фотографию для витрины"},
                await self._read_file_part(file_id),
            ],
        )

    async def generate_product_photo(
        self, *, company_id: str, user_id: str, name: str, description: str = ""
    ) -> str:
        """Генерация фото товара с нуля: ветка ``generate_photo`` (image_gen) → file_id."""
        variables: JsonObject = {"product_name": name}
        if description:
            variables["description"] = description
        return await self._flow_file_id(
            _BRANCH_GENERATE_PHOTO,
            company_id=company_id,
            user_id=user_id,
            content=f"Сгенерируй фотографию «{name}»",
            variables=variables,
        )

    async def parse_menu(
        self, *, company_id: str, user_id: str, text: str
    ) -> list[ShopAiMenuItem]:
        """Разбор свободного текста меню: ветка ``parse_menu`` (structured output)."""
        payload = await self._flow_json(
            _BRANCH_PARSE_MENU,
            company_id=company_id,
            user_id=user_id,
            content=text,
            variables={},
        )
        items_raw = payload.get("items")
        if not isinstance(items_raw, list) or not items_raw:
            raise PlatformNotFoundError("ai returned empty items", error_code="ai_empty_result")
        return TypeAdapter(list[ShopAiMenuItem]).validate_python(items_raw)[:500]

    async def describe_shop(
        self,
        *,
        company_id: str,
        user_id: str,
        name: str,
        description: str = "",
        city: str = "",
    ) -> str:
        """Описание магазина для витрины: ветка ``describe_shop``."""
        variables: JsonObject = {"shop_name": name}
        if description:
            variables["description"] = description
        if city:
            variables["city"] = city
        text = await self._flow_text(
            _BRANCH_DESCRIBE_SHOP,
            company_id=company_id,
            user_id=user_id,
            content=f"Напиши описание магазина «{name}»",
            variables=variables,
        )
        return text.strip('"').strip()[:500]

    async def generate_shop_cover(
        self, *, company_id: str, user_id: str, name: str, description: str = ""
    ) -> str:
        """Генерация обложки витрины: ветка ``generate_cover`` (image_gen) → file_id."""
        variables: JsonObject = {"shop_name": name}
        if description:
            variables["description"] = description
        return await self._flow_file_id(
            _BRANCH_GENERATE_COVER,
            company_id=company_id,
            user_id=user_id,
            content=f"Сгенерируй обложку витрины «{name}»",
            variables=variables,
        )

    async def generate_shop_logo(
        self, *, company_id: str, user_id: str, name: str, description: str = ""
    ) -> str:
        """Генерация логотипа магазина: ветка ``generate_logo`` (image_gen) → file_id."""
        variables: JsonObject = {"shop_name": name}
        if description:
            variables["description"] = description
        return await self._flow_file_id(
            _BRANCH_GENERATE_LOGO,
            company_id=company_id,
            user_id=user_id,
            content=f"Сгенерируй логотип «{name}»",
            variables=variables,
        )
