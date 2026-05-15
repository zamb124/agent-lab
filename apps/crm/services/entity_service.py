"""
Сервис для работы с entities.

Единый сервис для всех типов entities (note, task, contact, organization, etc).
Включает AI анализ с составными промптами и каскадное удаление через Saga.
"""

import asyncio
import json
import re
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, UTC
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.crm.constants_graph import (
    COMPANY_ENTITY_TYPE,
    IN_CONTEXT_RELATIONSHIP_TYPE,
    NOTE_ROOT_ENTITY_TYPE_ID,
    NOTE_VOICE_RELATIONSHIP_TYPE,
    PLATFORM_COMPANY_ID_ATTR,
    PLATFORM_USER_ID_ATTR,
)
from apps.crm.db.models import CRMEntity, CRMTask, EntityType, Relationship, RelationshipType
from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
from apps.crm.db.repositories.access_request_repository import AccessRequestRepository
from apps.crm.db.repositories.company_mapping_repository import CompanyMappingRepository
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.models.api import (
    AIAnalysisDraftApplyResult,
    AIAnalysisDraftPatchRequest,
    AIAnalysisDraftRepairFlowResult,
    AIAnalysisDraftStored,
    AIAnalysisRelationshipDraft,
    AIAnalyzeRelationshipExtracted,
    AIAnalyzeRequest,
    AIAnalyzeResponse,
    AIExtractedEntity,
    DeduplicateResult,
    DraftEntityPatch,
    EntityMergeRequest,
)
from apps.crm.services.attachment_service import AttachmentService
from apps.crm.services.crm_note_ws_broadcast import broadcast_crm_note_event
from apps.crm.services.crm_summary_ws_broadcast import (
    broadcast_crm_daily_summary_updated,
    broadcast_crm_period_summary_updated,
)
from apps.crm.services.daily_summary_artifact_service import DailySummaryArtifactService
from apps.crm.services.daily_summary_cache_service import DailySummaryCacheService
from apps.crm.services.entity_response_enrichment import build_entity_responses_with_semantic_index
from apps.crm.services.file_text_reader import load_text_and_name_from_stored_file_id
from apps.crm.services.note_attachment_description import (
    ATTACHMENT_SUMMARIZE_CHUNK_MAX_CHARS,
    ATTACHMENT_SUMMARIZE_MERGE_PASS_THRESHOLD_CHARS,
    merge_attachment_extracted_into_description,
    split_text_into_summarize_chunks,
    truncate_attachment_text_for_note,
)
from apps.crm.services.saga import EntityDeletionSaga, SagaStep
from apps.crm.services.user_person_service import UserPersonService
from core.clients.a2a_client import A2AClient
from core.context import get_context
from core.db.repositories.namespace_repository import NamespaceRepository
from core.logging import get_logger
from core.models.i18n_models import Language
from core.models.identity_models import Namespace, NamespaceCRMSettings

logger = get_logger(__name__)
from apps.crm.config import get_crm_settings  # noqa: E402
from apps.crm.services.task_board_presets import (  # noqa: E402
    resolve_allowed_task_status_ids,
    resolve_task_board_stages,
    task_board_key,
)
from core.config import get_settings  # noqa: E402
from core.utils.chunked_async import map_reduce_tree, run_chunked_map  # noqa: E402

if TYPE_CHECKING:
    from apps.crm.services.access_control_service import AccessControlService
    from core.db.repositories.company_repository import CompanyRepository

_ANALYZE_ENTITY_DESCRIPTION_MIN_LEN = 12

_AI_NOTE_ANALYSIS_ERROR_MAX_LEN = 8000

_RESOLVED_NOTE_NEIGHBOR_REL_TYPES: frozenset[str] = frozenset(
    {
        "linked",
        "mentions",
        IN_CONTEXT_RELATIONSHIP_TYPE,
        NOTE_VOICE_RELATIONSHIP_TYPE,
    }
)

SUMMARY_ALL_NAMESPACES_TASK_KEY = "__all_namespaces__"
_DAILY_SUMMARY_CARD_SNIPPET_MAX = 500

_INTERFACE_LANGUAGE_NAMES_RU: dict[str, str] = {
    Language.RU.value: "русском",
    Language.EN.value: "английском",
}


def _crm_llm_interface_language_vars() -> dict[str, str]:
    ctx = get_context()
    if ctx is None:
        raise ValueError("Контекст не задан: для CRM LLM нужен Context с языком интерфейса")
    code = ctx.language.value
    if code not in _INTERFACE_LANGUAGE_NAMES_RU:
        raise ValueError(f"Неподдерживаемый язык интерфейса для CRM LLM: {code!r}")
    return {
        "interface_language_code": code,
        "interface_language_name": _INTERFACE_LANGUAGE_NAMES_RU[code],
    }


def _iter_iso_dates_inclusive(date_from: str, date_to: str) -> list[str]:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    if end < start:
        raise ValueError("date_to must be >= date_from")
    out: list[str] = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _clamp_period_dates_for_summary(
    date_from: str, date_to: str, max_days: int
) -> tuple[str, str, bool]:
    """
    Оставляет не более max_days последних дней интервала (усечение с начала периода).
    """
    days = _iter_iso_dates_inclusive(date_from, date_to)
    if len(days) <= max_days:
        return date_from, date_to, False
    tail = days[-max_days:]
    return tail[0], tail[-1], True


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


ANALYSIS_DRAFT_APPLY_MAX_ROUNDS = 3

_MERGE_SCALAR_KEYS: tuple[str, ...] = (
    "name",
    "description",
    "status",
    "entity_subtype",
    "priority",
    "note_date",
    "due_date",
)


class DraftVersionConflictError(ValueError):
    """Ожидаемая версия черновика не совпадает с сохранённой в заметке."""


class ApplyAnalysisDraftEntityFailuresError(Exception):
    """После всех раундов ретраев часть строк черновика не сохранилась."""

    def __init__(
        self,
        failures: list[tuple[str, str | None, str | None, str]],
    ) -> None:
        """
        failures: (draft_entity_id, name, entity_type, сообщение об ошибке)
        """
        self.failures = failures
        parts = [
            f"draft_entity_id={did} name={name!r} type={etype!r}: {msg}"
            for did, name, etype, msg in failures
        ]
        super().__init__("Не удалось применить строки черновика: " + "; ".join(parts))


class SchemaValidationError(ValueError):
    """Атрибуты сущности не соответствуют required_fields / типам из EntityType."""

    def __init__(self, field_errors: list[dict[str, str]]) -> None:
        self.field_errors = field_errors
        parts = [f"{e['field']}: {e['error']}" for e in field_errors]
        super().__init__("Schema validation failed: " + ", ".join(parts))


def _extract_entity_type_fields(entity_type) -> list[dict[str, Any]]:
    """Собирает список полей сущности с описанием для передачи в LLM."""
    result: list[dict[str, Any]] = []
    schemas: list[tuple[dict[str, Any], bool]] = [
        (entity_type.required_fields or {}, True),
        (entity_type.optional_fields or {}, False),
    ]
    for schema, required in schemas:
        if not isinstance(schema, dict):
            continue
        for name, defn in schema.items():
            if not isinstance(defn, dict):
                continue
            field: dict[str, Any] = {
                "name": name,
                "label": defn.get("label", name),
                "required": required,
            }
            description = defn.get("description")
            if description:
                field["description"] = description
            json_type = defn.get("type")
            if isinstance(json_type, str) and json_type.strip():
                field["type"] = json_type.strip()
            if defn.get("type") == "enum" and isinstance(defn.get("values"), list):
                field["values"] = defn["values"]
            result.append(field)
    return result


class _AnalyzePipelineState(BaseModel):
    """Промежуточное состояние analyze до выдачи draft-id связям (только сервис)."""

    model_config = ConfigDict(extra="forbid")

    note: AIExtractedEntity | None = None
    entities: list[AIExtractedEntity] = Field(default_factory=list)
    relationships_extracted: list[AIAnalyzeRelationshipExtracted] = Field(default_factory=list)
    attachment_summaries: list[dict[str, Any]] = Field(default_factory=list)


_DRAFT_ONLY_ENTITY_ATTR_KEYS: frozenset[str] = frozenset({"platform_ai_draft_task_completed"})


def _strip_draft_only_entity_attrs(attrs: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(attrs or {})
    for k in _DRAFT_ONLY_ENTITY_ATTR_KEYS:
        out.pop(k, None)
    return out


class EntityService:
    """
    Сервис для работы с entities в CRM.

    Основные функции:
    - CRUD operations для любого типа entity
    - AI анализ текста с составными промптами
    - Извлечение entities и relationships
    - Каскадное удаление через Saga pattern
    """

    def __init__(
        self,
        entity_repo: EntityRepository,
        entity_type_repo: EntityTypeRepository,
        relationship_type_repo: RelationshipTypeRepository,
        relationship_repo: RelationshipRepository,
        namespace_repo: NamespaceRepository,
        attachment_service: AttachmentService,
        a2a_client: A2AClient,
        daily_summary_cache_service: DailySummaryCacheService,
        daily_summary_artifact_service: DailySummaryArtifactService,
        user_person_service: UserPersonService,
        access_grant_repo: AccessGrantRepository,
        access_request_repo: AccessRequestRepository,
        company_mapping_repo: CompanyMappingRepository,
        company_repo: "CompanyRepository",
        access_control: "AccessControlService",
        task_repository: TaskRepository | None = None,
        note_markdown_format_scheduler: Callable[..., Awaitable[bool]] | None = None,
    ):
        self._entity_repo = entity_repo
        self._entity_type_repo = entity_type_repo
        self._relationship_type_repo = relationship_type_repo
        self._relationship_repo = relationship_repo
        self._namespace_repo = namespace_repo
        self._attachment_service = attachment_service
        self._a2a_client = a2a_client
        self._daily_summary_cache_service = daily_summary_cache_service
        self._daily_summary_artifact_service = daily_summary_artifact_service
        self._user_person_service = user_person_service
        self._access_grant_repo = access_grant_repo
        self._access_request_repo = access_request_repo
        self._company_mapping_repo = company_mapping_repo
        self._company_repo = company_repo
        self._access_control = access_control
        self._task_repository = task_repository
        self._note_markdown_format_scheduler = note_markdown_format_scheduler

    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id

    @staticmethod
    def _get_user_id() -> str:
        context = get_context()
        if not context or not context.user:
            raise ValueError("Нет пользователя в контексте")
        return str(context.user.user_id)

    async def _tenant_company_entity_ids(self) -> frozenset[str]:
        """ID CRM-сущностей компании-тенанта (атрибут platform_company_id)."""
        company_id = self._get_company_id()
        rows = await self._entity_repo.find_by_attribute(
            entity_type=COMPANY_ENTITY_TYPE,
            attribute_key=PLATFORM_COMPANY_ID_ATTR,
            attribute_value=company_id,
            company_id=company_id,
        )
        return frozenset(row.entity_id for row in rows)

    @staticmethod
    def _normalize_namespace(namespace: str | None) -> str | None:
        if namespace is None:
            return None
        if namespace.strip() == "":
            return None
        return namespace

    @staticmethod
    def _resolve_namespace_for_write(namespace: str | None) -> str:
        normalized = EntityService._normalize_namespace(namespace)
        if normalized is None:
            return "default"
        return normalized

    async def _ensure_namespace_exists(self, namespace: str) -> None:
        existing_namespace = await self._namespace_repo.get(namespace)
        if existing_namespace is None and namespace == "default":
            context = get_context()
            if context is None or context.active_company is None:
                raise ValueError("Нет активной компании в контексте")
            default_namespace = Namespace(
                name="default",
                company_id=context.active_company.company_id,
                description="Основное пространство",
                is_default=True,
            )
            await self._namespace_repo.set(default_namespace)
            existing_namespace = await self._namespace_repo.get(namespace)
        if existing_namespace is None:
            raise ValueError(f"Namespace not found: {namespace}")

    async def _ensure_entity_type_allowed_in_namespace(
        self,
        entity_type: str,
        namespace: str,
        entity_subtype: str | None = None,
    ) -> None:
        if entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            sub_clean = entity_subtype.strip() if isinstance(entity_subtype, str) else ""
            if sub_clean == "":
                return

        entity_type_model = await self._entity_type_repo.get_by_type_id(
            entity_type,
            namespace=namespace,
        )
        if entity_type_model is None:
            raise ValueError(f"Entity type not found: {entity_type}")

        sub_clean = entity_subtype.strip() if isinstance(entity_subtype, str) else ""
        if sub_clean:
            subtype_model = await self._entity_type_repo.get_by_type_id(
                sub_clean,
                namespace=namespace,
            )
            if subtype_model is None:
                raise ValueError(f"Entity subtype not found: {sub_clean}")

    async def _validate_entity_attributes(
        self,
        entity_type: str,
        attributes: dict[str, Any],
        namespace: str,
        entity_subtype: str | None = None,
    ) -> None:
        """Проверяет attributes сущности на соответствие required_fields / optional_fields типа.

        Перед проверкой приводит значения полей с type integer/number из строковой формы,
        если это однозначно (типичный вывод LLM).
        """
        type_id = entity_subtype or entity_type
        entity_type_model = await self._entity_type_repo.get_by_type_id(
            type_id,
            namespace=namespace,
        )
        if entity_type_model is None:
            raise ValueError(f"Entity type not found: {type_id}")

        required = entity_type_model.required_fields or {}
        optional = entity_type_model.optional_fields or {}

        def _field_spec(field_name: str) -> dict[str, Any] | None:
            req = required.get(field_name)
            if isinstance(req, dict):
                return req
            opt = optional.get(field_name)
            if isinstance(opt, dict):
                return opt
            return None

        for attr_key in list(attributes.keys()):
            val = attributes.get(attr_key)
            if val is None:
                continue
            spec = _field_spec(attr_key)
            if spec is None:
                continue
            expected_type_raw = spec.get("type")
            if not isinstance(expected_type_raw, str):
                continue
            expected_type = expected_type_raw.strip()
            if not expected_type:
                continue
            attributes[attr_key] = self._coerce_attribute_value_for_schema(val, expected_type)

        if not required:
            return

        errors: list[dict[str, str]] = []
        for field_name, field_spec in required.items():
            if field_name not in attributes or attributes[field_name] is None:
                errors.append({"field": field_name, "error": "required"})
                continue
            expected_type = field_spec.get("type") if isinstance(field_spec, dict) else None
            if expected_type:
                value = attributes[field_name]
                type_valid = self._check_field_type(value, expected_type)
                if not type_valid:
                    errors.append({"field": field_name, "error": f"expected type {expected_type}"})

        if errors:
            raise SchemaValidationError(errors)

    async def _validate_task_entity_board_status(
        self,
        *,
        namespace: str,
        entity_subtype: str | None,
        attributes: dict[str, Any],
    ) -> None:
        crm = await self._load_namespace_crm_settings(namespace)
        key = task_board_key("task", entity_subtype)
        allowed = resolve_allowed_task_status_ids(crm, key)
        st = attributes.get("status")
        if st is None:
            return
        if not isinstance(st, str):
            raise ValueError("attributes.status для задачи должен быть строкой")
        st_clean = st.strip()
        if st_clean not in allowed:
            raise ValueError(f"Недопустимая стадия доски задач: {st_clean!r}")

    @staticmethod
    def _parse_decimal_string_for_schema(raw: str) -> float | None:
        """Разбор строки в float для полей integer/number (пробелы, NBSP, запятые)."""
        s = raw.strip().replace("\u00a0", "")
        if s == "":
            return None
        compact = s.replace(" ", "")
        candidates = [
            compact,
            compact.replace(",", "."),
            compact.replace(",", ""),
        ]
        for cand in candidates:
            try:
                return float(cand)
            except ValueError:
                continue
        return None

    @staticmethod
    def _coerce_attribute_value_for_schema(value: Any, expected_type: str) -> Any:
        """Приводит значение к JSON-типу поля там, где это однозначно (числа из строк)."""
        if expected_type == "integer":
            if isinstance(value, bool):
                return value
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value) if value.is_integer() else value
            if isinstance(value, str):
                parsed = EntityService._parse_decimal_string_for_schema(value)
                if parsed is None:
                    return value
                if not parsed.is_integer():
                    return value
                return int(parsed)
            return value

        if expected_type == "number":
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                parsed = EntityService._parse_decimal_string_for_schema(value)
                if parsed is None:
                    return value
                return float(parsed)
            return value

        return value

    @staticmethod
    def _check_field_type(value: Any, expected_type: str) -> bool:
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
            "external_refs": dict,
        }
        python_type = type_map.get(expected_type)
        if python_type is None:
            return True
        if expected_type == "integer":
            if isinstance(value, bool):
                return False
            return isinstance(value, int)
        if expected_type == "number":
            if isinstance(value, bool):
                return False
            return isinstance(value, (int, float))
        return isinstance(value, python_type)

    @staticmethod
    def _draft_repair_field_type_rules_doc() -> str:
        return (
            "В спецификации полей типов сущностей ключ type задаёт JSON-тип значения атрибута: "
            "string, integer, number, boolean, array, object, external_refs. "
            "Для enum используйте type=enum и массив values из строк. "
            "Числовые поля в черновике должны быть JSON-числами (не строками); "
            "при сохранении строковые значения с однозначным числовым смыслом приводятся к integer/number."
        )

    @staticmethod
    def _build_filter_operator_matrix() -> dict[str, set[str]]:
        return {
            "string": {"$eq", "$ne", "$contains", "$in", "$nin"},
            "text": {"$eq", "$ne", "$contains", "$in", "$nin"},
            "enum": {"$eq", "$ne", "$in", "$nin"},
            "integer": {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"},
            "number": {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"},
            "boolean": {"$eq", "$ne", "$in", "$nin"},
            "date": {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"},
            "datetime": {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"},
            "array": {"$contains", "$in", "$nin"},
            "object": {"$eq", "$ne"},
            "external_refs": {"$eq", "$ne"},
        }

    @staticmethod
    def _build_system_field_types() -> dict[str, str]:
        return {
            "entity_type": "string",
            "entity_subtype": "string",
            "namespace": "string",
            "status": "string",
            "priority": "string",
            "user_id": "string",
            "name": "text",
            "description": "text",
            "note_date": "date",
            "due_date": "date",
            "created_at": "datetime",
            "tags": "array",
        }

    @staticmethod
    def _collect_entity_type_field_specs(
        entity_type_model: EntityType,
    ) -> dict[str, dict[str, Any]]:
        field_specs: dict[str, dict[str, Any]] = {}
        required_fields = entity_type_model.required_fields or {}
        optional_fields = entity_type_model.optional_fields or {}
        for field_name, spec in {**required_fields, **optional_fields}.items():
            if isinstance(spec, dict):
                field_specs[field_name] = spec
        return field_specs

    @staticmethod
    def _validate_filter_value_type(field_type: str, operator: str, value: Any) -> None:
        def _validate_scalar(candidate: Any) -> None:
            if field_type in {"string", "text", "enum"}:
                if not isinstance(candidate, str):
                    raise ValueError(f"Filter value must be string for field type {field_type}")
                return
            if field_type == "integer":
                if not isinstance(candidate, int) or isinstance(candidate, bool):
                    raise ValueError("Filter value must be integer")
                return
            if field_type == "number":
                if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
                    raise ValueError("Filter value must be number")
                return
            if field_type == "boolean":
                if not isinstance(candidate, bool):
                    raise ValueError("Filter value must be boolean")
                return
            if field_type == "date":
                if not isinstance(candidate, str):
                    raise ValueError("Date filter value must be ISO date string")
                date.fromisoformat(candidate)
                return
            if field_type == "datetime":
                if not isinstance(candidate, str):
                    raise ValueError("Datetime filter value must be ISO datetime string")
                datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                return
            if field_type == "array":
                if not isinstance(candidate, (str, int, float, bool)):
                    raise ValueError("Array filter scalar value must be primitive")
                return
            if field_type == "object":
                if not isinstance(candidate, dict):
                    raise ValueError("Object filter value must be object")
                return
            if field_type == "external_refs":
                if not isinstance(candidate, dict):
                    raise ValueError("external_refs filter value must be object")
                return

        if operator in {"$in", "$nin"}:
            if not isinstance(value, list) or len(value) == 0:
                raise ValueError(f"{operator} requires non-empty array value")
            for item in value:
                _validate_scalar(item)
            return

        if field_type == "array" and operator == "$contains":
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError("$contains for array field requires primitive value")
            return

        _validate_scalar(value)

    async def resolve_filter_field_types(
        self,
        *,
        namespace: str,
        entity_type: str | None,
        entity_subtype: str | None,
        filters: dict[str, Any] | None,
    ) -> dict[str, str]:
        if filters is None:
            return {}

        system_field_types = self._build_system_field_types()
        field_specs: dict[str, dict[str, Any]] = {}
        type_id = entity_subtype or entity_type
        if type_id is not None:
            entity_type_model = await self._entity_type_repo.get_by_type_id(
                type_id,
                namespace=namespace,
            )
            if entity_type_model is None:
                raise ValueError(f"Entity type not found: {type_id}")
            field_specs = self._collect_entity_type_field_specs(entity_type_model)
        operator_matrix = self._build_filter_operator_matrix()
        used_field_types: dict[str, str] = {}

        def _resolve_field_type(field_name: str) -> str:
            if field_name in system_field_types:
                return system_field_types[field_name]
            if not field_name.startswith("attributes."):
                raise ValueError(f"Unsupported filter field: {field_name}")
            if type_id is None:
                raise ValueError(
                    "entity_type or entity_subtype is required for attributes.* filters"
                )
            attr_name = field_name.split(".", 1)[1]
            field_spec = field_specs.get(attr_name)
            if field_spec is None:
                raise ValueError(f"Attribute field '{attr_name}' is not defined in schema")
            field_type = field_spec.get("type")
            if not isinstance(field_type, str) or field_type.strip() == "":
                raise ValueError(f"Field '{attr_name}' has invalid schema type")
            return field_type

        def _validate_node(node: dict[str, Any]) -> None:
            if "$and" in node:
                for child in node["$and"]:
                    _validate_node(child)
                return
            if "$or" in node:
                for child in node["$or"]:
                    _validate_node(child)
                return

            field_name = node["field"]
            operator = node["op"]
            value = node["value"]
            field_type = _resolve_field_type(field_name)
            allowed_ops = operator_matrix.get(field_type, {"$eq", "$ne"})
            if operator not in allowed_ops:
                raise ValueError(
                    f"Operator '{operator}' is not allowed for field type '{field_type}'"
                )
            self._validate_filter_value_type(field_type, operator, value)
            used_field_types[field_name] = field_type

        _validate_node(filters)
        return used_field_types

    async def _load_namespace_crm_settings(self, namespace: str) -> NamespaceCRMSettings:
        ns = await self._namespace_repo.get(namespace)
        if ns is None or ns.crm_settings is None:
            return NamespaceCRMSettings()
        return ns.crm_settings

    async def _validate_voice_target(self, entity_id: str, company_id: str) -> None:
        ent = await self._entity_repo.get(entity_id)
        if ent is None or ent.company_id != company_id:
            raise ValueError(f"Сущность голоса не найдена: {entity_id}")
        et = await self._entity_type_repo.get_by_type_id(
            ent.entity_type,
            namespace=ent.namespace,
        )
        if et is None or not et.is_voice_target:
            raise ValueError(
                f"Тип {ent.entity_type!r} не может быть голосом заметки (is_voice_target=False)"
            )

    async def _validate_context_target(self, entity_id: str, company_id: str) -> None:
        ent = await self._entity_repo.get(entity_id)
        if ent is None or ent.company_id != company_id:
            raise ValueError(f"Сущность контекста не найдена: {entity_id}")
        et = await self._entity_type_repo.get_by_type_id(
            ent.entity_type,
            namespace=ent.namespace,
        )
        if et is None or not et.is_context_anchor:
            raise ValueError("Контекст заметки должен быть типом с флагом якоря контекста")

    async def _get_existing_outgoing_target(
        self,
        source_entity_id: str,
        relationship_type: str,
    ) -> str | None:
        rels = await self._relationship_repo.get_outgoing(source_entity_id, relationship_type)
        if not rels:
            return None
        return rels[0].target_entity_id

    async def get_note_voice_entity_id(self, note_id: str) -> str | None:
        """Возвращает entity_id автора заметки (note_voice relationship), если есть."""
        return await self._get_existing_outgoing_target(note_id, NOTE_VOICE_RELATIONSHIP_TYPE)

    async def _resolve_voice_entity_id_for_note(
        self,
        *,
        namespace: str,
        user_id: str,
        company_id: str,
        voice_entity_id: str | None,
        voice_entity_in_payload: bool,
    ) -> str | None:
        if voice_entity_in_payload:
            if voice_entity_id is None:
                return None
            await self._validate_voice_target(voice_entity_id, company_id)
            return voice_entity_id
        settings = await self._load_namespace_crm_settings(namespace)
        mode = settings.default_note_voice
        if mode == "none":
            return None
        if mode == "self":
            return await self._user_person_service.get_or_create_person_entity_id(
                user_id, company_id
            )
        last_id = await self._user_person_service.resolve_last_voice_entity_id(
            user_id, company_id, namespace
        )
        if last_id:
            await self._validate_voice_target(last_id, company_id)
            return last_id
        return await self._user_person_service.get_or_create_person_entity_id(user_id, company_id)

    async def _resolve_context_entity_id_for_note(
        self,
        *,
        namespace: str,
        company_id: str,
        context_entity_id: str | None,
        context_entity_in_payload: bool,
    ) -> str | None:
        if context_entity_in_payload:
            if context_entity_id is None:
                return None
            await self._validate_context_target(context_entity_id, company_id)
            return context_entity_id
        settings = await self._load_namespace_crm_settings(namespace)
        anchor = settings.default_context_entity_id
        if anchor is None or (isinstance(anchor, str) and anchor.strip() == ""):
            return None
        await self._validate_context_target(anchor, company_id)
        return anchor

    async def _sync_note_graph_edges(
        self,
        *,
        note_id: str,
        namespace: str,
        user_id: str,
        resolved_voice_id: str | None,
        resolved_context_id: str | None,
    ) -> None:
        company_id = self._get_company_id()
        await self._relationship_repo.delete_outgoing_by_source_and_types(
            note_id,
            [NOTE_VOICE_RELATIONSHIP_TYPE, IN_CONTEXT_RELATIONSHIP_TYPE],
        )
        now = datetime.now(UTC)
        if resolved_voice_id:
            voice_row = Relationship(
                relationship_id=str(uuid.uuid4()),
                source_entity_id=note_id,
                target_entity_id=resolved_voice_id,
                relationship_type=NOTE_VOICE_RELATIONSHIP_TYPE,
                namespace=namespace,
                weight=1.0,
                confidence=1.0,
                attributes={},
                company_id=company_id,
                created_at=now,
                updated_at=now,
            )
            await self._relationship_repo.create(voice_row)
            await self._user_person_service.record_last_voice_entity(
                user_id, namespace, resolved_voice_id
            )
        if resolved_context_id:
            ctx_row = Relationship(
                relationship_id=str(uuid.uuid4()),
                source_entity_id=note_id,
                target_entity_id=resolved_context_id,
                relationship_type=IN_CONTEXT_RELATIONSHIP_TYPE,
                namespace=namespace,
                weight=1.0,
                confidence=1.0,
                attributes={},
                company_id=company_id,
                created_at=now,
                updated_at=now,
            )
            await self._relationship_repo.create(ctx_row)

    async def apply_imported_note_graph_links(
        self,
        *,
        note_id: str,
        namespace: str,
        context_parent_entity_id: str,
        user_id: str,
    ) -> None:
        ns = self._resolve_namespace_for_write(namespace)
        company_id = self._get_company_id()
        note = await self._entity_repo.get(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")
        mention_ids = self.extract_linked_entity_ids_from_description(note.description or "")
        await self._sync_note_mention_links(note_id, mention_ids, ns)
        resolved_voice = await self._resolve_voice_entity_id_for_note(
            namespace=ns,
            user_id=user_id,
            company_id=company_id,
            voice_entity_id=None,
            voice_entity_in_payload=False,
        )
        await self._sync_note_graph_edges(
            note_id=note_id,
            namespace=ns,
            user_id=user_id,
            resolved_voice_id=resolved_voice,
            resolved_context_id=context_parent_entity_id,
        )

    async def resolved_entity_ids_for_note(self, note_id: str) -> list[str]:
        note = await self._entity_repo.get(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")
        from_text = self.extract_linked_entity_ids_from_description(note.description or "")
        rels = await self._relationship_repo.get_by_entity(note_id)
        from_edges: list[str] = []
        for rel in rels:
            if rel.source_entity_id != note_id:
                continue
            if rel.relationship_type not in _RESOLVED_NOTE_NEIGHBOR_REL_TYPES:
                continue
            from_edges.append(rel.target_entity_id)
        seen: set[str] = {note_id}
        out: list[str] = []
        for eid in from_text + from_edges:
            if eid in seen:
                continue
            seen.add(eid)
            out.append(eid)
        return out

    def _synthetic_entity_description_for_analyze(self, row: CRMEntity) -> str:
        parts: list[str] = []
        nm = (row.name or "").strip()
        if nm:
            parts.append(nm)
        parts.append(f"type={row.entity_type}")
        attrs = row.attributes or {}
        for key in (
            "email",
            "phone",
            "stage",
            "source",
            "first_name",
            "last_name",
            "display_name",
            "price",
        ):
            v = attrs.get(key)
            if v is None:
                continue
            s = str(v).strip()
            if s:
                parts.append(f"{key}={s}")
        return " ".join(parts)

    def _effective_description_for_analyze_inject(self, row: CRMEntity) -> str:
        raw = row.description if isinstance(row.description, str) else ""
        if len(raw.strip()) >= _ANALYZE_ENTITY_DESCRIPTION_MIN_LEN:
            return raw.strip()
        syn = self._synthetic_entity_description_for_analyze(row).strip()
        if len(syn) >= _ANALYZE_ENTITY_DESCRIPTION_MIN_LEN:
            return syn
        return f"{syn} id={row.entity_id}"

    async def _list_notes_for_date(
        self, date_str: str, namespace: str | None = None
    ) -> list[CRMEntity]:
        query_filters: dict[str, Any] = {
            "field": "note_date",
            "op": "$eq",
            "value": date_str,
        }
        eff_type, list_nf, legacy_nf = await self._list_by_cursor_note_family_args(
            NOTE_ROOT_ENTITY_TYPE_ID,
            None,
            self._normalize_namespace(namespace),
        )
        entities, _, _ = await self._entity_repo.list_by_cursor(
            entity_type=eff_type,
            entity_subtype=None,
            namespace=self._normalize_namespace(namespace),
            filters=query_filters,
            filter_field_types={"note_date": "date"},
            limit=1000,
            list_note_family=list_nf,
            note_family_legacy_entity_types=legacy_nf,
        )
        return entities

    @staticmethod
    def _build_source_version(notes: list[CRMEntity]) -> dict[str, Any]:
        notes_count = len(notes)
        max_updated_at: str | None = None
        for note in notes:
            if note.updated_at is None:
                continue
            note_updated_iso = note.updated_at.isoformat()
            if max_updated_at is None or note_updated_iso > max_updated_at:
                max_updated_at = note_updated_iso
        return {
            "notes_count": notes_count,
            "max_updated_at": max_updated_at,
        }

    async def _collect_notes_and_source_version(
        self,
        date_str: str,
        namespace: str | None = None,
    ) -> tuple[list[CRMEntity], dict[str, Any]]:
        notes = await self._list_notes_for_date(date_str=date_str, namespace=namespace)
        source_version = self._build_source_version(notes)
        return notes, source_version

    async def create_entity(
        self,
        entity_type: str,
        name: str,
        description: str | None = None,
        entity_subtype: str | None = None,
        attributes: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        voice_entity_id: str | None = None,
        context_entity_id: str | None = None,
        voice_entity_in_payload: bool = False,
        context_entity_in_payload: bool = False,
        **kwargs,
    ) -> CRMEntity:
        """Создает новую entity"""

        # user_id ОБЯЗАТЕЛЕН - берем из kwargs или из контекста
        user_id = kwargs.pop("user_id", None)
        if not user_id:
            context = get_context()
            if not context or not context.user:
                raise ValueError("user_id is required (no user in context)")
            user_id = context.user.user_id

        namespace = self._resolve_namespace_for_write(kwargs.get("namespace"))
        kwargs["namespace"] = namespace
        await self._ensure_namespace_exists(namespace)

        storage_type, storage_subtype = await self._resolve_storage_type_for_note_family(
            entity_type,
            entity_subtype,
            namespace,
        )
        entity_type = storage_type
        entity_subtype = storage_subtype

        await self._ensure_entity_type_allowed_in_namespace(
            entity_type=entity_type,
            namespace=namespace,
            entity_subtype=entity_subtype,
        )
        if entity_type == "task":
            base_attrs = dict(attributes or {})
            crm = await self._load_namespace_crm_settings(namespace)
            bkey = task_board_key("task", entity_subtype)
            stages = resolve_task_board_stages(crm, bkey)
            if "status" not in base_attrs or base_attrs.get("status") is None:
                base_attrs["status"] = stages[0].id
            else:
                st0 = base_attrs["status"]
                if not isinstance(st0, str) or not st0.strip():
                    base_attrs["status"] = stages[0].id
            attributes = base_attrs
            await self._validate_task_entity_board_status(
                namespace=namespace,
                entity_subtype=entity_subtype,
                attributes=attributes,
            )
        await self._validate_entity_attributes(
            entity_type=entity_type,
            attributes=attributes or {},
            namespace=namespace,
            entity_subtype=entity_subtype,
        )

        if entity_type == NOTE_ROOT_ENTITY_TYPE_ID and kwargs.get("note_date") is None:
            kwargs["note_date"] = datetime.now(UTC).date()

        entity = CRMEntity(
            user_id=user_id,
            entity_id=str(uuid.uuid4()),
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            name=name,
            description=description,
            attributes=attributes or {},
            tags=tags or [],
            company_id=self._get_company_id(),
            **kwargs,
        )

        attachment_text_merged = False
        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID and entity.attachment_ids:
            merged_desc: str | None = entity.description
            for fid in entity.attachment_ids:
                try:
                    text, att_name = await load_text_and_name_from_stored_file_id(fid)
                except Exception as exc:
                    logger.warning(
                        "note create: attachment text extract failed",
                        entity_id=entity.entity_id,
                        file_id=fid,
                        error=str(exc),
                    )
                    continue
                if text.strip():
                    attachment_text_merged = True
                merged_desc = merge_attachment_extracted_into_description(
                    merged_desc,
                    att_name,
                    text,
                )
            entity.description = merged_desc

        await self._entity_repo.create(entity)
        logger.info(f"Created entity: {entity.entity_id}, type={entity.full_type}")

        if attachment_text_merged:
            if self._note_markdown_format_scheduler is None:
                raise ValueError("note_markdown_format_scheduler is required")
            await self._note_markdown_format_scheduler(
                note_id=entity.entity_id,
                company_id=entity.company_id,
                namespace=entity.namespace,
                expected_updated_at_iso=entity.updated_at.isoformat(),
            )

        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            company_id = self._get_company_id()
            resolved_voice = await self._resolve_voice_entity_id_for_note(
                namespace=namespace,
                user_id=user_id,
                company_id=company_id,
                voice_entity_id=voice_entity_id,
                voice_entity_in_payload=voice_entity_in_payload,
            )
            resolved_context = await self._resolve_context_entity_id_for_note(
                namespace=namespace,
                company_id=company_id,
                context_entity_id=context_entity_id,
                context_entity_in_payload=context_entity_in_payload,
            )
            await self._sync_note_graph_edges(
                note_id=entity.entity_id,
                namespace=namespace,
                user_id=user_id,
                resolved_voice_id=resolved_voice,
                resolved_context_id=resolved_context,
            )

        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID and entity.note_date is not None:
            await self.enqueue_daily_summary_rebuild(
                date_str=entity.note_date.isoformat(),
                namespace=entity.namespace,
            )

        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            note_date_iso = entity.note_date.isoformat() if entity.note_date is not None else None
            await broadcast_crm_note_event(
                company_id=entity.company_id,
                namespace=entity.namespace,
                note_id=entity.entity_id,
                note_date_iso=note_date_iso,
                action="created",
                company_repository=self._company_repo,
                access_grant_repository=self._access_grant_repo,
            )

        return entity

    async def get_entity(
        self,
        entity_id: str,
    ) -> CRMEntity | None:
        """Получает entity по ID"""

        return await self._entity_repo.get(entity_id)

    async def list_entities_by_ids_ordered(self, entity_ids: list[str]) -> list[CRMEntity]:
        """Сущности по списку id в заданном порядке; отсутствующие id пропускаются."""
        return await self._entity_repo.list_by_entity_ids_ordered(entity_ids)

    async def merge_entities(self, body: EntityMergeRequest) -> tuple[CRMEntity, str]:
        """
        Сливает source в survivor: переносит связи и права, объединяет поля по выбору,
        удаляет source. survivor сохраняет entity_id и entity_type (тип source может отличаться).
        """
        survivor_id = body.survivor_entity_id.strip()
        source_id = body.source_entity_id.strip()
        if survivor_id == source_id:
            raise ValueError("survivor_entity_id и source_entity_id должны различаться")

        survivor = await self._entity_repo.get(survivor_id)
        source = await self._entity_repo.get(source_id)
        if survivor is None:
            raise ValueError(f"Сущность survivor не найдена: {survivor_id}")
        if source is None:
            raise ValueError(f"Сущность source не найдена: {source_id}")

        company_id = self._get_company_id()
        if survivor.company_id != company_id or source.company_id != company_id:
            raise ValueError("Сущности должны принадлежать активной компании")

        if survivor.namespace != source.namespace:
            raise ValueError("Разный namespace: слияние запрещено")

        if (
            survivor.entity_type == NOTE_ROOT_ENTITY_TYPE_ID
            and source.entity_type == NOTE_ROOT_ENTITY_TYPE_ID
        ):
            raise ValueError("Слияние двух заметок (note) не поддерживается")

        mapping_survivor = await self._company_mapping_repo.get_by_entity(survivor_id)
        mapping_source = await self._company_mapping_repo.get_by_entity(source_id)
        if mapping_survivor is not None or mapping_source is not None:
            raise ValueError("Слияние сущности из company_mapping запрещено")

        for ent, role in ((survivor, "survivor"), (source, "source")):
            attrs = ent.attributes or {}
            if attrs.get(PLATFORM_USER_ID_ATTR):
                raise ValueError(f"Слияние персональной contact-сущности ({role}) запрещено")

        scalar_choices = dict(body.scalar_choices)
        attr_choices = dict(body.attribute_choices)

        conflict_scalar_keys: set[str] = set()
        merged_scalars: dict[str, Any] = {}
        for key in _MERGE_SCALAR_KEYS:
            av = getattr(survivor, key)
            bv = getattr(source, key)
            if _canonical_json(av) == _canonical_json(bv):
                merged_scalars[key] = av
            else:
                conflict_scalar_keys.add(key)
                if key not in scalar_choices:
                    raise ValueError(
                        f"Конфликт поля {key}: укажите scalar_choices[{key!r}] "
                        f"равным 'survivor' или 'source'"
                    )
                side = scalar_choices[key]
                if side not in ("survivor", "source"):
                    raise ValueError(f"Недопустимое значение scalar_choices[{key!r}]: {side!r}")
                merged_scalars[key] = av if side == "survivor" else bv

        extra_scalar = set(scalar_choices) - conflict_scalar_keys
        if extra_scalar:
            raise ValueError(
                "Лишние ключи в scalar_choices (нет конфликта): " + ", ".join(sorted(extra_scalar))
            )

        sa = dict(survivor.attributes or {})
        sb = dict(source.attributes or {})
        all_attr_keys = set(sa.keys()) | set(sb.keys())
        conflict_attr_keys: set[str] = set()
        merged_attrs: dict[str, Any] = {}
        for k in sorted(all_attr_keys):
            a_has = k in sa
            b_has = k in sb
            if a_has and not b_has:
                merged_attrs[k] = sa[k]
            elif b_has and not a_has:
                merged_attrs[k] = sb[k]
            elif _canonical_json(sa[k]) == _canonical_json(sb[k]):
                merged_attrs[k] = sa[k]
            else:
                conflict_attr_keys.add(k)
                if k not in attr_choices:
                    raise ValueError(f"Конфликт attributes[{k!r}]: укажите attribute_choices")
                side = attr_choices[k]
                if side not in ("survivor", "source"):
                    raise ValueError(f"Недопустимое значение attribute_choices[{k!r}]: {side!r}")
                merged_attrs[k] = sa[k] if side == "survivor" else sb[k]

        extra_attr = set(attr_choices) - conflict_attr_keys
        if extra_attr:
            raise ValueError(
                "Лишние ключи в attribute_choices (нет конфликта): " + ", ".join(sorted(extra_attr))
            )

        def _union_str_lists(a: object, b: object) -> list[str]:
            if a is not None and not isinstance(a, list):
                raise ValueError("Ожидался список строк")
            if b is not None and not isinstance(b, list):
                raise ValueError("Ожидался список строк")
            merged: list[str] = []
            for value in [*(a or []), *(b or [])]:
                if not isinstance(value, str):
                    raise ValueError("Ожидался список строк")
                merged.append(value)
            return list(dict.fromkeys(merged))

        merged_tags = _union_str_lists(survivor.tags, source.tags)
        merged_assignees = _union_str_lists(survivor.assignees, source.assignees)
        merged_attachments = _union_str_lists(survivor.attachment_ids, source.attachment_ids)

        await self._relationship_repo.rewrite_entity_id(company_id, source_id, survivor_id)
        await self._relationship_repo.deduplicate_relationships_for_entity(survivor_id)

        await self._entity_repo.rewrite_source_entity_id_references(
            company_id, source_id, survivor_id
        )

        await self._access_grant_repo.remap_entity_resource_id(company_id, source_id, survivor_id)
        await self._access_grant_repo.deduplicate_entity_grants(company_id, survivor_id)

        await self._access_request_repo.remap_entity_resource_id(company_id, source_id, survivor_id)
        await self._access_request_repo.deduplicate_pending_entity_requests(survivor_id)

        source_fresh = await self._entity_repo.get(source_id)
        if source_fresh is None:
            raise ValueError("Сущность source пропала до завершения слияния")
        source_fresh.attachment_ids = []
        source_fresh.updated_at = datetime.now(UTC)
        await self._entity_repo.update(source_fresh)

        surv = await self._entity_repo.get(survivor_id)
        if surv is None:
            raise ValueError("Сущность survivor не найдена после переноса связей")
        for key in _MERGE_SCALAR_KEYS:
            setattr(surv, key, merged_scalars[key])
        surv.tags = merged_tags
        surv.assignees = merged_assignees
        surv.attributes = merged_attrs
        surv.attachment_ids = merged_attachments
        surv.updated_at = datetime.now(UTC)
        await self._ensure_namespace_exists(surv.namespace)
        await self._ensure_entity_type_allowed_in_namespace(
            entity_type=surv.entity_type,
            namespace=surv.namespace,
            entity_subtype=surv.entity_subtype,
        )
        await self._entity_repo.update(surv)

        await self._delete_entity_with_saga(source_id)

        out = await self._entity_repo.get(survivor_id)
        if out is None:
            raise ValueError("Сущность survivor не найдена после слияния")
        return (out, source_id)

    async def update_entity(
        self,
        entity_id: str,
        updates: dict[str, Any],
        voice_entity_id: str | None = None,
        voice_entity_in_payload: bool = False,
        context_entity_id: str | None = None,
        context_entity_in_payload: bool = False,
    ) -> CRMEntity:
        """Обновляет entity"""

        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        old_note_date = entity.note_date.isoformat() if entity.note_date is not None else None
        old_namespace = entity.namespace
        is_note = entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID
        old_attachment_ids = list(entity.attachment_ids or []) if is_note else []

        next_namespace = self._resolve_namespace_for_write(
            updates["namespace"] if "namespace" in updates else entity.namespace
        )
        next_entity_type_raw = updates["entity_type"] if "entity_type" in updates else entity.entity_type
        if not isinstance(next_entity_type_raw, str) or not next_entity_type_raw.strip():
            raise ValueError("entity_type is required")
        next_entity_type = next_entity_type_raw
        next_entity_subtype_raw = (
            updates["entity_subtype"] if "entity_subtype" in updates else entity.entity_subtype
        )
        if next_entity_subtype_raw is not None and not isinstance(next_entity_subtype_raw, str):
            raise ValueError("entity_subtype must be a string or null")
        next_entity_subtype = next_entity_subtype_raw
        await self._ensure_namespace_exists(next_namespace)
        await self._ensure_entity_type_allowed_in_namespace(
            entity_type=next_entity_type,
            namespace=next_namespace,
            entity_subtype=next_entity_subtype,
        )
        merged_attributes = {**(entity.attributes or {}), **(updates.get("attributes") or {})}
        if next_entity_type == "task":
            await self._validate_task_entity_board_status(
                namespace=next_namespace,
                entity_subtype=next_entity_subtype,
                attributes=merged_attributes,
            )
        await self._validate_entity_attributes(
            entity_type=next_entity_type,
            attributes=merged_attributes,
            namespace=next_namespace,
            entity_subtype=next_entity_subtype,
        )

        for key, value in updates.items():
            if not hasattr(entity, key):
                continue
            if key == "entity_subtype" and value is None:
                setattr(entity, key, None)
                continue
            if value is not None:
                setattr(entity, key, value)
        entity.namespace = next_namespace

        if is_note and "attachment_ids" in updates:
            prior = frozenset(old_attachment_ids)
            added = [x for x in (entity.attachment_ids or []) if x not in prior]
            merged_desc: str | None = entity.description
            for fid in added:
                try:
                    text, att_name = await load_text_and_name_from_stored_file_id(fid)
                except Exception as exc:
                    logger.warning(
                        "note update: new attachment text extract failed",
                        entity_id=entity_id,
                        file_id=fid,
                        error=str(exc),
                    )
                    continue
                merged_desc = merge_attachment_extracted_into_description(
                    merged_desc,
                    att_name,
                    text,
                )
            entity.description = merged_desc

        entity.updated_at = datetime.now(UTC)
        await self._entity_repo.update(entity)

        logger.info(f"Updated entity: {entity_id}")

        if is_note:
            new_note_date = entity.note_date.isoformat() if entity.note_date is not None else None
            new_namespace = entity.namespace

            if old_note_date is not None:
                await self.enqueue_daily_summary_rebuild(
                    date_str=old_note_date,
                    namespace=old_namespace,
                )
            if new_note_date is not None and (
                new_note_date != old_note_date or new_namespace != old_namespace
            ):
                await self.enqueue_daily_summary_rebuild(
                    date_str=new_note_date,
                    namespace=new_namespace,
                )
            if (
                new_note_date is not None
                and new_note_date == old_note_date
                and new_namespace == old_namespace
            ):
                await self.enqueue_daily_summary_rebuild(
                    date_str=new_note_date,
                    namespace=new_namespace,
                )

            note_date_iso = entity.note_date.isoformat() if entity.note_date is not None else None
            await broadcast_crm_note_event(
                company_id=entity.company_id,
                namespace=entity.namespace,
                note_id=entity.entity_id,
                note_date_iso=note_date_iso,
                action="updated",
                company_repository=self._company_repo,
                access_grant_repository=self._access_grant_repo,
            )

            company_id = self._get_company_id()
            uid = entity.user_id
            ns = entity.namespace
            if voice_entity_in_payload:
                resolved_voice = await self._resolve_voice_entity_id_for_note(
                    namespace=ns,
                    user_id=uid,
                    company_id=company_id,
                    voice_entity_id=voice_entity_id,
                    voice_entity_in_payload=True,
                )
            else:
                resolved_voice = await self._get_existing_outgoing_target(
                    entity.entity_id,
                    NOTE_VOICE_RELATIONSHIP_TYPE,
                )
            if context_entity_in_payload:
                resolved_context = await self._resolve_context_entity_id_for_note(
                    namespace=ns,
                    company_id=company_id,
                    context_entity_id=context_entity_id,
                    context_entity_in_payload=True,
                )
            else:
                resolved_context = await self._get_existing_outgoing_target(
                    entity.entity_id,
                    IN_CONTEXT_RELATIONSHIP_TYPE,
                )
            await self._sync_note_graph_edges(
                note_id=entity.entity_id,
                namespace=ns,
                user_id=uid,
                resolved_voice_id=resolved_voice,
                resolved_context_id=resolved_context,
            )
            if "description" in updates:
                mention_ids = self.extract_linked_entity_ids_from_description(
                    entity.description or ""
                )
                await self._sync_note_mention_links(entity.entity_id, mention_ids, ns)

        return entity

    async def list_entities(
        self,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: dict[str, Any] | None = None,
        filter_field_types: dict[str, str] | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[CRMEntity], str | None, bool]:
        """
        Получает список entities с cursor-пагинацией и фильтрацией по грантам.

        Oversample стратегия: запрашиваем кратно больше строк из БД,
        фильтруем по ACL и дозагружаем при нехватке, чтобы клиент
        всегда получал ровно ``limit`` читаемых записей (или меньше,
        если данных в БД не осталось).
        """
        user_id = self._get_user_id()
        company_id = self._get_company_id()

        (
            eff_entity_type,
            list_note_family,
            note_family_legacy,
        ) = await self._list_by_cursor_note_family_args(
            entity_type,
            entity_subtype,
            namespace,
        )

        oversample_factor = 3
        max_iterations = 3
        readable: list[CRMEntity] = []
        current_cursor = cursor
        db_has_more = True

        for _ in range(max_iterations):
            entities, repo_cursor, repo_has_more = await self._entity_repo.list_by_cursor(
                entity_type=eff_entity_type,
                entity_subtype=entity_subtype,
                namespace=namespace,
                filters=filters,
                filter_field_types=filter_field_types,
                limit=limit * oversample_factor,
                cursor=current_cursor,
                list_note_family=list_note_family,
                note_family_legacy_entity_types=note_family_legacy,
            )
            filtered = await self._access_control.batch_filter_readable(
                entities,
                user_id,
                company_id,
                query_namespace=namespace,
            )
            readable.extend(filtered)
            db_has_more = repo_has_more

            if len(readable) >= limit or not repo_has_more:
                break
            current_cursor = repo_cursor

        result = readable[:limit]
        has_more = len(readable) > limit or db_has_more

        next_cursor = None
        if result and has_more:
            last = result[-1]
            next_cursor = self._entity_repo.encode_cursor(last.created_at, last.entity_id)

        return result, next_cursor, has_more

    async def get_timeline_bounds(
        self,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Возвращает границы timeline по created_at."""
        (
            min_created_at,
            max_created_at,
            total_entities,
        ) = await self._entity_repo.get_created_at_bounds(
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
        )
        return {
            "min_created_at": min_created_at.isoformat() if min_created_at else None,
            "max_created_at": max_created_at.isoformat() if max_created_at else None,
            "total_entities": total_entities,
        }

    @staticmethod
    def _get_related_entity_id(relationship: Relationship, current_entity_id: str) -> str:
        if relationship.source_entity_id == current_entity_id:
            return relationship.target_entity_id
        if relationship.target_entity_id == current_entity_id:
            return relationship.source_entity_id
        raise ValueError(
            f"Relationship {relationship.relationship_id} does not include entity {current_entity_id}"
        )

    async def _build_entity_component_relationships(
        self,
        root_entity_id: str,
    ) -> dict[str, list[Relationship]]:
        queue: deque[str] = deque([root_entity_id])
        visited: set[str] = set()
        relationships_by_entity: dict[str, list[Relationship]] = {}

        while queue:
            entity_id = queue.popleft()
            if entity_id in visited:
                continue
            visited.add(entity_id)

            relationships = await self._relationship_repo.get_by_entity(entity_id)
            relationships_by_entity[entity_id] = relationships

            for relationship in relationships:
                related_entity_id = self._get_related_entity_id(relationship, entity_id)
                if related_entity_id not in visited:
                    queue.append(related_entity_id)

        return relationships_by_entity

    async def _collect_exclusive_related_entities_for_note(
        self,
        note_entity_id: str,
    ) -> list[str]:
        """
        Возвращает все сущности, созданные этой заметкой, которые не имеют связей с ДРУГИМИ заметками.

        Логика:
        1. Строим граф связей заметки
        2. Для каждой сущности проверяем: есть ли связи с ДРУГИМИ заметками (entity_type == NOTE_ROOT_ENTITY_TYPE_ID и entity_id != note_entity_id)
        3. Если нет таких связей - сущность подлежит удалению

        Это защищает от удаления сущностей, которые связаны с другими заметками.
        """
        relationships_by_entity = await self._build_entity_component_relationships(note_entity_id)
        component_order = list(relationships_by_entity.keys())

        logger.info(
            f"[_collect_exclusive_related_entities_for_note] note_id={note_entity_id}, component_order={component_order}"
        )

        # Получаем source_entity_id и entity_type для всех сущностей в компоненте
        entities = await self._entity_repo.get_by_ids(component_order)
        source_entity_id_map = {e.entity_id: e.source_entity_id for e in entities}
        entity_type_map = {e.entity_id: e.entity_type for e in entities}

        logger.info(
            f"[_collect_exclusive_related_entities_for_note] source_entity_id_map: {source_entity_id_map}"
        )
        logger.info(
            f"[_collect_exclusive_related_entities_for_note] entity_type_map: {entity_type_map}"
        )

        exclusive_entity_ids = []

        for entity_id in component_order:
            if entity_id == note_entity_id:
                continue

            # Сущность должна быть создана этой заметкой
            if source_entity_id_map.get(entity_id) != note_entity_id:
                logger.info(
                    f"[_collect_exclusive_related_entities_for_note] Entity {entity_id} not created by this note (source={source_entity_id_map.get(entity_id)})"
                )
                continue

            # Проверяем связи с ДРУГИМИ заметками
            relationships = relationships_by_entity.get(entity_id, [])
            has_other_note_connection = False
            other_note_connections = []

            for relationship in relationships:
                related_entity_id = self._get_related_entity_id(relationship, entity_id)
                related_type = entity_type_map.get(related_entity_id)

                # Если связанная сущность - заметка и это НЕ текущая заметка
                if related_type == NOTE_ROOT_ENTITY_TYPE_ID and related_entity_id != note_entity_id:
                    has_other_note_connection = True
                    other_note_connections.append(f"{related_entity_id} (type=note)")

            if not has_other_note_connection:
                exclusive_entity_ids.append(entity_id)
                logger.info(
                    f"[_collect_exclusive_related_entities_for_note] Entity {entity_id} can be deleted (no connections to other notes)"
                )
            else:
                logger.info(
                    f"[_collect_exclusive_related_entities_for_note] Entity {entity_id} has connections to other notes: {other_note_connections}"
                )

        logger.info(
            f"[_collect_exclusive_related_entities_for_note] final exclusive_entity_ids: {exclusive_entity_ids}"
        )
        return exclusive_entity_ids

    async def get_exclusive_related_entities_for_note(
        self,
        note_entity_id: str,
    ) -> list[dict[str, Any]]:
        """Возвращает список сущностей, которые будут удалены каскадно вместе с заметкой."""
        exclusive_entity_ids = await self._collect_exclusive_related_entities_for_note(
            note_entity_id
        )
        if not exclusive_entity_ids:
            return []

        entities = await self._entity_repo.get_by_ids(exclusive_entity_ids)
        return [
            {
                "entity_id": entity.entity_id,
                "name": entity.name,
                "entity_type": entity.entity_type,
                "entity_subtype": entity.entity_subtype,
                "namespace": entity.namespace,
                "description": entity.description,
            }
            for entity in entities
        ]

    async def _delete_entity_with_saga(
        self,
        entity_id: str,
    ) -> CRMEntity:
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found for deletion: {entity_id}")

        saga = EntityDeletionSaga()
        deleted_relationships: list[Relationship] = []

        async def delete_relationships() -> None:
            nonlocal deleted_relationships
            relationships = await self._relationship_repo.get_by_entity(entity_id)
            deleted_relationships = relationships.copy()
            await self._relationship_repo.delete_by_entity(entity_id)

        async def restore_relationships() -> None:
            for relationship in deleted_relationships:
                await self._relationship_repo.create(relationship)

        async def delete_attachments() -> None:
            await self._attachment_service.delete_all_attachments(entity_id)

        async def restore_attachments() -> None:
            pass

        async def delete_entity_from_db() -> None:
            await self._entity_repo.delete(entity_id)

        async def restore_entity_to_db() -> None:
            await self._entity_repo.create(entity)

        saga.add_step(
            SagaStep(
                name="Delete relationships",
                execute_fn=delete_relationships,
                compensate_fn=restore_relationships,
            )
        )
        saga.add_step(
            SagaStep(
                name="Delete attachments",
                execute_fn=delete_attachments,
                compensate_fn=restore_attachments,
            )
        )
        saga.add_step(
            SagaStep(
                name="Delete entity",
                execute_fn=delete_entity_from_db,
                compensate_fn=restore_entity_to_db,
            )
        )

        await saga.execute()
        return entity

    async def delete_entity(
        self,
        entity_id: str,
    ) -> bool:
        """
        Каскадное удаление entity через Saga pattern.

        Для note: удаляет саму заметку и эксклюзивно связанные сущности.
        Эксклюзивная сущность - та, у которой после удаления note не остается связей
        с сущностями вне удаляемого подграфа и которая была создана этой заметкой.
        """
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            logger.warning(f"Entity not found for deletion: {entity_id}")
            return False

        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            exclusive_related_entity_ids = await self._collect_exclusive_related_entities_for_note(
                entity_id
            )
            for related_entity_id in exclusive_related_entity_ids:
                related_entity = await self._entity_repo.get(related_entity_id)
                if related_entity is None:
                    logger.info(
                        f"Skip already deleted exclusive entity for note {entity_id}: {related_entity_id}"
                    )
                    continue
                await self._delete_entity_with_saga(related_entity_id)
                logger.info(
                    f"Deleted exclusive related entity for note {entity_id}: {related_entity_id}"
                )

            await self._delete_entity_with_saga(entity_id)
            logger.info(
                f"Successfully deleted note {entity_id} with {len(exclusive_related_entity_ids)} exclusive entities"
            )
        else:
            await self._delete_entity_with_saga(entity_id)
            logger.info(f"Successfully deleted entity: {entity_id} (cascade)")

        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID and entity.note_date is not None:
            await self.enqueue_daily_summary_rebuild(
                date_str=entity.note_date.isoformat(),
                namespace=entity.namespace,
            )

        if entity.entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            note_date_iso = entity.note_date.isoformat() if entity.note_date is not None else None
            await broadcast_crm_note_event(
                company_id=entity.company_id,
                namespace=entity.namespace,
                note_id=entity_id,
                note_date_iso=note_date_iso,
                action="deleted",
                company_repository=self._company_repo,
                access_grant_repository=self._access_grant_repo,
            )

        return True

    async def search_entities(
        self,
        query: str,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: dict[str, Any] | None = None,
        filter_field_types: dict[str, str] | None = None,
        limit: int = 100,
    ) -> list[tuple[CRMEntity, float]]:
        """Семантический поиск entities с фильтрацией по грантам. Возвращает (entity, score)."""
        results = await self._entity_repo.search_with_similarity(
            query=query,
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters,
            filter_field_types=filter_field_types,
            limit=limit,
        )
        entities = [entity for entity, _ in results]
        user_id = self._get_user_id()
        company_id = self._get_company_id()
        readable = await self._access_control.batch_filter_readable(
            entities, user_id, company_id, query_namespace=namespace
        )
        readable_ids = {e.entity_id for e in readable}
        return [(e, score) for e, score in results if e.entity_id in readable_ids]

    async def hybrid_search(
        self,
        query: str,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: dict[str, Any] | None = None,
        filter_field_types: dict[str, str] | None = None,
        limit: int = 100,
    ) -> list[tuple[CRMEntity, float, str]]:
        """Гибридный поиск RRF (tsvector + pgvector) с фильтрацией по грантам."""
        results = await self._entity_repo.hybrid_search(
            query=query,
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters,
            filter_field_types=filter_field_types,
            limit=limit,
        )
        entities = [entity for entity, _, _ in results]
        user_id = self._get_user_id()
        company_id = self._get_company_id()
        readable = await self._access_control.batch_filter_readable(
            entities, user_id, company_id, query_namespace=namespace
        )
        readable_ids = {e.entity_id for e in readable}
        return [(e, score, mt) for e, score, mt in results if e.entity_id in readable_ids]

    async def text_search(
        self,
        query: str,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: dict[str, Any] | None = None,
        filter_field_types: dict[str, str] | None = None,
        limit: int = 100,
    ) -> list[tuple[CRMEntity, float]]:
        """FTS поиск с ранжированием по ts_rank и фильтрацией по грантам."""
        results = await self._entity_repo.fts_search_ranked(
            query=query,
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters,
            filter_field_types=filter_field_types,
            limit=limit,
        )
        entities = [entity for entity, _ in results]
        user_id = self._get_user_id()
        company_id = self._get_company_id()
        readable = await self._access_control.batch_filter_readable(
            entities, user_id, company_id, query_namespace=namespace
        )
        readable_ids = {e.entity_id for e in readable}
        return [(e, score) for e, score in results if e.entity_id in readable_ids]

    async def aggregate_facets(
        self,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Фасетная агрегация: по entity_type, status, месяц создания."""
        return await self._entity_repo.aggregate_facets(namespace=namespace)

    async def search_mentions(
        self,
        text: str,
        namespace: str | None = None,
        limit: int = 20,
    ) -> list[CRMEntity]:
        """
        Real-time поиск упоминаний entities в тексте для подсветки.
        Семантический поиск + фильтр по совпадению имени.
        """
        if not text or len(text) < 3:
            return []

        words = text.lower().split()
        search_phrases = []

        for i in range(len(words)):
            if i + 1 < len(words):
                search_phrases.append(f"{words[i]} {words[i + 1]}")
            search_phrases.append(words[i])

        unique_phrases = list(set(search_phrases))[:5]

        combined_query = " ".join(unique_phrases)

        scored = await self._entity_repo.search_with_similarity(
            query=combined_query,
            namespace=namespace,
            limit=limit,
        )
        entities = [entity for entity, _ in scored]

        user_id = self._get_user_id()
        company_id = self._get_company_id()
        entities = await self._access_control.batch_filter_readable(
            entities, user_id, company_id, query_namespace=namespace
        )

        matched = [
            entity
            for entity in entities
            if any(phrase in entity.name.lower() for phrase in unique_phrases)
        ]
        return matched if matched else entities[:10]

    @staticmethod
    def _normalize_name_for_relationship_key(name: str) -> str:
        s = name.strip().lower()
        for q in "\u00ab\u00bb\"\"''`":
            s = s.replace(q, "")
        while "  " in s:
            s = s.replace("  ", " ")
        return s.strip()

    def _assign_draft_ids_to_note_and_entities(self, state: _AnalyzePipelineState) -> None:
        if state.note is not None:
            state.note = state.note.model_copy(update={"draft_entity_id": str(uuid.uuid4())})
        state.entities = [
            e.model_copy(update={"draft_entity_id": str(uuid.uuid4())}) for e in state.entities
        ]

    def _draft_entity_key_to_id_index(
        self,
        note: AIExtractedEntity | None,
        entities: list[AIExtractedEntity],
    ) -> dict[tuple[str, str], str]:
        buckets: dict[tuple[str, str], list[str]] = {}

        def put_row(entity: AIExtractedEntity) -> None:
            did = entity.draft_entity_id
            if not did:
                raise ValueError("Внутренняя ошибка: у сущности черновика нет draft_entity_id")
            norm_name = self._normalize_name_for_relationship_key(entity.name)
            type_lower = entity.entity_type.lower().strip()
            keys: list[tuple[str, str]] = [(type_lower, norm_name)]
            sub = entity.entity_subtype
            if isinstance(sub, str) and sub.strip():
                sub_lower = sub.lower().strip()
                if sub_lower != type_lower:
                    keys.append((sub_lower, norm_name))
            for key in keys:
                buckets.setdefault(key, []).append(did)

        if note is not None:
            put_row(note)
        for ent in entities:
            put_row(ent)

        out: dict[tuple[str, str], str] = {}
        for key, ids in buckets.items():
            if len(ids) > 1:
                logger.warning(
                    "analyze: дубликат ключа (тип, имя) в черновике %s — "
                    "оставляем первый draft_entity_id из %s",
                    key,
                    ids,
                )
            out[key] = ids[0]
        return out

    def _build_relationship_drafts_from_extracted(
        self,
        state: _AnalyzePipelineState,
    ) -> list[AIAnalysisRelationshipDraft]:
        key_index = self._draft_entity_key_to_id_index(state.note, state.entities)
        out: list[AIAnalysisRelationshipDraft] = []
        for ext in state.relationships_extracted:
            st = ext.source_type.strip()
            sn = ext.source_name
            tt = ext.target_type.strip()
            tn = ext.target_name
            sk = (st.lower(), self._normalize_name_for_relationship_key(sn))
            tk = (tt.lower(), self._normalize_name_for_relationship_key(tn))
            if sk not in key_index:
                logger.warning(
                    "analyze: LLM вернул связь с source, для которого нет черновика сущности: "
                    "type=%r name=%r — связь пропущена",
                    st,
                    sn,
                )
                continue
            if tk not in key_index:
                logger.warning(
                    "analyze: LLM вернул связь с target, для которого нет черновика сущности: "
                    "type=%r name=%r — связь пропущена",
                    tt,
                    tn,
                )
                continue
            out.append(
                AIAnalysisRelationshipDraft(
                    draft_relationship_id=str(uuid.uuid4()),
                    source_draft_entity_id=key_index[sk],
                    target_draft_entity_id=key_index[tk],
                    relationship_type=ext.relationship_type,
                    weight=ext.weight,
                    confidence=ext.confidence,
                    attributes=ext.attributes,
                )
            )
        return out

    async def _persist_analysis_draft_to_note(
        self,
        note_id: str,
        snapshot: AIAnalyzeResponse,
    ) -> None:
        note = await self._entity_repo.get(note_id)
        if not note:
            raise ValueError(f"Заметка не найдена: {note_id}")
        if note.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
            raise ValueError(
                f"Сохранение черновика analyze допустимо только для note, получено: {note.entity_type}"
            )
        attrs = dict(note.attributes or {})
        attrs.pop("ai_analysis_last_error", None)
        attrs.pop("ai_analysis_last_error_at", None)
        prev = attrs.get("ai_analysis_draft")
        next_ver = 1
        if isinstance(prev, dict) and isinstance(prev.get("draft_version"), int):
            next_ver = int(prev["draft_version"]) + 1
        stored = AIAnalysisDraftStored(
            draft_version=next_ver,
            updated_at=datetime.now(UTC).isoformat(),
            note=snapshot.note,
            entities=list(snapshot.entities),
            relationships=list(snapshot.relationships),
            known_entity_id_map=dict(snapshot.known_entity_id_map),
        )
        attrs["ai_analysis_draft"] = stored.model_dump(mode="json")

        # Если LLM вернул описание заметки — сохраняем его как ai_summary
        # чтобы пользователь видел резюме сразу, не дожидаясь ежечасовой daily summary задачи
        note_field = snapshot.note
        note_description = note_field.description if note_field is not None else None
        if isinstance(note_description, str):
            summary_text = note_description.strip()
            if summary_text:
                attrs["ai_summary"] = summary_text
                attrs["ai_summary_generated_at"] = datetime.now(UTC).isoformat()
                entity_names = [
                    e.name
                    for e in (snapshot.entities or [])
                    if isinstance(getattr(e, "name", None), str) and e.name.strip()
                ]
                if entity_names:
                    attrs["ai_summary_entities"] = entity_names[:8]

        if snapshot.attachment_summaries:
            attrs["attachment_summaries"] = snapshot.attachment_summaries

        await self.update_entity(note_id, {"attributes": attrs})

    async def record_note_analysis_failure(
        self,
        note_id: str,
        error_message: str,
        *,
        apply_failures: list[dict[str, str]] | None = None,
    ) -> None:
        note = await self._entity_repo.get(note_id)
        if note is None:
            return
        if note.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
            return
        if isinstance(error_message, str):
            msg = error_message.strip()
        else:
            msg = str(error_message).strip()
        if not msg:
            msg = "Неизвестная ошибка"
        if len(msg) > _AI_NOTE_ANALYSIS_ERROR_MAX_LEN:
            msg = msg[:_AI_NOTE_ANALYSIS_ERROR_MAX_LEN] + "…"
        attrs = dict(note.attributes or {})
        attrs["ai_analysis_last_error"] = msg
        attrs["ai_analysis_last_error_at"] = datetime.now(UTC).isoformat()
        if apply_failures:
            cleaned: list[dict[str, str]] = []
            for row in apply_failures:
                if not isinstance(row, dict):
                    continue
                cleaned.append(
                    {
                        "draft_entity_id": str(row.get("draft_entity_id", "")),
                        "entity_name": str(row.get("entity_name", "")),
                        "entity_type": str(row.get("entity_type", "")),
                        "message": str(row.get("message", "")),
                    }
                )
            attrs["ai_analysis_apply_failures"] = cleaned
        else:
            attrs.pop("ai_analysis_apply_failures", None)
        await self.update_entity(note_id, {"attributes": attrs})

    async def clear_note_analysis_error(self, note_id: str) -> None:
        note = await self._entity_repo.get(note_id)
        if note is None:
            return
        attrs = dict(note.attributes or {})
        error_keys = (
            "ai_analysis_last_error",
            "ai_analysis_last_error_at",
            "ai_analysis_apply_failures",
        )
        if not any(k in attrs for k in error_keys):
            return
        for k in error_keys:
            attrs.pop(k, None)
        await self.update_entity(note_id, {"attributes": attrs})

    async def _load_all_relationship_types_for_company(self) -> list[RelationshipType]:
        out: list[RelationshipType] = []
        offset = 0
        limit = 200
        while True:
            page = await self._relationship_type_repo.get_all_for_company(
                include_system=True,
                limit=limit,
                offset=offset,
            )
            if not page:
                break
            out.extend(page)
            if len(page) < limit:
                break
            offset += limit
        return out

    async def _validate_draft_repair_patch_list(
        self,
        draft: AIAnalysisDraftStored,
        patches: list[DraftEntityPatch],
        *,
        namespace_for_types: str,
    ) -> None:
        by_id: dict[str, AIExtractedEntity] = {
            e.draft_entity_id: e for e in draft.entities if e.draft_entity_id
        }
        if draft.note is not None and draft.note.draft_entity_id:
            n_id = draft.note.draft_entity_id
            by_id[n_id] = draft.note
        seen_ids: set[str] = set()
        for p in patches:
            did = p.draft_entity_id
            if did in seen_ids:
                raise ValueError(f"draft_repair: дубликат draft_entity_id в patch_entities: {did!r}")
            seen_ids.add(did)
            ent = by_id.get(did)
            if ent is None:
                raise ValueError(f"draft_repair: неизвестный draft_entity_id: {did!r}")

            et_after = ent.entity_type
            if p.entity_type is not None:
                s = str(p.entity_type).strip()
                if not s:
                    raise ValueError(f"draft_repair: пустой entity_type (draft_entity_id={did!r})")
                et_after = s

            sub_after = ent.entity_subtype
            if p.entity_subtype is not None:
                st = str(p.entity_subtype).strip()
                sub_after = st if st else None

            merged_attrs = dict(ent.attributes or {})
            if p.attributes is not None:
                merged_attrs.update(p.attributes)

            await self._validate_entity_attributes(
                et_after,
                merged_attrs,
                namespace_for_types,
                entity_subtype=sub_after,
            )

    async def repair_analysis_draft_via_flow(self, note_id: str) -> AIAnalysisDraftStored:
        """Вызывает CRM flow (ветка draft_repair) и патчит ai_analysis_draft."""
        from core.config import get_settings

        note, draft = await self._load_analysis_draft_from_note(note_id)
        attrs = note.attributes or {}
        summary_raw = attrs.get("ai_analysis_last_error")
        summary = summary_raw.strip() if isinstance(summary_raw, str) else ""
        failures_raw = attrs.get("ai_analysis_apply_failures")
        has_failures_list = isinstance(failures_raw, list) and len(failures_raw) > 0
        if not summary and not has_failures_list:
            raise ValueError(
                "Нет сохранённой ошибки применения черновика — починка по запросу не выполняется"
            )

        ns_for_types = self._normalize_namespace(note.namespace) or (note.namespace or "default")

        entity_rows = await self._entity_type_repo.load_all_entity_types_for_company(namespace=ns_for_types)
        rel_rows = await self._load_all_relationship_types_for_company()
        parent_map = await self._entity_type_repo.get_parent_type_id_map_for_namespace(ns_for_types)

        cleaned_failures: list[dict[str, str]] = []
        if isinstance(failures_raw, list):
            for row in failures_raw:
                if not isinstance(row, dict):
                    continue
                cleaned_failures.append(
                    {
                        "draft_entity_id": str(row.get("draft_entity_id", "")),
                        "entity_name": str(row.get("entity_name", "")),
                        "entity_type": str(row.get("entity_type", "")),
                        "message": str(row.get("message", "")),
                    }
                )

        catalog_et = [
            {
                "type_id": et.type_id,
                "namespace": et.namespace,
                "parent_type_id": et.parent_type_id,
                "name": et.name,
                "extractable": et.extractable,
                "required_fields": et.required_fields or {},
                "optional_fields": et.optional_fields or {},
            }
            for et in entity_rows
        ]
        catalog_rt = [
            {
                "type_id": rt.type_id,
                "name": rt.name,
                "description": rt.description,
                "prompt": rt.prompt,
                "is_directed": rt.is_directed,
                "inverse_type_id": rt.inverse_type_id,
            }
            for rt in rel_rows
        ]

        repair_context = {
            "draft": draft.model_dump(mode="json"),
            "apply_failure_summary": summary,
            "apply_failures": cleaned_failures,
            "entity_types_catalog": catalog_et,
            "relationship_types_catalog": catalog_rt,
            "parent_type_map": parent_map,
            "type_constraints_for_llm": EntityService._draft_repair_field_type_rules_doc(),
        }
        repair_context_json = json.dumps(repair_context, ensure_ascii=False)
        variables: dict[str, Any] = {
            **_crm_llm_interface_language_vars(),
            "repair_context_json": repair_context_json,
        }

        settings_global = get_settings()
        flows_base_url = settings_global.server.get_flows_service_url().rstrip("/")
        crm_settings = get_crm_settings()
        timeout_sec = crm_settings.analysis_draft_repair_a2a_timeout_seconds

        response = await self._a2a_client.send_task(
            base_url=f"{flows_base_url}/flows/api/v1/crm",
            content="CRM: починка черновика AI-анализа заметки",
            branch_id="draft_repair",
            metadata={"variables": variables},
            timeout=timeout_sec,
        )

        result_data = self._extract_data_from_a2a_response(response)
        if not result_data or "patch_entities" not in result_data:
            raise ValueError("Ответ flow draft_repair не содержит patch_entities")

        try:
            flow_result = AIAnalysisDraftRepairFlowResult.model_validate(result_data)
        except ValidationError as exc:
            raise ValueError(f"Невалидный ответ flow draft_repair: {exc}") from exc

        if not flow_result.patch_entities:
            notes = flow_result.repair_notes.strip() if isinstance(flow_result.repair_notes, str) else ""
            if notes:
                raise ValueError(notes)
            raise ValueError("Модель не вернула patch_entities для исправления черновика")

        await self._validate_draft_repair_patch_list(
            draft,
            flow_result.patch_entities,
            namespace_for_types=ns_for_types,
        )

        patch_body = AIAnalysisDraftPatchRequest(
            expected_version=draft.draft_version,
            patch_entities=list(flow_result.patch_entities),
        )
        updated = await self.patch_analysis_draft(note_id, patch_body)
        await self.clear_note_analysis_error(note_id)
        return updated

    async def discard_note_analysis_draft(self, note_id: str) -> None:
        note = await self._entity_repo.get(note_id)
        if note is None:
            raise ValueError("Заметка не найдена")
        if note.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
            raise ValueError("Ожидалась заметка (entity_type=note)")
        attrs = dict(note.attributes or {})
        keys = (
            "ai_analysis_draft",
            "ai_analysis_last_error",
            "ai_analysis_last_error_at",
            "ai_analysis_apply_failures",
        )
        if not any(k in attrs for k in keys):
            return
        for k in keys:
            attrs.pop(k, None)
        await self.update_entity(note_id, {"attributes": attrs})

    async def _load_analysis_draft_from_note(
        self,
        note_id: str,
    ) -> tuple[CRMEntity, AIAnalysisDraftStored]:
        note = await self._entity_repo.get(note_id)
        if not note:
            raise ValueError(f"Entity not found: {note_id}")
        if note.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
            raise ValueError("Ожидалась заметка (entity_type=note)")
        raw = (note.attributes or {}).get("ai_analysis_draft")
        if not isinstance(raw, dict):
            raise ValueError("У заметки нет черновика ai_analysis_draft")
        if not isinstance(raw.get("draft_version"), int):
            raise ValueError(
                "Некорректный формат ai_analysis_draft: отсутствует или неверен draft_version"
            )
        draft = AIAnalysisDraftStored.model_validate(raw)
        for ent in draft.entities:
            if not ent.draft_entity_id:
                raise ValueError("Каждая сущность в черновике должна иметь draft_entity_id")
        for rel in draft.relationships:
            if (
                not rel.draft_relationship_id
                or not rel.source_draft_entity_id
                or not rel.target_draft_entity_id
            ):
                raise ValueError(
                    "Каждая связь в черновике должна иметь draft_relationship_id, "
                    "source_draft_entity_id и target_draft_entity_id"
                )
        return note, draft

    async def patch_analysis_draft(
        self,
        note_id: str,
        body: AIAnalysisDraftPatchRequest,
    ) -> AIAnalysisDraftStored:
        note, draft = await self._load_analysis_draft_from_note(note_id)
        if body.expected_version != draft.draft_version:
            raise DraftVersionConflictError(
                f"Версия черновика не совпадает: ожидалось {body.expected_version}, "
                f"в БД {draft.draft_version}"
            )

        remove_e: set[str] = set(body.remove_entity_draft_ids)
        remove_r: set[str] = set(body.remove_relationship_draft_ids)

        entities = [e for e in draft.entities if e.draft_entity_id not in remove_e]
        rels = [r for r in draft.relationships if r.draft_relationship_id not in remove_r]

        remaining_draft_ids = {e.draft_entity_id for e in entities if e.draft_entity_id}
        if draft.note is not None and draft.note.draft_entity_id:
            remaining_draft_ids.add(draft.note.draft_entity_id)
        rels = [
            r
            for r in rels
            if r.source_draft_entity_id in remaining_draft_ids
            and r.target_draft_entity_id in remaining_draft_ids
        ]

        ns_for_types = self._normalize_namespace(note.namespace) or (note.namespace or "default")

        existing_entity_ids: set[str] = {
            e.draft_entity_id for e in entities if e.draft_entity_id
        }
        if draft.note is not None and draft.note.draft_entity_id:
            existing_entity_ids.add(draft.note.draft_entity_id)
        existing_entity_ids.update(draft.known_entity_id_map.keys())

        seen_new_ent: set[str] = set()
        appended_entities: list[AIExtractedEntity] = []
        for ent in body.add_entities:
            did = ent.draft_entity_id
            if not did:
                raise ValueError("add_entities: отсутствует draft_entity_id")
            if did in existing_entity_ids or did in seen_new_ent:
                raise ValueError(f"add_entities: draft_entity_id уже занят или повторяется: {did!r}")
            seen_new_ent.add(did)
            await self._resolve_storage_type_for_note_family(
                ent.entity_type,
                ent.entity_subtype,
                ns_for_types,
            )
            appended_entities.append(ent)

        entities = [*entities, *appended_entities]
        existing_entity_ids.update(seen_new_ent)

        note_row = draft.note
        by_draft_entity = {e.draft_entity_id: i for i, e in enumerate(entities)}
        seen_entity_patch: set[str] = set()
        for p in body.patch_entities:
            if p.draft_entity_id in seen_entity_patch:
                raise ValueError(
                    f"Дублирующийся draft_entity_id в patch_entities: {p.draft_entity_id}"
                )
            seen_entity_patch.add(p.draft_entity_id)
            idx = by_draft_entity.get(p.draft_entity_id)
            if idx is None:
                if (
                    note_row is not None
                    and note_row.draft_entity_id
                    and p.draft_entity_id == note_row.draft_entity_id
                ):
                    ent = note_row
                    updates: dict[str, Any] = {}
                    if p.entity_type is not None:
                        et = str(p.entity_type).strip()
                        if not et:
                            raise ValueError(
                                f"patch_entities: пустой entity_type не допускается "
                                f"(draft_entity_id={p.draft_entity_id})"
                            )
                        updates["entity_type"] = et
                    if p.name is not None:
                        updates["name"] = p.name
                    if p.description is not None:
                        updates["description"] = p.description
                    if p.entity_subtype is not None:
                        st = str(p.entity_subtype).strip()
                        updates["entity_subtype"] = st if st else None
                    if p.note_date is not None:
                        updates["note_date"] = p.note_date
                    if p.due_date is not None:
                        updates["due_date"] = p.due_date
                    if p.priority is not None:
                        updates["priority"] = p.priority
                    if p.assignees is not None:
                        updates["assignees"] = p.assignees
                    if p.attributes is not None:
                        merged = dict(ent.attributes or {})
                        merged.update(p.attributes)
                        updates["attributes"] = merged
                    if updates:
                        note_row = ent.model_copy(update=updates)
                    continue
                raise ValueError(f"Нет сущности с draft_entity_id={p.draft_entity_id}")
            ent = entities[idx]
            updates: dict[str, Any] = {}
            if p.entity_type is not None:
                et = str(p.entity_type).strip()
                if not et:
                    raise ValueError(
                        f"patch_entities: пустой entity_type не допускается "
                        f"(draft_entity_id={p.draft_entity_id})"
                    )
                updates["entity_type"] = et
            if p.name is not None:
                updates["name"] = p.name
            if p.description is not None:
                updates["description"] = p.description
            if p.entity_subtype is not None:
                st = str(p.entity_subtype).strip()
                updates["entity_subtype"] = st if st else None
            if p.note_date is not None:
                updates["note_date"] = p.note_date
            if p.due_date is not None:
                updates["due_date"] = p.due_date
            if p.priority is not None:
                updates["priority"] = p.priority
            if p.assignees is not None:
                updates["assignees"] = p.assignees
            if p.attributes is not None:
                merged = dict(ent.attributes or {})
                merged.update(p.attributes)
                updates["attributes"] = merged
            if updates:
                entities[idx] = ent.model_copy(update=updates)

        by_rel = {r.draft_relationship_id: i for i, r in enumerate(rels)}
        seen_rel_patch: set[str] = set()
        for p in body.patch_relationships:
            if p.draft_relationship_id in seen_rel_patch:
                raise ValueError(
                    f"Дублирующийся draft_relationship_id в patch_relationships: "
                    f"{p.draft_relationship_id}"
                )
            seen_rel_patch.add(p.draft_relationship_id)
            idx = by_rel.get(p.draft_relationship_id)
            if idx is None:
                raise ValueError(f"Нет связи с draft_relationship_id={p.draft_relationship_id}")
            rel = rels[idx]
            ru: dict[str, Any] = {}
            if p.weight is not None:
                ru["weight"] = p.weight
            if p.confidence is not None:
                ru["confidence"] = p.confidence
            if p.attributes is not None:
                rmerged = dict(rel.attributes or {})
                rmerged.update(p.attributes)
                ru["attributes"] = rmerged
            if ru:
                rels[idx] = rel.model_copy(update=ru)

        rel_tuple_seen: set[tuple[str, str, str]] = {
            (r.source_draft_entity_id, r.target_draft_entity_id, r.relationship_type)
            for r in rels
        }
        existing_rel_ids: set[str] = {r.draft_relationship_id for r in rels}

        valid_rel_type_ids = {
            t.type_id
            for t in await self._relationship_type_repo.get_all_for_company(include_system=True)
        }

        seen_new_rel: set[str] = set()
        appended_rels: list[AIAnalysisRelationshipDraft] = []
        for rel in body.add_relationships:
            rid = rel.draft_relationship_id
            if not rid:
                raise ValueError("add_relationships: отсутствует draft_relationship_id")
            if rid in existing_rel_ids or rid in seen_new_rel:
                raise ValueError(
                    f"add_relationships: draft_relationship_id уже занят или повторяется: {rid!r}"
                )
            seen_new_rel.add(rid)
            tup = (
                rel.source_draft_entity_id,
                rel.target_draft_entity_id,
                rel.relationship_type,
            )
            if tup in rel_tuple_seen:
                raise ValueError(
                    f"add_relationships: дублируется связь source={tup[0]!r} "
                    f"target={tup[1]!r} type={tup[2]!r}"
                )
            if rel.relationship_type not in valid_rel_type_ids:
                raise ValueError(f"add_relationships: неизвестный тип связи: {rel.relationship_type}")
            if rel.source_draft_entity_id not in existing_entity_ids:
                raise ValueError(
                    f"add_relationships: неизвестный source_draft_entity_id: "
                    f"{rel.source_draft_entity_id}"
                )
            if rel.target_draft_entity_id not in existing_entity_ids:
                raise ValueError(
                    f"add_relationships: неизвестный target_draft_entity_id: "
                    f"{rel.target_draft_entity_id}"
                )
            rel_tuple_seen.add(tup)
            existing_rel_ids.add(rid)
            appended_rels.append(rel)

        rels = [*rels, *appended_rels]

        next_draft = AIAnalysisDraftStored(
            draft_version=draft.draft_version + 1,
            updated_at=datetime.now(UTC).isoformat(),
            note=note_row,
            entities=entities,
            relationships=rels,
            known_entity_id_map=dict(draft.known_entity_id_map),
        )

        attrs = dict(note.attributes or {})
        attrs["ai_analysis_draft"] = next_draft.model_dump(mode="json")
        await self.update_entity(note_id, {"attributes": attrs})
        return next_draft

    async def _persist_analysis_draft_entity_row(
        self,
        ent: AIExtractedEntity,
        namespace: str,
        merge_target_locks: dict[str, asyncio.Lock],
        source_entity_id: str | None = None,
    ) -> tuple[str, str, Literal["created", "updated"]]:
        """Одна строка черновика: create или merge в БД и RAG (без ретраев)."""
        did = ent.draft_entity_id
        if not did:
            raise ValueError("Сущность без draft_entity_id в сохранённом черновике")

        def _lock_for_merge_target(entity_id: str) -> asyncio.Lock:
            if entity_id not in merge_target_locks:
                merge_target_locks[entity_id] = asyncio.Lock()
            return merge_target_locks[entity_id]

        if ent.dedup_action == "merge":
            existing_id = ent.dedup_existing_id
            if not existing_id:
                raise ValueError(
                    f"dedup_action=merge требует dedup_existing_id (draft_entity_id={did})"
                )
            async with _lock_for_merge_target(existing_id):
                existing_row = await self._entity_repo.get(existing_id)
                if not existing_row:
                    raise ValueError(f"dedup_existing_id не найден в БД: {existing_id}")
                merged_attrs = _strip_draft_only_entity_attrs(
                    {**(existing_row.attributes or {}), **(ent.attributes or {})}
                )
                raw = ent.model_dump()
                await self.update_entity(
                    existing_id,
                    {
                        "name": ent.name,
                        "description": ent.description,
                        "entity_subtype": ent.entity_subtype,
                        "attributes": merged_attrs,
                        "priority": raw.get("priority"),
                        "assignees": raw.get("assignees") or [],
                        "note_date": self._parse_optional_date_iso(raw.get("note_date")),
                        "due_date": self._parse_optional_date_iso(raw.get("due_date")),
                    },
                )
            return (did, existing_id, "updated")
        if ent.dedup_action in (None, "create"):
            created = await self._create_entity_from_draft_row(ent, namespace, source_entity_id)
            return (did, created.entity_id, "created")
        raise ValueError(f"Неизвестный dedup_action={ent.dedup_action!r} (draft_entity_id={did})")

    async def _apply_analysis_draft_entity_rows_with_retries(
        self,
        entities: list[AIExtractedEntity],
        namespace: str,
        source_entity_id: str | None = None,
    ) -> tuple[dict[str, str], list[str], list[str]]:
        """
        Параллельный проход по списку; неуспешные строки повторяются до ANALYSIS_DRAFT_APPLY_MAX_ROUNDS.
        Возвращает id_map по draft_entity_id, списки created/updated в порядке следования в entities.
        """
        merge_target_locks: dict[str, asyncio.Lock] = {}
        pending = list(entities)
        last_error_by_draft: dict[str, Exception] = {}
        id_fragment: dict[str, str] = {}
        kind_by_draft: dict[str, Literal["created", "updated"]] = {}

        for _ in range(ANALYSIS_DRAFT_APPLY_MAX_ROUNDS):
            if not pending:
                break
            results = await asyncio.gather(
                *[
                    self._persist_analysis_draft_entity_row(
                        ent, namespace, merge_target_locks, source_entity_id
                    )
                    for ent in pending
                ],
                return_exceptions=True,
            )
            next_pending: list[AIExtractedEntity] = []
            for ent, res in zip(pending, results):
                did = ent.draft_entity_id
                if not did:
                    raise ValueError("Сущность без draft_entity_id в сохранённом черновике")
                if isinstance(res, Exception):
                    last_error_by_draft[did] = res
                    next_pending.append(ent)
                    continue
                if isinstance(res, BaseException):
                    raise res
                out_did, real_id, kind = res
                id_fragment[out_did] = real_id
                kind_by_draft[out_did] = kind
            pending = next_pending

        if pending:
            created_real_ids = [
                id_fragment[did] for did in id_fragment if kind_by_draft.get(did) == "created"
            ]
            for eid in reversed(created_real_ids):
                ok = await self.delete_entity(eid)
                if not ok:
                    raise RuntimeError(
                        f"Компенсация частичного apply черновика: сущность {eid} не удалена"
                    )
            if created_real_ids:
                logger.warning(
                    "apply черновика: откат %s частично созданных сущностей из-за ошибок в других строках",
                    len(created_real_ids),
                )
            failures: list[tuple[str, str | None, str | None, str]] = []
            for ent in pending:
                did = ent.draft_entity_id or ""
                exc = last_error_by_draft.get(did)
                msg = str(exc) if exc else "unknown error"
                failures.append((did, ent.name, ent.entity_type, msg))
            raise ApplyAnalysisDraftEntityFailuresError(failures)

        created_entity_ids: list[str] = []
        updated_entity_ids: list[str] = []
        for ent in entities:
            did = ent.draft_entity_id
            if not did or did not in id_fragment:
                continue
            if kind_by_draft.get(did) == "created":
                created_entity_ids.append(id_fragment[did])
            elif kind_by_draft.get(did) == "updated":
                updated_entity_ids.append(id_fragment[did])

        return (id_fragment, created_entity_ids, updated_entity_ids)

    async def apply_analysis_draft(self, note_id: str) -> AIAnalysisDraftApplyResult:
        note, draft = await self._load_analysis_draft_from_note(note_id)
        namespace = self._resolve_namespace_for_write(note.namespace)

        all_types = await self._relationship_type_repo.get_all_for_company(include_system=True)
        valid_type_ids = {t.type_id for t in all_types}

        draft_entity_ids = {e.draft_entity_id for e in draft.entities if e.draft_entity_id}
        if draft.note is not None and draft.note.draft_entity_id:
            draft_entity_ids.add(draft.note.draft_entity_id)
        # known entities не в draft.entities, но их draft_entity_id валидны
        draft_entity_ids.update(draft.known_entity_id_map.keys())

        rel_tuples: set[tuple[str, str, str]] = set()
        for rel in draft.relationships:
            t = (
                rel.source_draft_entity_id,
                rel.target_draft_entity_id,
                rel.relationship_type,
            )
            if t in rel_tuples:
                raise ValueError(
                    f"В черновике дублируется связь source_draft={t[0]!r} "
                    f"target_draft={t[1]!r} type={t[2]!r}"
                )
            rel_tuples.add(t)
            if rel.relationship_type not in valid_type_ids:
                raise ValueError(f"Неизвестный тип связи: {rel.relationship_type}")
            if rel.source_draft_entity_id not in draft_entity_ids:
                raise ValueError(
                    f"Связь ссылается на неизвестный source_draft_entity_id: "
                    f"{rel.source_draft_entity_id}"
                )
            if rel.target_draft_entity_id not in draft_entity_ids:
                raise ValueError(
                    f"Связь ссылается на неизвестный target_draft_entity_id: "
                    f"{rel.target_draft_entity_id}"
                )

        id_map: dict[str, str] = {}
        if draft.note is not None and draft.note.draft_entity_id:
            id_map[draft.note.draft_entity_id] = note_id
        # known entities (member, company) разрешаются напрямую без update_entity
        id_map.update(draft.known_entity_id_map)

        (
            id_fragment,
            created_entity_ids,
            updated_entity_ids,
        ) = await self._apply_analysis_draft_entity_rows_with_retries(
            draft.entities,
            namespace,
            source_entity_id=note_id,
        )
        id_map.update(id_fragment)

        seen_resolved_edges: set[tuple[str, str, str]] = set()
        unique_draft_rels: list[AIAnalysisRelationshipDraft] = []
        for rel in draft.relationships:
            src = id_map[rel.source_draft_entity_id]
            tgt = id_map[rel.target_draft_entity_id]
            key = (src, tgt, rel.relationship_type)
            if key in seen_resolved_edges:
                continue
            seen_resolved_edges.add(key)
            unique_draft_rels.append(rel)

        async def create_one_relationship(rel: AIAnalysisRelationshipDraft) -> str | None:
            src = id_map[rel.source_draft_entity_id]
            tgt = id_map[rel.target_draft_entity_id]
            row = Relationship(
                relationship_id=str(uuid.uuid4()),
                source_entity_id=src,
                target_entity_id=tgt,
                relationship_type=rel.relationship_type,
                namespace=namespace,
                weight=rel.weight,
                confidence=rel.confidence,
                attributes=dict(rel.attributes or {}),
                company_id=self._get_company_id(),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            saved = await self._relationship_repo.ensure_edge(row)
            if saved.relationship_id == row.relationship_id:
                return saved.relationship_id
            return None

        rel_results = await asyncio.gather(
            *[create_one_relationship(rel) for rel in unique_draft_rels]
        )
        created_relationship_ids = [rid for rid in rel_results if rid is not None]

        attrs = dict(note.attributes or {})
        attrs.pop("ai_analysis_last_error", None)
        attrs.pop("ai_analysis_last_error_at", None)
        note_draft = draft.note
        if note_draft is not None and isinstance(note_draft.description, str):
            summary_text = note_draft.description.strip()
            if summary_text:
                attrs["ai_summary"] = summary_text
                attrs["ai_summary_generated_at"] = datetime.now(UTC).isoformat()
                entity_names = [
                    e.name
                    for e in (draft.entities or [])
                    if isinstance(getattr(e, "name", None), str) and e.name.strip()
                ]
                if entity_names:
                    attrs["ai_summary_entities"] = entity_names[:8]
        if "ai_analysis_draft" in attrs:
            del attrs["ai_analysis_draft"]
        attrs["ai_analysis_applied_at"] = datetime.now(UTC).isoformat()
        await self.update_entity(note_id, {"attributes": attrs})

        return AIAnalysisDraftApplyResult(
            created_entity_ids=created_entity_ids,
            updated_entity_ids=updated_entity_ids,
            created_relationship_ids=created_relationship_ids,
        )

    async def _resolve_storage_type_for_note_family(
        self,
        leaf_type_id: str,
        initial_subtype: str | None,
        namespace: str,
    ) -> tuple[str, str | None]:
        """
        Типы из ветки note в справочнике entity_types (meeting, call, …) в БД храним как
        entity_type=note и entity_subtype=<type_id>, чтобы строки попадали в /crm/notes и
        общую логику заметок (edges, summary, WS).
        """
        if leaf_type_id == NOTE_ROOT_ENTITY_TYPE_ID:
            return (NOTE_ROOT_ENTITY_TYPE_ID, initial_subtype)

        seen: set[str] = set()
        cur: str | None = leaf_type_id
        while cur and cur not in seen:
            seen.add(cur)
            row = await self._entity_type_repo.get_by_type_id(cur, namespace=namespace)
            if row is None:
                raise ValueError(f"Entity type not found: {leaf_type_id}")
            if row.type_id == NOTE_ROOT_ENTITY_TYPE_ID:
                return (NOTE_ROOT_ENTITY_TYPE_ID, leaf_type_id)
            cur = row.parent_type_id

        return (leaf_type_id, initial_subtype)

    async def _list_by_cursor_note_family_args(
        self,
        entity_type: str | None,
        entity_subtype: str | None,
        namespace: str | None = None,
    ) -> tuple[str | None, bool, list[str] | None]:
        """
        Для ленты заметок (entity_type=note без subtype) учитываем и канонические строки
        (entity_type=note), и устаревшие (type_id потомка в колонке entity_type).
        """
        if entity_type != NOTE_ROOT_ENTITY_TYPE_ID or entity_subtype is not None:
            return entity_type, False, None
        ns = self._normalize_namespace(namespace)
        if ns is None:
            return NOTE_ROOT_ENTITY_TYPE_ID, False, None
        family = await self._collect_note_family_type_ids(ns)
        legacy = sorted(t for t in family if t != NOTE_ROOT_ENTITY_TYPE_ID)
        return None, True, legacy

    async def _collect_note_family_type_ids(self, namespace: str) -> set[str]:
        """Возвращает множество type_id, принадлежащих ветке note (включая note и дочерние типы)."""
        all_types = await self._entity_type_repo.get_all_for_company(
            include_system=True,
            namespace=namespace,
        )
        children_by_parent: dict[str | None, list[str]] = {}
        for et in all_types:
            children_by_parent.setdefault(et.parent_type_id, []).append(et.type_id)

        result: set[str] = {NOTE_ROOT_ENTITY_TYPE_ID}
        queue = [NOTE_ROOT_ENTITY_TYPE_ID]
        while queue:
            parent = queue.pop()
            for child in children_by_parent.get(parent, []):
                if child not in result:
                    result.add(child)
                    queue.append(child)
        return result

    async def _create_entity_from_draft_row(
        self,
        ent: AIExtractedEntity,
        namespace: str,
        source_entity_id: str | None = None,
    ) -> CRMEntity:
        raw = ent.model_dump()
        storage_type, storage_subtype = await self._resolve_storage_type_for_note_family(
            ent.entity_type,
            ent.entity_subtype,
            namespace,
        )
        note_date = self._parse_optional_date_iso(raw.get("note_date"))
        if storage_type == NOTE_ROOT_ENTITY_TYPE_ID and note_date is None:
            note_date = datetime.now(UTC).date()

        return await self.create_entity(
            entity_type=storage_type,
            name=ent.name,
            description=ent.description,
            entity_subtype=storage_subtype,
            namespace=namespace,
            attributes=_strip_draft_only_entity_attrs(raw.get("attributes")),
            tags=raw.get("tags") or [],
            note_date=note_date,
            due_date=self._parse_optional_date_iso(raw.get("due_date")),
            priority=raw.get("priority"),
            assignees=raw.get("assignees") or [],
            source_entity_id=source_entity_id,
        )

    @staticmethod
    def _parse_optional_date_iso(value: str | None) -> date | None:
        if value is None or value == "":
            return None
        return date.fromisoformat(value)

    async def analyze_text_with_ai(
        self,
        request: AIAnalyzeRequest,
        check_duplicates: bool = True,
        note_id: str | None = None,
        progress_cb: Callable[[str, int, str], Awaitable[None]] | None = None,
    ) -> AIAnalyzeResponse:
        """
        AI анализ текста с составными промптами.

        Строит промпт из:
        1. EntityType.prompt для базовых типов (note, task)
        2. EntityType.prompt для подтипов (meeting, call)
        3. RelationshipType.prompt для связей (mentions, works_for)

        Args:
            request: Запрос на анализ
            check_duplicates: Проверять ли дубликаты (по умолчанию True)
            note_id: ID заметки для сохранения черновика
            progress_cb: Колбэк прогресса (stage, pct, message)
        """
        namespace = self._resolve_namespace_for_write(request.namespace)
        await self._ensure_namespace_exists(namespace)
        entity_types = await self._load_all_entity_types_for_namespace(namespace)
        relationship_types = await self._relationship_type_repo.get_with_prompts()

        prompt = self._build_composite_prompt(
            entity_types,
            relationship_types,
            request.extract_entity_types,
            request.extract_relationship_types,
        )
        ctx = get_context()
        known_entities: list[dict[str, Any]] = []
        _known_entity_rows: list[CRMEntity] = []
        if ctx and ctx.user:
            company_id = self._get_company_id()
            member_entity_id = await self._user_person_service.get_or_create_person_entity_id(
                ctx.user.user_id,
                company_id,
            )
            member_entity = await self._entity_repo.get(member_entity_id)
            if member_entity:
                known_entities.append(
                    {
                        "entity_id": member_entity.entity_id,
                        "name": member_entity.name,
                        "type": "member",
                        "description": self._effective_description_for_analyze_inject(
                            member_entity
                        ),
                    }
                )
                _known_entity_rows.append(member_entity)

            company_entities = await self._entity_repo.find_by_attribute(
                entity_type=COMPANY_ENTITY_TYPE,
                attribute_key=PLATFORM_COMPANY_ID_ATTR,
                attribute_value=company_id,
                company_id=company_id,
            )
            if company_entities:
                ce = company_entities[0]
                known_entities.append(
                    {
                        "entity_id": ce.entity_id,
                        "name": ce.name,
                        "type": "company",
                        "description": self._effective_description_for_analyze_inject(ce),
                    }
                )
                _known_entity_rows.append(ce)

        resolved_for_note: list[str] = []
        if note_id:
            resolved_for_note = await self.resolved_entity_ids_for_note(note_id)
            for eid in resolved_for_note:
                if any(ke.get("entity_id") == eid for ke in known_entities):
                    continue
                row = await self._entity_repo.get(eid)
                if row is None:
                    continue
                known_entities.append(
                    {
                        "entity_id": row.entity_id,
                        "name": row.name,
                        "type": row.entity_type,
                        "description": self._effective_description_for_analyze_inject(row),
                    }
                )
                _known_entity_rows.append(row)

        prefix_parts: list[str] = []
        anchor_types = [et for et in entity_types if et.is_context_anchor]
        if anchor_types:
            anchor_lines = "\n".join(f"- {et.name} ({et.type_id})" for et in anchor_types)
            prefix_parts.append(
                "ТИПЫ-ЯКОРЯ КОНТЕКСТА (привязка заметок к сделке, лиду и т.д.):\n" + anchor_lines
            )
        if prefix_parts:
            prompt = "\n\n".join(prefix_parts) + "\n\n" + prompt

        if progress_cb:
            await progress_cb("analyzing", 57, "Извлечение данных")
        t_analyze = time.perf_counter()
        state = await self._call_ai_agent(
            text=request.text,
            prompt=prompt,
            entity_types=entity_types,
            relationship_types=relationship_types,
            known_entities=known_entities if known_entities else None,
            namespace=namespace,
        )
        logger.info(
            "crm.analyze.flow_llm_ms=%.1f",
            (time.perf_counter() - t_analyze) * 1000,
        )

        if progress_cb:
            await progress_cb("processing_results", 70, "Обработка результатов")
        mentioned_only = (
            list(request.mentioned_entity_ids) if request.mentioned_entity_ids else None
        )

        await self._inject_mentioned_entities_into_analyze_state(
            state,
            mentioned_only,
            namespace,
        )

        if check_duplicates and state.entities:
            if progress_cb:
                await progress_cb("deduplicating", 76, "Проверка дубликатов")
            t_dedup = time.perf_counter()
            dedup_results = await self._deduplicate_entities(
                extracted_entities=state.entities,
                namespace=namespace,
            )
            logger.info(
                "crm.analyze.dedup_phase_ms=%.1f entities=%s",
                (time.perf_counter() - t_dedup) * 1000,
                len(state.entities),
            )

            for i, entity in enumerate(state.entities):
                if i < len(dedup_results):
                    result = dedup_results[i]
                    entity.dedup_action = result.action
                    entity.dedup_confidence = result.confidence
                    if result.is_duplicate:
                        entity.dedup_existing_id = result.existing_entity_id
                        entity.dedup_existing_name = result.existing_entity_name

        injected_known: list[AIExtractedEntity] = []
        if _known_entity_rows:
            injected_known = self._inject_known_entities_into_analyze_state(
                state, _known_entity_rows
            )

        # Сохраняем dedup_existing_id до model_copy в _assign_draft_ids_to_note_and_entities
        injected_known_existing_ids: set[str] = {
            e.dedup_existing_id for e in injected_known if e.dedup_existing_id
        }

        if progress_cb:
            await progress_cb("building_draft", 83, "Формирование черновика")
        self._assign_draft_ids_to_note_and_entities(state)
        draft_relationships = self._build_relationship_drafts_from_extracted(state)

        # Собираем маппинг draft_entity_id → real entity_id для known entities
        # и удаляем их из state.entities — они не должны отображаться в UI анализа.
        # Фильтруем по dedup_existing_id, а не по id() — _assign_draft_ids создаёт
        # новые объекты через model_copy, поэтому id() сравнение не работает.
        known_entity_id_map: dict[str, str] = {}
        if injected_known_existing_ids:
            for e in state.entities:
                if e.dedup_existing_id in injected_known_existing_ids and e.draft_entity_id:
                    known_entity_id_map[e.draft_entity_id] = e.dedup_existing_id
            state.entities = [
                e for e in state.entities if e.dedup_existing_id not in injected_known_existing_ids
            ]

        ai_result = AIAnalyzeResponse(
            note=state.note,
            entities=state.entities,
            relationships=draft_relationships,
            attachment_summaries=state.attachment_summaries,
            known_entity_id_map=known_entity_id_map,
        )
        if note_id:
            await self._persist_analysis_draft_to_note(note_id, ai_result)

        return ai_result

    async def _load_all_entity_types_for_namespace(self, namespace: str) -> list[EntityType]:
        page_limit = 200
        offset = 0
        collected: list[EntityType] = []
        while True:
            batch = await self._entity_type_repo.get_all_for_company(
                namespace=namespace,
                limit=page_limit,
                offset=offset,
            )
            if not batch:
                return collected
            collected.extend(batch)
            if len(batch) < page_limit:
                return collected
            offset += page_limit

    def _build_composite_prompt(
        self,
        entity_types: list[EntityType],
        relationship_types: list[RelationshipType],
        extract_entity_types: list[str] | None,
        extract_relationship_types: list[str] | None,
    ) -> str:
        """Строит составной промпт из типов"""
        prompt_parts = [
            "Проанализируй текст и извлеки следующие сущности и связи:",
            "",
            "ТИПЫ СУЩНОСТЕЙ:",
        ]

        for et in entity_types:
            if not et.extractable:
                continue
            if extract_entity_types and et.type_id not in extract_entity_types:
                continue

            if et.prompt:
                prompt_parts.append(f"\n{et.name} ({et.type_id}):")
                prompt_parts.append(et.prompt)
                fields = _extract_entity_type_fields(et)
                if fields:
                    prompt_parts.append("  Поля attributes:")
                    for field in fields:
                        req_mark = " [обязательное]" if field["required"] else ""
                        desc_part = f": {field['description']}" if field.get("description") else ""
                        values_part = (
                            f" Допустимые значения: {field['values']}"
                            if field.get("values")
                            else ""
                        )
                        prompt_parts.append(
                            f"  - `{field['name']}` ({field['label']}){req_mark}{desc_part}{values_part}"
                        )

        prompt_parts.append("\nТИПЫ СВЯЗЕЙ:")

        for rt in relationship_types:
            if extract_relationship_types and rt.type_id not in extract_relationship_types:
                continue

            if rt.prompt:
                prompt_parts.append(f"\n{rt.name} ({rt.type_id}):")
                prompt_parts.append(rt.prompt)

        return "\n".join(prompt_parts)

    async def _inject_mentioned_entities_into_analyze_state(
        self,
        state: _AnalyzePipelineState,
        mentioned_entity_ids: list[str] | None,
        namespace: str,
    ) -> None:
        """
        Связи в ответе LLM ссылаются на (type, name) строк черновика.
        Упомянутые через @ сущности из БД подмешиваются как строки, чтобы резолв концов связи не падал.
        """
        if not mentioned_entity_ids:
            return
        company_id = self._get_company_id()

        def row_key(entity: AIExtractedEntity) -> tuple[str, str]:
            return (
                entity.entity_type.lower().strip(),
                self._normalize_name_for_relationship_key(entity.name),
            )

        occupied: set[tuple[str, str]] = set()
        if state.note is not None:
            occupied.add(row_key(state.note))
        for ent in state.entities:
            occupied.add(row_key(ent))

        for mid in mentioned_entity_ids:
            row = await self._entity_repo.get(mid)
            if not row:
                raise ValueError(f"Упомянутая сущность не найдена: {mid}")
            if row.company_id != company_id:
                raise ValueError(f"Упомянутая сущность {mid} принадлежит другой компании")
            if row.namespace != namespace:
                raise ValueError(
                    f"Упомянутая сущность {mid} в namespace {row.namespace!r}, "
                    f"ожидался {namespace!r}"
                )
            k = (
                row.entity_type.lower().strip(),
                self._normalize_name_for_relationship_key(row.name),
            )
            if k in occupied:
                continue
            occupied.add(k)
            desc = self._effective_description_for_analyze_inject(row)
            payload = {
                "entity_type": row.entity_type,
                "name": row.name,
                "description": desc,
                "attributes": dict(row.attributes or {}),
                "entity_subtype": row.entity_subtype,
            }
            state.entities.append(
                AIExtractedEntity.model_validate(self._normalize_entity_payload(payload))
            )

    def _inject_known_entities_into_analyze_state(
        self,
        state: _AnalyzePipelineState,
        entity_rows: list[CRMEntity],
    ) -> list[AIExtractedEntity]:
        """
        Добавляет known entities (member, company) в state.entities как синтетические
        черновые записи с dedup_action="merge". Это позволяет резолверу связей
        _build_relationship_drafts_from_extracted найти их в key_index и не дропать
        AI-созданные связи к автору/компании. Вызывается после dedup, до assign_draft_ids.

        Возвращает список добавленных синтетических записей — caller должен удалить их
        из state.entities после резолва связей, чтобы они не попали в черновик и UI.
        """
        occupied: set[tuple[str, str]] = set()
        if state.note is not None:
            occupied.add(
                (
                    state.note.entity_type.lower().strip(),
                    self._normalize_name_for_relationship_key(state.note.name),
                )
            )
        for ent in state.entities:
            occupied.add(
                (
                    ent.entity_type.lower().strip(),
                    self._normalize_name_for_relationship_key(ent.name),
                )
            )

        injected: list[AIExtractedEntity] = []
        for row in entity_rows:
            k = (
                row.entity_type.lower().strip(),
                self._normalize_name_for_relationship_key(row.name),
            )
            if k in occupied:
                continue
            occupied.add(k)
            payload = {
                "entity_type": row.entity_type,
                "name": row.name,
                "description": self._effective_description_for_analyze_inject(row),
                "attributes": dict(row.attributes or {}),
                "entity_subtype": row.entity_subtype,
            }
            synthetic = AIExtractedEntity.model_validate(self._normalize_entity_payload(payload))
            synthetic.dedup_action = "merge"
            synthetic.dedup_existing_id = row.entity_id
            state.entities.append(synthetic)
            injected.append(synthetic)
        return injected

    async def _call_ai_agent(
        self,
        text: str,
        prompt: str,
        entity_types: list[EntityType],
        relationship_types: list[RelationshipType],
        known_entities: list[dict[str, Any]] | None = None,
        *,
        namespace: str,
    ) -> _AnalyzePipelineState:
        """Вызывает AI agent через A2A API для анализа"""
        from core.config import get_settings

        settings = get_settings()

        extractable_entity_types = [et for et in entity_types if et.prompt and et.extractable]
        variables = {
            **_crm_llm_interface_language_vars(),
            "text": text,
            "entity_types": [
                {
                    "type": et.type_id,
                    "prompt": et.prompt or "",
                    "fields": _extract_entity_type_fields(et),
                }
                for et in extractable_entity_types
            ],
            "relationship_types": [
                {"type": rt.type_id, "prompt": rt.prompt or ""}
                for rt in relationship_types
                if rt.prompt
            ],
        }

        if known_entities:
            variables["known_entities"] = known_entities

        flows_base_url = settings.server.get_flows_service_url().rstrip("/")

        response = await self._a2a_client.send_task(
            base_url=f"{flows_base_url}/flows/api/v1/crm",
            content=text,
            branch_id="analyze",
            metadata={"variables": variables},
        )

        result_data = self._extract_data_from_a2a_response(response)
        normalized_result = self._normalize_analyze_result(result_data)
        self._validate_analyze_entity_descriptions(normalized_result)

        note_obj: AIExtractedEntity | None = None
        note_data = normalized_result.get(NOTE_ROOT_ENTITY_TYPE_ID)
        if isinstance(note_data, dict):
            note_obj = AIExtractedEntity.model_validate(self._normalize_entity_payload(note_data))

        entities_data = normalized_result.get("entities")
        if not isinstance(entities_data, list):
            entities_data = []
        entity_list: list[AIExtractedEntity] = []
        note_family_type_ids = await self._collect_note_family_type_ids(namespace)
        note_family_lc = {str(t).lower() for t in note_family_type_ids}
        for i, raw_ent in enumerate(entities_data):
            if not isinstance(raw_ent, dict):
                raise ValueError(f"entities[{i}] должен быть объектом")
            parsed = AIExtractedEntity.model_validate(self._normalize_entity_payload(raw_ent))
            if parsed.entity_type.lower() in note_family_lc:
                logger.warning(
                    "analyze: LLM вернул сущность note-семейства (type=%r, name=%r) "
                    "в массиве entities — пропущена (заметка уже представлена в поле note)",
                    parsed.entity_type,
                    parsed.name,
                )
                continue
            entity_list.append(parsed)

        rels_data = normalized_result.get("relationships")
        if not isinstance(rels_data, list):
            rels_data = []
        rel_extracted: list[AIAnalyzeRelationshipExtracted] = []
        for i, raw_rel in enumerate(rels_data):
            if not isinstance(raw_rel, dict):
                raise ValueError(f"relationships[{i}] должен быть объектом")
            rel_extracted.append(AIAnalyzeRelationshipExtracted.model_validate(raw_rel))

        attachment_summaries: list[dict[str, Any]] = []
        summaries_data = normalized_result.get("attachment_summaries")
        if isinstance(summaries_data, list):
            for item in summaries_data:
                if isinstance(item, dict) and item.get("filename") and item.get("summary"):
                    attachment_summaries.append(
                        {
                            "filename": str(item["filename"]),
                            "summary": str(item["summary"]),
                        }
                    )

        return _AnalyzePipelineState(
            note=note_obj,
            entities=entity_list,
            relationships_extracted=rel_extracted,
            attachment_summaries=attachment_summaries,
        )

    def _normalize_entity_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Приводит entity payload к ожидаемому контракту CRM."""
        normalized = dict(payload)
        if "entity_type" not in normalized and "type" in normalized:
            normalized["entity_type"] = normalized["type"]
        return normalized

    def _normalize_analyze_result(self, result_data: dict[str, Any]) -> dict[str, Any]:
        """Нормализует ответ analyze от flows перед Pydantic-валидацией."""
        normalized = dict(result_data)

        nested = normalized.get("structured_output")
        if isinstance(nested, dict):
            for key in (
                NOTE_ROOT_ENTITY_TYPE_ID,
                "entities",
                "relationships",
                "metadata",
                "attachment_summaries",
            ):
                if key in nested:
                    normalized[key] = nested[key]

        note_data = normalized.get(NOTE_ROOT_ENTITY_TYPE_ID)
        if isinstance(note_data, dict):
            normalized[NOTE_ROOT_ENTITY_TYPE_ID] = self._normalize_entity_payload(note_data)

        entities_data = normalized.get("entities")
        if isinstance(entities_data, list):
            normalized["entities"] = [
                self._normalize_entity_payload(entity) if isinstance(entity, dict) else entity
                for entity in entities_data
            ]

        return normalized

    def _validate_analyze_entity_descriptions(self, normalized: dict[str, Any]) -> None:
        """Ответ analyze должен содержать непустые описания для note (если не null) и каждой entity."""
        min_len = _ANALYZE_ENTITY_DESCRIPTION_MIN_LEN
        note_data = normalized.get(NOTE_ROOT_ENTITY_TYPE_ID)
        if isinstance(note_data, dict):
            desc = note_data.get("description")
            if not isinstance(desc, str) or len(desc.strip()) < min_len:
                raise ValueError(
                    f"Поле {NOTE_ROOT_ENTITY_TYPE_ID}.description обязательно и должно содержать не менее {min_len} непробельных символов"
                )
        entities_data = normalized.get("entities")
        if not isinstance(entities_data, list):
            return
        for i, ent in enumerate(entities_data):
            if not isinstance(ent, dict):
                raise ValueError(f"entities[{i}] должен быть объектом")
            desc = ent.get("description")
            if not isinstance(desc, str) or len(desc.strip()) < min_len:
                raise ValueError(
                    f"Поле entities[{i}].description обязательно и должно содержать не менее {min_len} непробельных символов"
                )

    def _extract_data_from_a2a_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """
        Извлекает структурированные данные из A2A response.

        Поддерживает:
        1. data parts в artifacts
        2. text parts с JSON в markdown (```json ... ```)
        """
        # A2AClient возвращает нормализованный ответ с полем raw
        raw_response = response.get("raw", response)

        if "result" not in raw_response:
            return {}

        task_result = raw_response["result"]
        artifacts = task_result.get("artifacts")
        if artifacts is None:
            artifacts = []

        if not artifacts:
            plain = (response.get("response") or "").strip()
            if plain:
                extracted = self._extract_json_from_text(plain)
                if extracted:
                    return extracted
            history = task_result.get("history")
            if isinstance(history, list):
                for message in reversed(history):
                    if not isinstance(message, dict):
                        continue
                    parts = message.get("parts")
                    if not isinstance(parts, list):
                        continue
                    for part in parts:
                        if not isinstance(part, dict):
                            continue
                        part_kind = part.get("kind") or part.get("type")
                        if part_kind == "text":
                            text = part.get("text")
                            if isinstance(text, str) and text.strip():
                                extracted = self._extract_json_from_text(text)
                                if extracted:
                                    return extracted
                        elif part_kind == "data":
                            data = part.get("data")
                            if isinstance(data, dict):
                                if any(
                                    key in data
                                    for key in (
                                        "entities",
                                        "relationships",
                                        NOTE_ROOT_ENTITY_TYPE_ID,
                                        "summary",
                                        "structured_output",
                                        "is_duplicate",
                                        "decisions",
                                        "action",
                                        "patch_entities",
                                    )
                                ):
                                    return data
            return {}

        for artifact in artifacts:
            if "parts" not in artifact:
                continue

            for part in artifact["parts"]:
                part_kind = part.get("kind") or part.get("type")

                if part_kind == "data" and "data" in part:
                    data = part["data"]
                    if not isinstance(data, dict):
                        continue
                    if "res" in data:
                        raw_res = data["res"]
                        if isinstance(raw_res, dict):
                            return raw_res
                        if isinstance(raw_res, str) and raw_res.strip():
                            try:
                                parsed = json.loads(raw_res)
                            except (json.JSONDecodeError, TypeError):
                                parsed = None
                            if isinstance(parsed, dict):
                                return parsed
                        continue
                    if any(
                        k in data
                        for k in (
                            "entities",
                            "relationships",
                            NOTE_ROOT_ENTITY_TYPE_ID,
                            "is_duplicate",
                            "summary",
                            "structured_output",
                            "decisions",
                            "patch_entities",
                        )
                    ):
                        return data
                    content = data.get("content")
                    if isinstance(content, str) and content.strip():
                        extracted = self._extract_json_from_text(content)
                        if extracted:
                            return extracted
                    continue

                if part_kind == "text" and "text" in part:
                    text = part["text"]
                    extracted = self._extract_json_from_text(text)
                    if extracted:
                        return extracted

        plain = (response.get("response") or "").strip()
        if plain:
            extracted = self._extract_json_from_text(plain)
            if extracted:
                return extracted
        return {}

    @staticmethod
    def _compose_summary_fallback_from_structured(payload: dict[str, Any]) -> str:
        """Если модель вернула пустой summary, собираем читаемый текст из highlights/key_events."""
        lines: list[str] = []
        for key in ("highlights", "key_events"):
            raw = payload.get(key)
            if not isinstance(raw, list):
                continue
            for item in raw:
                if isinstance(item, str):
                    normalized = item.strip()
                    if normalized:
                        lines.append(normalized)
        if not lines:
            return ""
        deduped: list[str] = []
        seen: set[str] = set()
        for line in lines:
            k = line.lower()
            if k in seen:
                continue
            seen.add(k)
            deduped.append(line)
        return "\n".join(deduped)

    def _extract_json_from_text(self, text: str) -> dict[str, Any]:
        """Извлекает JSON из текста (включая markdown code blocks)."""
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1).strip())
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

        if "{" in stripped:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start != -1 and end > start:
                try:
                    parsed = json.loads(stripped[start : end + 1])
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, TypeError):
                    pass

        return {}

    def _extract_summary_from_payload(self, payload: Any) -> str | None:
        """Извлекает summary из вложенного payload A2A ответа."""
        if isinstance(payload, dict):
            summary_value = payload.get("summary")
            if isinstance(summary_value, str) and summary_value.strip():
                return summary_value

            if "structured_output" in payload:
                nested_summary = self._extract_summary_from_payload(payload["structured_output"])
                if nested_summary is not None:
                    return nested_summary

            for nested_value in payload.values():
                nested_summary = self._extract_summary_from_payload(nested_value)
                if nested_summary is not None:
                    return nested_summary
            return None

        if isinstance(payload, list):
            for item in payload:
                nested_summary = self._extract_summary_from_payload(item)
                if nested_summary is not None:
                    return nested_summary
            return None

        return None

    def _extract_string_list_from_payload(self, payload: Any, key: str) -> list[str]:
        """Извлекает список строк по ключу из вложенного payload."""
        if isinstance(payload, dict):
            raw_value = payload.get(key)
            if isinstance(raw_value, list):
                collected: list[str] = []
                for item in raw_value:
                    if isinstance(item, str):
                        normalized = item.strip()
                        if normalized:
                            collected.append(normalized)
                if collected:
                    return collected
            if "structured_output" in payload:
                nested = self._extract_string_list_from_payload(payload["structured_output"], key)
                if nested:
                    return nested
            for nested_value in payload.values():
                nested = self._extract_string_list_from_payload(nested_value, key)
                if nested:
                    return nested
            return []

        if isinstance(payload, list):
            for item in payload:
                nested = self._extract_string_list_from_payload(item, key)
                if nested:
                    return nested
            return []

        return []

    @staticmethod
    def _normalize_entity_name(entity_name: str) -> str | None:
        normalized = entity_name.strip()
        if not normalized:
            return None
        if normalized.startswith("@"):
            normalized = normalized[1:]
        normalized = normalized.strip(".,;:!?()[]{}\"'")
        if not normalized:
            return None
        return normalized

    def _extract_entities_from_text_mentions(self, text: str) -> list[str]:
        if not text:
            return []
        link_re = re.compile(r"\[(@?[^\]]+)\]\(entity:[^)]+\)", re.IGNORECASE)
        link_matches = link_re.findall(text)
        text_without_links = link_re.sub(" ", text)
        mention_matches = re.findall(r"@([^\s,.;:!?(){}\[\]]+)", text_without_links)
        entities: list[str] = []
        seen: set[str] = set()
        for mention in [*link_matches, *mention_matches]:
            normalized = self._normalize_entity_name(mention)
            if normalized is None:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            entities.append(normalized)
        return entities

    _SUMMARY_ENTITY_TOKEN_SPLIT_RE = re.compile(
        r"(\[@[^\]]+\]\(entity:[^)]+\))",
        re.IGNORECASE,
    )

    @staticmethod
    def _summary_link_entry_from_entity(entity: Any) -> dict[str, Any] | None:
        entity_id = getattr(entity, "entity_id", None)
        name = getattr(entity, "name", None)
        if not isinstance(entity_id, str) or not entity_id.strip():
            return None
        if not isinstance(name, str) or not name.strip():
            return None
        entity_type = getattr(entity, "entity_type", None)
        if entity_type == NOTE_ROOT_ENTITY_TYPE_ID:
            return None
        entry: dict[str, Any] = {
            "entity_id": entity_id.strip(),
            "name": name.strip(),
        }
        for attr in ("entity_type", "entity_subtype", "namespace"):
            value = getattr(entity, attr, None)
            if isinstance(value, str) and value.strip():
                entry[attr] = value.strip()

        attrs = getattr(entity, "attributes", None)
        aliases: list[str] = []
        if isinstance(attrs, dict):
            raw_aliases = attrs.get("aliases")
            if isinstance(raw_aliases, list):
                for alias in raw_aliases:
                    if isinstance(alias, str) and alias.strip() and alias.strip() != entry["name"]:
                        aliases.append(alias.strip())
            if entity_type == "member":
                for key in ("first_name", "last_name"):
                    value = attrs.get(key)
                    if isinstance(value, str) and value.strip() and value.strip() != entry["name"]:
                        aliases.append(value.strip())
        if aliases:
            entry["aliases"] = sorted(set(aliases), key=aliases.index)
        return entry

    @staticmethod
    def _summary_entity_links_payload(link_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in link_entries:
            if not isinstance(entry, dict):
                continue
            entity_id = entry.get("entity_id")
            name = entry.get("name")
            if not isinstance(entity_id, str) or not entity_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                continue
            normalized_id = entity_id.strip()
            if normalized_id in seen:
                continue
            seen.add(normalized_id)
            payload: dict[str, Any] = {
                "entity_id": normalized_id,
                "name": name.strip(),
            }
            for key in ("entity_type", "entity_subtype", "namespace"):
                value = entry.get(key)
                if isinstance(value, str) and value.strip():
                    payload[key] = value.strip()
            out.append(payload)
            if len(out) >= 32:
                break
        return out

    @staticmethod
    def _normalize_summary_entity_links(raw_links: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_links, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in raw_links:
            if not isinstance(item, dict):
                continue
            entity_id = item.get("entity_id")
            name = item.get("name")
            if not isinstance(entity_id, str) or not entity_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                continue
            entry: dict[str, Any] = {
                "entity_id": entity_id.strip(),
                "name": name.strip(),
            }
            for key in ("entity_type", "entity_subtype", "namespace"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    entry[key] = value.strip()
            normalized.append(entry)
        return EntityService._summary_entity_links_payload(normalized)

    async def _summary_link_entries_for_notes(self, notes: list[CRMEntity]) -> list[dict[str, Any]]:
        note_ids = [
            getattr(note, "entity_id", "")
            for note in notes
            if isinstance(getattr(note, "entity_id", ""), str)
            and getattr(note, "entity_id", "").strip()
        ]
        if not note_ids:
            return []

        entity_ids: list[str] = []
        seen_ids: set[str] = set()

        def append_entity_id(raw_id: Any) -> None:
            if not isinstance(raw_id, str):
                return
            entity_id = raw_id.strip()
            if not entity_id or entity_id in seen_ids or entity_id in note_ids:
                return
            seen_ids.add(entity_id)
            entity_ids.append(entity_id)

        relationships_by_note = await self._relationship_repo.get_neighbors(
            note_ids,
            relationship_types=list(_RESOLVED_NOTE_NEIGHBOR_REL_TYPES),
        )
        if isinstance(relationships_by_note, dict):
            for note_id in note_ids:
                rels = relationships_by_note.get(note_id)
                if not isinstance(rels, list):
                    continue
                for rel in rels:
                    source_id = getattr(rel, "source_entity_id", "")
                    target_id = getattr(rel, "target_entity_id", "")
                    append_entity_id(target_id if source_id == note_id else source_id)

        for note in notes:
            desc = getattr(note, "description", "")
            if isinstance(desc, str):
                for entity_id in self.extract_linked_entity_ids_from_description(desc):
                    append_entity_id(entity_id)

        if not entity_ids:
            return []
        rows = await self._entity_repo.list_by_entity_ids_ordered(
            entity_ids,
            company_id=self._get_company_id(),
        )
        if not isinstance(rows, list):
            return []
        entries: list[dict[str, Any]] = []
        for row in rows:
            entry = self._summary_link_entry_from_entity(row)
            if entry is not None:
                entries.append(entry)
        return entries

    def _enrich_summary_text_with_entity_links(
        self,
        summary_text: str,
        link_entries: list[dict[str, Any]],
    ) -> str:
        if not isinstance(summary_text, str) or not summary_text:
            return summary_text
        entries: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for entry in link_entries:
            if not isinstance(entry, dict):
                continue
            entity_id = entry.get("entity_id")
            canonical_name = entry.get("name")
            if not isinstance(entity_id, str) or not entity_id.strip():
                continue
            if not isinstance(canonical_name, str) or not canonical_name.strip():
                continue
            canonical = canonical_name.strip()
            if any(ch in canonical for ch in "[]()"):
                continue
            raw_aliases = entry.get("aliases")
            aliases = raw_aliases if isinstance(raw_aliases, list) else []
            names = [canonical, *aliases]
            for raw_name in names:
                if not isinstance(raw_name, str) or not raw_name.strip():
                    continue
                match_name = raw_name.strip()
                if match_name.startswith("@"):
                    match_name = match_name[1:].strip()
                if not match_name or any(ch in match_name for ch in "[]()"):
                    continue
                key = (entity_id.strip(), match_name.lower())
                if key in seen:
                    continue
                seen.add(key)
                entries.append((match_name, canonical, entity_id.strip()))

        entries.sort(key=lambda item: len(item[0]), reverse=True)
        text = summary_text
        for match_name, canonical_name, entity_id in entries:
            replacement = f"[@{canonical_name}](entity:{entity_id})"
            pattern = re.compile(
                rf"(?<!\w)@?{re.escape(match_name)}(?!\w)",
                re.IGNORECASE,
            )
            segments = self._SUMMARY_ENTITY_TOKEN_SPLIT_RE.split(text)
            for idx in range(0, len(segments), 2):
                segments[idx] = pattern.sub(replacement, segments[idx])
            text = "".join(segments)
        return text

    # Соответствует формату [@Name](entity:UUID) в description заметки
    _MENTION_TOKEN_RE = re.compile(
        r"\[@[^\]]+\]\(entity:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\)",
        re.IGNORECASE,
    )
    _EXISTING_TOKEN_SPLIT_RE = re.compile(
        r"(\[@[^\]]+\]\(entity:[0-9a-f\-]+\))",
        re.IGNORECASE,
    )

    def extract_linked_entity_ids_from_description(self, text: str) -> list[str]:
        """Возвращает список entity_id из [@Name](entity:UUID) токенов в тексте."""
        if not text:
            return []
        seen: set[str] = set()
        result: list[str] = []
        for entity_id in self._MENTION_TOKEN_RE.findall(text):
            if entity_id not in seen:
                seen.add(entity_id)
                result.append(entity_id)
        return result

    def _enrich_description_with_entity_mentions(
        self, description: str, entities: list[dict[str, object]]
    ) -> str:
        """
        Вставляет [@Name](entity:id) токены в plain-текст description.

        Работает только с exact match (регистронезависимо). Уже токенизированные
        упоминания не трогаются. Падежные формы не обрабатываются.
        Сортировка по убыванию длины имени предотвращает частичные замены
        (например «Ольга» не испортит «Ольга Ким»).

        Каждый entity может содержать поле aliases: list[str] — дополнительные строки
        для поиска; все они заменяются токеном с канонического именем entity.
        """
        # Строим плоский список (match_name, canonical_name, entity_id)
        entries: list[tuple[str, str, str]] = []
        for entity in entities:
            entity_id = entity.get("entity_id") or entity.get("id")
            name = entity.get("name")
            if not isinstance(entity_id, str) or not isinstance(name, str):
                continue
            name_stripped = name.strip()
            if not name_stripped:
                continue
            entries.append((name_stripped, name_stripped, entity_id))
            raw_aliases = entity.get("aliases")
            aliases = raw_aliases if isinstance(raw_aliases, list) else []
            for alias in aliases:
                alias_stripped = alias.strip() if isinstance(alias, str) else ""
                if alias_stripped:
                    entries.append((alias_stripped, name_stripped, entity_id))

        # Длинные совпадения обрабатываем первыми
        entries.sort(key=lambda e: len(e[0]), reverse=True)

        text = description
        for match_name, canonical_name, entity_id in entries:
            replacement = f"[@{canonical_name}](entity:{entity_id})"
            name_re = re.compile(re.escape(match_name), re.IGNORECASE)
            # Разбиваем по уже существующим токенам: чётные индексы — plain-текст
            segments = self._EXISTING_TOKEN_SPLIT_RE.split(text)
            for i in range(0, len(segments), 2):
                segments[i] = name_re.sub(replacement, segments[i])
            text = "".join(segments)
        return text

    async def _sync_note_mention_links(
        self, note_id: str, entity_ids: list[str], namespace: str
    ) -> None:
        """Создаёт linked-связи для сущностей, упомянутых в тексте заметки через @-токены."""
        if not entity_ids:
            return
        company_id = self._get_company_id()
        now = datetime.now(UTC)
        for entity_id in entity_ids:
            row = Relationship(
                relationship_id=str(uuid.uuid4()),
                source_entity_id=note_id,
                target_entity_id=entity_id,
                relationship_type="linked",
                namespace=namespace,
                weight=1.0,
                confidence=1.0,
                attributes={},
                company_id=company_id,
                created_at=now,
                updated_at=now,
            )
            await self._relationship_repo.ensure_edge(row)

    async def sync_note_mentions_from_applied_entities(
        self, note_id: str, entity_ids: list[str]
    ) -> None:
        """
        После apply AI-анализа: создаёт mentions-связи от заметки ко всем найденным сущностям.
        AI не всегда включает эти связи в черновик — создаём принудительно для всех извлечённых.
        Сущность компании тенанта (platform_company_id) пропускается — не создаём шумную связь.
        """
        if not entity_ids:
            return
        note = await self._entity_repo.get(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")
        namespace = self._resolve_namespace_for_write(note.namespace)
        company_id = self._get_company_id()
        tenant_company_ids = await self._tenant_company_entity_ids()
        now = datetime.now(UTC)
        for entity_id in entity_ids:
            if entity_id == note_id:
                continue
            if entity_id in tenant_company_ids:
                continue
            row = Relationship(
                relationship_id=str(uuid.uuid4()),
                source_entity_id=note_id,
                target_entity_id=entity_id,
                relationship_type="mentions",
                namespace=namespace,
                weight=1.0,
                confidence=1.0,
                attributes={},
                company_id=company_id,
                created_at=now,
                updated_at=now,
            )
            await self._relationship_repo.ensure_edge(row)

    async def enrich_note_description_with_mention_tokens(self, note_id: str) -> None:
        """
        После apply AI-анализа: вставляет [@Name](entity:id) токены в description
        для сущностей, связанных с заметкой через linked/mentions связи.
        """
        note = await self._entity_repo.get(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")
        if not note.description:
            return
        relationships = await self._relationship_repo.get_by_entity(note_id)
        linked_target_ids = [
            r.target_entity_id
            for r in relationships
            if r.source_entity_id == note_id
            and r.relationship_type in ("linked", "mentions", NOTE_VOICE_RELATIONSHIP_TYPE)
        ]
        if not linked_target_ids:
            return
        entities: list[dict[str, object]] = []
        for entity_id in linked_target_ids:
            entity = await self._entity_repo.get(entity_id)
            if not entity or not entity.name:
                continue
            entry: dict[str, object] = {"entity_id": entity_id, "name": entity.name}
            attrs = entity.attributes or {}
            aliases: list[str] = []

            # Псевдонимы, вручную заданные пользователем в атрибуте aliases
            raw_aliases = attrs.get("aliases")
            if isinstance(raw_aliases, list):
                for a in raw_aliases:
                    a_str = (a or "").strip() if isinstance(a, str) else ""
                    if a_str and a_str != entity.name:
                        aliases.append(a_str)

            # Для участников платформы дополнительно пробуем first_name и last_name
            if entity.entity_type == "member":
                first = (attrs.get("first_name") or "").strip()
                last = (attrs.get("last_name") or "").strip()
                if first and first != entity.name and first not in aliases:
                    aliases.append(first)
                if last and last != entity.name and last not in aliases:
                    aliases.append(last)

            if aliases:
                entry["aliases"] = aliases
            entities.append(entry)
        if not entities:
            return
        enriched = self._enrich_description_with_entity_mentions(note.description, entities)
        if enriched == note.description:
            return
        await self.update_entity(note_id, {"description": enriched})

    def _extract_entities_from_notes(self, notes: list[CRMEntity]) -> list[str]:
        entities: list[str] = []
        seen: set[str] = set()

        def append_entity(raw_name: str) -> None:
            normalized = self._normalize_entity_name(raw_name)
            if normalized is None:
                return
            key = normalized.lower()
            if key in seen:
                return
            seen.add(key)
            entities.append(normalized)

        for note in notes:
            note_tags = getattr(note, "tags", [])
            if isinstance(note_tags, list):
                for tag in note_tags:
                    if isinstance(tag, str):
                        append_entity(tag)

            note_name = getattr(note, "name", "")
            if isinstance(note_name, str):
                for entity_name in self._extract_entities_from_text_mentions(note_name):
                    append_entity(entity_name)

            note_description = getattr(note, "description", "")
            if isinstance(note_description, str):
                for entity_name in self._extract_entities_from_text_mentions(note_description):
                    append_entity(entity_name)

            attributes = getattr(note, "attributes", {})
            if isinstance(attributes, dict):
                mentioned_entities = attributes.get("mentioned_entities")
                if isinstance(mentioned_entities, list):
                    for entity_name in mentioned_entities:
                        if isinstance(entity_name, str):
                            append_entity(entity_name)

        return entities

    @staticmethod
    def _note_has_applied_ai_analysis(note: CRMEntity) -> bool:
        attrs = note.attributes or {}
        v = attrs.get("ai_analysis_applied_at")
        return isinstance(v, str) and bool(v.strip())

    def _note_to_summary_card(self, note: CRMEntity) -> dict[str, Any]:
        attrs = note.attributes or {}
        snippet: str
        custom = attrs.get("ai_summary_snippet")
        if isinstance(custom, str) and custom.strip():
            snippet = custom.strip()
            if len(snippet) > _DAILY_SUMMARY_CARD_SNIPPET_MAX:
                snippet = snippet[:_DAILY_SUMMARY_CARD_SNIPPET_MAX]
        else:
            desc = note.description or ""
            snippet = desc[:_DAILY_SUMMARY_CARD_SNIPPET_MAX] if desc else ""

        return {
            "entity_id": note.entity_id,
            "name": note.name or "",
            "entity_subtype": note.entity_subtype or "",
            "snippet": snippet,
        }

    async def _call_summarize_chunk_skill(
        self,
        cards: list[dict[str, Any]],
        date_str: str,
        namespace: str | None,
    ) -> dict[str, Any]:
        company_id = self._get_company_id()
        settings = get_settings()
        flows_base = settings.server.get_flows_service_url().rstrip("/")
        variables = {
            **_crm_llm_interface_language_vars(),
            "notes_json": json.dumps(cards, ensure_ascii=False),
            "date": date_str,
            "namespace": self._normalize_namespace(namespace),
        }
        response = await self._a2a_client.send_task(
            base_url=f"{flows_base}/flows/api/v1/crm",
            content="Daily summary: chunk",
            branch_id="summarize_chunk",
            metadata={"variables": variables, "company_id": company_id},
        )
        return self._extract_data_from_a2a_response(response)

    async def _call_summarize_merge_skill(
        self,
        partial_payloads: list[dict[str, Any]],
        date_str: str,
        namespace: str | None,
    ) -> dict[str, Any]:
        company_id = self._get_company_id()
        settings = get_settings()
        flows_base = settings.server.get_flows_service_url().rstrip("/")
        variables = {
            **_crm_llm_interface_language_vars(),
            "partials_json": json.dumps(partial_payloads, ensure_ascii=False),
            "date": date_str,
            "namespace": self._normalize_namespace(namespace),
        }
        response = await self._a2a_client.send_task(
            base_url=f"{flows_base}/flows/api/v1/crm",
            content="Daily summary: merge partials",
            branch_id="summarize_merge",
            metadata={"variables": variables, "company_id": company_id},
        )
        return self._extract_data_from_a2a_response(response)

    async def _call_period_summarize_merge_skill(
        self,
        partial_payloads: list[dict[str, Any]],
        date_from: str,
        date_to: str,
        namespace: str | None,
    ) -> dict[str, Any]:
        company_id = self._get_company_id()
        settings = get_settings()
        flows_base = settings.server.get_flows_service_url().rstrip("/")
        variables = {
            **_crm_llm_interface_language_vars(),
            "partials_json": json.dumps(partial_payloads, ensure_ascii=False),
            "date_from": date_from,
            "date_to": date_to,
            "namespace": self._normalize_namespace(namespace),
        }
        response = await self._a2a_client.send_task(
            base_url=f"{flows_base}/flows/api/v1/crm",
            content="Period summary: merge daily summaries",
            branch_id="period_summarize_merge",
            metadata={"variables": variables, "company_id": company_id},
        )
        return self._extract_data_from_a2a_response(response)

    async def call_summarize_attachment(self, text: str, filename: str) -> str:
        """Суммаризировать текст вложения до компактного резюме через CRM flows skill.

        Длинный текст режется на чанки в пределах контекстного окна локального LLM (~32k токенов),
        каждый чанк суммарируется отдельно; при необходимости выполняется финальное слияние резюме.
        """
        safe_text = truncate_attachment_text_for_note(text)
        chunks = split_text_into_summarize_chunks(safe_text, ATTACHMENT_SUMMARIZE_CHUNK_MAX_CHARS)
        if not chunks:
            return ""

        partials: list[str] = []
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            chunk_label = filename if total == 1 else f"{filename} (фрагмент {i + 1}/{total})"
            partials.append(await self._summarize_attachment_fragment(chunk, chunk_label))

        merged = "\n\n---\n\n".join(s.strip() for s in partials if s.strip())
        merged = merged.strip()
        if not merged:
            raise ValueError("Суммаризация вложения не вернула текст ни по одному фрагменту")
        if len(merged) <= ATTACHMENT_SUMMARIZE_MERGE_PASS_THRESHOLD_CHARS:
            return merged
        return await self._summarize_attachment_fragment(
            merged,
            f"{filename} (объединённое резюме фрагментов)",
        )

    async def _summarize_attachment_fragment(self, text: str, filename: str) -> str:
        company_id = self._get_company_id()
        settings = get_settings()
        flows_base = settings.server.get_flows_service_url().rstrip("/")
        variables = {
            **_crm_llm_interface_language_vars(),
            "text": text,
            "filename": filename,
        }
        response = await self._a2a_client.send_task(
            base_url=f"{flows_base}/flows/api/v1/crm",
            content="Summarize attachment",
            branch_id="summarize_attachment",
            metadata={"variables": variables, "company_id": company_id},
        )
        data = self._extract_data_from_a2a_response(response)
        summary = data.get("summary", "")
        if not isinstance(summary, str):
            raise ValueError(
                f"summarize_attachment вернул некорректный тип summary: {type(summary)}"
            )
        return summary

    async def _persist_daily_summary_state(
        self,
        *,
        company_id: str,
        date_str: str,
        namespace: str | None,
        state: dict[str, Any],
    ) -> None:
        await self._daily_summary_cache_service.set_state(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
            state=state,
        )
        await self._daily_summary_artifact_service.put_daily_payload(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
            payload=state,
        )
        await broadcast_crm_daily_summary_updated(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
            state=state,
            company_repository=self._company_repo,
            access_grant_repository=self._access_grant_repo,
        )

    async def _materialize_empty_daily_summary(
        self,
        date_str: str,
        namespace: str | None,
        *,
        company_id: str,
    ) -> dict[str, Any]:
        summary_core = await self.compute_daily_summary(date_str=date_str, namespace=namespace)
        state = {
            **summary_core,
            "revalidating": False,
            "stale": False,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        await self._daily_summary_cache_service.clear_revalidating(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )
        await self._persist_daily_summary_state(
            company_id=company_id,
            date_str=date_str,
            namespace=namespace,
            state=state,
        )
        return state

    async def _try_hydrate_daily_from_s3(
        self,
        *,
        company_id: str,
        date_str: str,
        namespace: str | None,
        current_version: dict[str, Any],
    ) -> dict[str, Any] | None:
        payload = await self._daily_summary_artifact_service.get_daily_payload(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )
        if payload is None:
            return None
        cached_v = payload.get("source_version")
        if _canonical_json(cached_v) != _canonical_json(current_version):
            return None
        await self._daily_summary_cache_service.set_state(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
            state=payload,
        )
        return payload

    async def _collect_period_days_bundle(
        self,
        date_from: str,
        date_to: str,
        namespace: str | None,
    ) -> dict[str, Any]:
        days = _iter_iso_dates_inclusive(date_from, date_to)
        day_entries: list[dict[str, Any]] = []
        for d in days:
            _, ver = await self._collect_notes_and_source_version(
                date_str=d,
                namespace=namespace,
            )
            day_entries.append({"date": d, "source_version": ver})
        return {"days": day_entries}

    async def compute_daily_summary(
        self,
        date_str: str,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Синхронно вычисляет summary для даты и namespace (map-reduce по чанкам заметок с AI)."""
        datetime.fromisoformat(date_str)

        notes, source_version = await self._collect_notes_and_source_version(
            date_str=date_str,
            namespace=namespace,
        )

        if not notes:
            return {
                "date": date_str,
                "namespace": self._normalize_namespace(namespace),
                "summary": f"За {date_str} заметок не найдено.",
                "entities": [],
                "entity_links": [],
                "entities_count": 0,
                "source_version": source_version,
            }

        analyzed_notes = [n for n in notes if self._note_has_applied_ai_analysis(n)]
        if not analyzed_notes:
            return {
                "date": date_str,
                "namespace": self._normalize_namespace(namespace),
                "summary": (
                    f"За {date_str} нет заметок с применённым AI-анализом "
                    f"(ожидается поле ai_analysis_applied_at после подтверждения черновика)."
                ),
                "entities": [],
                "entity_links": [],
                "entities_count": len(notes),
                "source_version": source_version,
            }

        crm_settings = get_crm_settings()
        chunk_sz = crm_settings.daily_summary_chunk_size
        max_conc = crm_settings.daily_summary_map_reduce_max_concurrent
        cards = [self._note_to_summary_card(n) for n in analyzed_notes]
        input_entities = self._extract_entities_from_notes(analyzed_notes)
        summary_link_entries = await self._summary_link_entries_for_notes(analyzed_notes)

        async def map_batch(batch: list[dict[str, Any]]) -> dict[str, Any]:
            return await self._call_summarize_chunk_skill(batch, date_str, namespace)

        async def merge_batch(partials: list[dict[str, Any]]) -> dict[str, Any]:
            return await self._call_summarize_merge_skill(partials, date_str, namespace)

        structured = await map_reduce_tree(
            cards,
            chunk_size=chunk_sz,
            map_batch=map_batch,
            merge_batch=merge_batch,
            max_concurrent=max_conc,
        )

        summary_text = self._extract_summary_from_payload(structured)
        if summary_text is None and isinstance(structured, dict):
            s = structured.get("summary")
            summary_text = s if isinstance(s, str) else None
        if summary_text is None:
            summary_text = ""
        if isinstance(structured, dict) and (
            not isinstance(summary_text, str) or not summary_text.strip()
        ):
            fallback = self._compose_summary_fallback_from_structured(structured)
            if fallback.strip():
                summary_text = fallback
        summary_text = self._enrich_summary_text_with_entity_links(
            summary_text,
            summary_link_entries,
        )
        summary_entities = self._extract_string_list_from_payload(structured, "entities")
        if not summary_entities and isinstance(structured, dict):
            parsed = structured
            summary_entities = self._extract_string_list_from_payload(parsed, "entities")
        if not summary_entities:
            summary_entities = self._extract_entities_from_text_mentions(summary_text)
        if not summary_entities:
            summary_entities = input_entities

        return {
            "date": date_str,
            "namespace": self._normalize_namespace(namespace),
            "summary": summary_text,
            "entities": summary_entities[:8],
            "entity_links": self._summary_entity_links_payload(summary_link_entries),
            "entities_count": len(notes),
            "source_version": source_version,
        }

    async def rebuild_daily_summary(
        self,
        date_str: str,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Пересчитывает и сохраняет daily summary в Redis state."""
        company_id = self._get_company_id()
        lock_acquired = await self._daily_summary_cache_service.acquire_rebuild_lock(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )
        if not lock_acquired:
            state = await self._daily_summary_cache_service.get_state(
                company_id=company_id,
                namespace=namespace,
                date_str=date_str,
            )
            if state is None:
                return {
                    "date": date_str,
                    "namespace": self._normalize_namespace(namespace),
                    "summary": "",
                    "entities": [],
                    "entities_count": 0,
                    "revalidating": True,
                    "generated_at": None,
                    "source_version": {
                        "notes_count": 0,
                        "max_updated_at": None,
                    },
                    "stale": True,
                }
            if not isinstance(state.get("entities"), list):
                state["entities"] = []
            state["revalidating"] = True
            state["stale"] = True
            return state
        try:
            summary = await self.compute_daily_summary(date_str=date_str, namespace=namespace)
            state = {
                **summary,
                "revalidating": False,
                "stale": False,
                "generated_at": datetime.now(UTC).isoformat(),
            }
            await self._persist_daily_summary_state(
                company_id=company_id,
                date_str=date_str,
                namespace=namespace,
                state=state,
            )
            await self._daily_summary_cache_service.clear_revalidating(
                company_id=company_id,
                namespace=namespace,
                date_str=date_str,
            )
            return state
        except Exception:
            await self._daily_summary_cache_service.clear_revalidating(
                company_id=company_id,
                namespace=namespace,
                date_str=date_str,
            )
            raise
        finally:
            await self._daily_summary_cache_service.release_rebuild_lock(
                company_id=company_id,
                namespace=namespace,
                date_str=date_str,
            )

    async def enqueue_daily_summary_rebuild(
        self,
        date_str: str,
        namespace: str | None = None,
    ) -> bool:
        """Ставит задачу пересчета summary, если она ещё не в процессе."""
        company_id = self._get_company_id()
        notes_empty_check, _ = await self._collect_notes_and_source_version(
            date_str=date_str,
            namespace=namespace,
        )
        if len(notes_empty_check) == 0:
            await self._materialize_empty_daily_summary(
                date_str=date_str,
                namespace=namespace,
                company_id=company_id,
            )
            return True

        became_revalidating = await self._daily_summary_cache_service.set_revalidating(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )
        if not became_revalidating:
            return False

        from apps.crm_worker.tasks.daily_summary_tasks import rebuild_daily_summary_task

        context = get_context()
        if not context:
            raise ValueError("Нет контекста для отправки задачи rebuild_daily_summary")

        user_id = self._get_user_id()
        normalized_namespace = self._normalize_namespace(namespace)
        task_namespace = normalized_namespace or SUMMARY_ALL_NAMESPACES_TASK_KEY
        task_id: str | None = None

        if self._task_repository is not None:
            task_row = CRMTask(
                task_id=str(uuid.uuid4()),
                task_type="daily_summary",
                status="running",
                stage="summarizing_day",
                progress_pct=10,
                company_id=company_id,
                namespace=task_namespace,
                user_id=user_id,
                started_at=datetime.now(UTC),
                data={"date_str": date_str, "reason": "event"},
            )
            await self._task_repository.create(task_row)
            task_id = task_row.task_id

        await rebuild_daily_summary_task.kiq(
            company_id=company_id,
            date_str=date_str,
            namespace=normalized_namespace,
            reason="event",
            auth_token=context.auth_token,
            user_id=user_id,
            task_id=task_id,
        )
        return True

    @staticmethod
    def _normalize_summary_entity_list(cached_entities: Any) -> list[str]:
        normalized_entities: list[str] = []
        if isinstance(cached_entities, list):
            for entity_name in cached_entities:
                if isinstance(entity_name, str):
                    normalized = entity_name.strip()
                    if normalized:
                        normalized_entities.append(normalized)
        return normalized_entities

    async def get_daily_summary_cached(
        self,
        date_str: str,
        namespace: str | None = None,
        force_rebuild: bool = False,
    ) -> dict[str, Any]:
        """Возвращает summary по SWR: stale-while-revalidate."""
        company_id = self._get_company_id()
        datetime.fromisoformat(date_str)

        notes, current_version = await self._collect_notes_and_source_version(
            date_str=date_str,
            namespace=namespace,
        )

        if len(notes) == 0:
            cached_state = await self._daily_summary_cache_service.get_state(
                company_id=company_id,
                namespace=namespace,
                date_str=date_str,
            )
            if (
                not force_rebuild
                and cached_state is not None
                and "entity_links" in cached_state
                and _canonical_json(cached_state.get("source_version"))
                == _canonical_json(current_version)
            ):
                normalized_entities = self._normalize_summary_entity_list(
                    cached_state.get("entities")
                )
                normalized_links = self._normalize_summary_entity_links(
                    cached_state.get("entity_links")
                )
                return {
                    **cached_state,
                    "entities": normalized_entities,
                    "entity_links": normalized_links,
                    "source_version": current_version,
                    "revalidating": False,
                    "stale": False,
                }
            fresh = await self._materialize_empty_daily_summary(
                date_str=date_str,
                namespace=namespace,
                company_id=company_id,
            )
            normalized_entities = self._normalize_summary_entity_list(fresh.get("entities"))
            normalized_links = self._normalize_summary_entity_links(fresh.get("entity_links"))
            return {
                **fresh,
                "entities": normalized_entities,
                "entity_links": normalized_links,
                "source_version": current_version,
                "revalidating": False,
                "stale": False,
            }

        cached_state = await self._daily_summary_cache_service.get_state(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )
        if cached_state is None:
            hydrated = await self._try_hydrate_daily_from_s3(
                company_id=company_id,
                date_str=date_str,
                namespace=namespace,
                current_version=current_version,
            )
            if hydrated is not None:
                cached_state = hydrated

        is_revalidating = await self._daily_summary_cache_service.is_revalidating(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )

        if force_rebuild and not is_revalidating:
            await self.enqueue_daily_summary_rebuild(date_str=date_str, namespace=namespace)
            is_revalidating = True

        if cached_state is None:
            if not is_revalidating:
                await self.enqueue_daily_summary_rebuild(date_str=date_str, namespace=namespace)
            return {
                "date": date_str,
                "namespace": self._normalize_namespace(namespace),
                "summary": "",
                "entities": [],
                "entity_links": [],
                "entities_count": 0,
                "generated_at": None,
                "source_version": current_version,
                "revalidating": True,
                "stale": True,
            }

        cached_version = cached_state.get("source_version")
        cached_stale = cached_state.get("stale") is True
        cached_schema_stale = "entity_links" not in cached_state
        is_stale = (
            _canonical_json(cached_version) != _canonical_json(current_version)
            or cached_schema_stale
        )
        normalized_entities = self._normalize_summary_entity_list(cached_state.get("entities"))
        normalized_links = self._normalize_summary_entity_links(cached_state.get("entity_links"))

        if is_stale and not is_revalidating:
            await self.enqueue_daily_summary_rebuild(date_str=date_str, namespace=namespace)
            is_revalidating = True

        return {
            **cached_state,
            "entities": normalized_entities,
            "entity_links": normalized_links,
            "source_version": current_version if is_stale else cached_version,
            "revalidating": is_revalidating,
            "stale": is_stale or force_rebuild or cached_stale or is_revalidating,
        }

    async def _ensure_daily_payload_for_period(
        self,
        date_str: str,
        namespace: str | None,
        *,
        company_id: str,
    ) -> dict[str, Any]:
        """Дневная сводка для merge периода: Redis/S3 или пересчёт."""
        notes, ver = await self._collect_notes_and_source_version(
            date_str=date_str,
            namespace=namespace,
        )
        if len(notes) == 0:
            empty_core = await self.compute_daily_summary(date_str=date_str, namespace=namespace)
            return {**empty_core, "generated_at": None}

        cached = await self._daily_summary_cache_service.get_state(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )
        if (
            cached is not None
            and "entity_links" in cached
            and _canonical_json(cached.get("source_version")) == _canonical_json(ver)
        ):
            return cached

        hydrated = await self._try_hydrate_daily_from_s3(
            company_id=company_id,
            date_str=date_str,
            namespace=namespace,
            current_version=ver,
        )
        if hydrated is not None and "entity_links" in hydrated:
            return hydrated

        summary_core = await self.compute_daily_summary(date_str=date_str, namespace=namespace)
        state = {
            **summary_core,
            "revalidating": False,
            "stale": False,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        await self._persist_daily_summary_state(
            company_id=company_id,
            date_str=date_str,
            namespace=namespace,
            state=state,
        )
        return state

    async def compute_period_summary(
        self,
        date_from: str,
        date_to: str,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Сводка за диапазон: merge готовых дневных сводок (при необходимости досчитывает день)."""
        datetime.fromisoformat(date_from)
        datetime.fromisoformat(date_to)
        max_days = get_crm_settings().period_summary_max_days
        date_from, date_to, _ = _clamp_period_dates_for_summary(date_from, date_to, max_days)
        days = _iter_iso_dates_inclusive(date_from, date_to)

        company_id = self._get_company_id()
        period_bundle = await self._collect_period_days_bundle(date_from, date_to, namespace)
        partials: list[dict[str, Any]] = []
        period_link_entries: list[dict[str, Any]] = []
        for d in days:
            day_payload = await self._ensure_daily_payload_for_period(
                d,
                namespace,
                company_id=company_id,
            )
            day_links = self._normalize_summary_entity_links(day_payload.get("entity_links"))
            period_link_entries.extend(day_links)
            partials.append(
                {
                    "date": d,
                    "summary": day_payload.get("summary", ""),
                    "entities": day_payload.get("entities", []),
                    "entity_links": day_links,
                }
            )

        structured = await self._call_period_summarize_merge_skill(
            partials,
            date_from,
            date_to,
            namespace,
        )
        summary_text = self._extract_summary_from_payload(structured)
        if summary_text is None and isinstance(structured, dict):
            s = structured.get("summary")
            summary_text = s if isinstance(s, str) else None
        if summary_text is None:
            summary_text = ""
        if isinstance(structured, dict) and (
            not isinstance(summary_text, str) or not summary_text.strip()
        ):
            fallback = self._compose_summary_fallback_from_structured(structured)
            if fallback.strip():
                summary_text = fallback
        summary_text = self._enrich_summary_text_with_entity_links(
            summary_text,
            period_link_entries,
        )
        summary_entities = self._extract_string_list_from_payload(structured, "entities")
        if not summary_entities:
            summary_entities = self._extract_entities_from_text_mentions(summary_text)
        if not summary_entities:
            merged: list[str] = []
            for p in partials:
                for name in p.get("entities") or []:
                    if isinstance(name, str) and name.strip() and name.strip() not in merged:
                        merged.append(name.strip())
            summary_entities = merged[:12]

        return {
            "date_from": date_from,
            "date_to": date_to,
            "namespace": self._normalize_namespace(namespace),
            "summary": summary_text,
            "entities": summary_entities[:12],
            "entity_links": self._summary_entity_links_payload(period_link_entries),
            "source_version": period_bundle,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    async def rebuild_period_summary(
        self,
        date_from: str,
        date_to: str,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        company_id = self._get_company_id()
        lock_ok = await self._daily_summary_cache_service.acquire_period_rebuild_lock(
            company_id=company_id,
            namespace=namespace,
            date_from=date_from,
            date_to=date_to,
        )
        if not lock_ok:
            existing = await self._daily_summary_cache_service.get_period_state(
                company_id=company_id,
                namespace=namespace,
                date_from=date_from,
                date_to=date_to,
            )
            if existing is None:
                return {
                    "date_from": date_from,
                    "date_to": date_to,
                    "namespace": self._normalize_namespace(namespace),
                    "summary": "",
                    "entities": [],
                    "revalidating": True,
                    "stale": True,
                    "source_version": await self._collect_period_days_bundle(
                        date_from, date_to, namespace
                    ),
                }
            existing["revalidating"] = True
            existing["stale"] = True
            return existing
        try:
            summary = await self.compute_period_summary(
                date_from=date_from,
                date_to=date_to,
                namespace=namespace,
            )
            state = {
                **summary,
                "revalidating": False,
                "stale": False,
            }
            await self._daily_summary_cache_service.set_period_state(
                company_id=company_id,
                namespace=namespace,
                date_from=date_from,
                date_to=date_to,
                state=state,
            )
            await self._daily_summary_artifact_service.put_period_payload(
                company_id=company_id,
                namespace=namespace,
                date_from=date_from,
                date_to=date_to,
                payload=state,
            )
            await self._daily_summary_cache_service.clear_period_revalidating(
                company_id=company_id,
                namespace=namespace,
                date_from=date_from,
                date_to=date_to,
            )
            await broadcast_crm_period_summary_updated(
                company_id=company_id,
                namespace=namespace,
                date_from=date_from,
                date_to=date_to,
                state=state,
                company_repository=self._company_repo,
                access_grant_repository=self._access_grant_repo,
            )
            return state
        except Exception:
            await self._daily_summary_cache_service.clear_period_revalidating(
                company_id=company_id,
                namespace=namespace,
                date_from=date_from,
                date_to=date_to,
            )
            raise
        finally:
            await self._daily_summary_cache_service.release_period_rebuild_lock(
                company_id=company_id,
                namespace=namespace,
                date_from=date_from,
                date_to=date_to,
            )

    async def enqueue_period_summary_rebuild(
        self,
        date_from: str,
        date_to: str,
        namespace: str | None = None,
    ) -> bool:
        company_id = self._get_company_id()
        became = await self._daily_summary_cache_service.set_period_revalidating(
            company_id=company_id,
            namespace=namespace,
            date_from=date_from,
            date_to=date_to,
        )
        if not became:
            return False
        from apps.crm_worker.tasks.daily_summary_tasks import rebuild_period_summary_task
        from core.context import get_context

        context = get_context()
        if not context:
            raise ValueError("Нет контекста для отправки задачи rebuild_period_summary")

        user_id = self._get_user_id()
        normalized_namespace = self._normalize_namespace(namespace)
        task_namespace = normalized_namespace or SUMMARY_ALL_NAMESPACES_TASK_KEY
        task_id: str | None = None

        if self._task_repository is not None:
            task_row = CRMTask(
                task_id=str(uuid.uuid4()),
                task_type="period_summary",
                status="running",
                stage="summarizing_day",
                progress_pct=10,
                company_id=company_id,
                namespace=task_namespace,
                user_id=user_id,
                started_at=datetime.now(UTC),
                data={
                    "date_from": date_from,
                    "date_to": date_to,
                    "reason": "event",
                },
            )
            await self._task_repository.create(task_row)
            task_id = task_row.task_id

        await rebuild_period_summary_task.kiq(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            namespace=normalized_namespace,
            reason="event",
            auth_token=context.auth_token,
            user_id=user_id,
            task_id=task_id,
        )
        return True

    async def _try_hydrate_period_from_s3(
        self,
        *,
        company_id: str,
        date_from: str,
        date_to: str,
        namespace: str | None,
        current_bundle: dict[str, Any],
    ) -> dict[str, Any] | None:
        payload = await self._daily_summary_artifact_service.get_period_payload(
            company_id=company_id,
            namespace=namespace,
            date_from=date_from,
            date_to=date_to,
        )
        if payload is None:
            return None
        if _canonical_json(payload.get("source_version")) != _canonical_json(current_bundle):
            return None
        await self._daily_summary_cache_service.set_period_state(
            company_id=company_id,
            namespace=namespace,
            date_from=date_from,
            date_to=date_to,
            state=payload,
        )
        return payload

    async def get_period_summary_cached(
        self,
        date_from: str,
        date_to: str,
        namespace: str | None = None,
        force_rebuild: bool = False,
    ) -> dict[str, Any]:
        requested_date_from = date_from
        requested_date_to = date_to
        datetime.fromisoformat(requested_date_from)
        datetime.fromisoformat(requested_date_to)
        max_days = get_crm_settings().period_summary_max_days
        date_from, date_to, period_was_truncated = _clamp_period_dates_for_summary(
            requested_date_from, requested_date_to, max_days
        )
        requested_period_days = len(
            _iter_iso_dates_inclusive(requested_date_from, requested_date_to)
        )

        def _period_truncation_fields() -> dict[str, Any]:
            fields: dict[str, Any] = {"period_truncated": period_was_truncated}
            if period_was_truncated:
                fields["requested_date_from"] = requested_date_from
                fields["requested_date_to"] = requested_date_to
                fields["period_summary_max_days"] = max_days
                fields["requested_period_days"] = requested_period_days
            return fields

        company_id = self._get_company_id()
        current_bundle = await self._collect_period_days_bundle(date_from, date_to, namespace)

        cached_state = await self._daily_summary_cache_service.get_period_state(
            company_id=company_id,
            namespace=namespace,
            date_from=date_from,
            date_to=date_to,
        )
        if cached_state is None:
            hydrated = await self._try_hydrate_period_from_s3(
                company_id=company_id,
                date_from=date_from,
                date_to=date_to,
                namespace=namespace,
                current_bundle=current_bundle,
            )
            if hydrated is not None:
                cached_state = hydrated

        is_revalidating = await self._daily_summary_cache_service.is_period_revalidating(
            company_id=company_id,
            namespace=namespace,
            date_from=date_from,
            date_to=date_to,
        )

        if force_rebuild and not is_revalidating:
            await self.enqueue_period_summary_rebuild(
                date_from=date_from,
                date_to=date_to,
                namespace=namespace,
            )
            is_revalidating = True

        if cached_state is None:
            if not is_revalidating:
                await self.enqueue_period_summary_rebuild(
                    date_from=date_from,
                    date_to=date_to,
                    namespace=namespace,
                )
            return {
                "date_from": date_from,
                "date_to": date_to,
                "namespace": self._normalize_namespace(namespace),
                "summary": "",
                "entities": [],
                "entity_links": [],
                "generated_at": None,
                "source_version": current_bundle,
                "revalidating": True,
                "stale": True,
                **_period_truncation_fields(),
            }

        cached_version = cached_state.get("source_version")
        cached_stale = cached_state.get("stale") is True
        cached_schema_stale = "entity_links" not in cached_state
        is_stale = (
            _canonical_json(cached_version) != _canonical_json(current_bundle)
            or cached_schema_stale
        )
        normalized_entities = self._normalize_summary_entity_list(cached_state.get("entities"))
        normalized_links = self._normalize_summary_entity_links(cached_state.get("entity_links"))

        if is_stale and not is_revalidating:
            await self.enqueue_period_summary_rebuild(
                date_from=date_from,
                date_to=date_to,
                namespace=namespace,
            )
            is_revalidating = True

        return {
            **cached_state,
            "entities": normalized_entities,
            "entity_links": normalized_links,
            "source_version": current_bundle if is_stale else cached_version,
            "revalidating": is_revalidating,
            "stale": is_stale or force_rebuild or cached_stale or is_revalidating,
            **_period_truncation_fields(),
        }

    async def get_entity_card(
        self,
        entity_id: str,
    ) -> dict[str, Any]:
        """
        Получает полную карточку entity с контекстом:
        - Данные entity
        - Все relationships
        - Связанные entities
        - Attachments

        Args:
            entity_id: ID entity
            company_id: ID компании

        Returns:
            Dict с полной информацией о entity
        """

        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        relationships = await self._relationship_repo.get_by_entity(entity_id)

        related_entity_ids = set()
        for rel in relationships:
            if rel.source_entity_id == entity_id:
                related_entity_ids.add(rel.target_entity_id)
            else:
                related_entity_ids.add(rel.source_entity_id)

        related_entities = await self._entity_repo.get_by_ids(list(related_entity_ids))
        related_entities_payload = await self._related_entities_as_api_dicts(related_entities)

        attachments = await self._attachment_service.get_attachments(entity_id)

        entity_payload = await self._entity_as_api_dict(entity)

        return {
            "entity": entity_payload,
            "relationships": [
                {
                    "relationship_id": rel.relationship_id,
                    "company_id": rel.company_id,
                    "namespace": rel.namespace,
                    "source_entity_id": rel.source_entity_id,
                    "target_entity_id": rel.target_entity_id,
                    "relationship_type": rel.relationship_type,
                    "weight": rel.weight,
                    "confidence": rel.confidence,
                    "attributes": rel.attributes,
                    "created_at": rel.created_at.isoformat() if rel.created_at else None,
                    "updated_at": rel.updated_at.isoformat() if rel.updated_at else None,
                }
                for rel in relationships
            ],
            "related_entities": related_entities_payload,
            "attachments": attachments,
        }

    async def get_bulk_entity_cards(
        self,
        entity_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """
        Batch-загрузка карточек для списка entity_id.

        Вместо N запросов делает:
          - 1 запрос за всеми сущностями
          - 1 запрос за всеми relationships
          - 1 запрос за всеми связанными сущностями
          - N параллельных запросов за attachments (по одному на entity)

        Returns:
            Dict {entity_id: card_dict}; отсутствующие entity_id не включаются в результат.
        """
        if not entity_ids:
            return {}

        entities = await self._entity_repo.get_by_ids(entity_ids)
        entities_by_id = {e.entity_id: e for e in entities}

        relationships_by_entity = await self._relationship_repo.get_neighbors(entity_ids)

        all_related_ids: set[str] = set()
        for eid, rels in relationships_by_entity.items():
            for rel in rels:
                neighbor = (
                    rel.target_entity_id if rel.source_entity_id == eid else rel.source_entity_id
                )
                all_related_ids.add(neighbor)
        all_related_ids -= set(entity_ids)

        related_entities = (
            await self._entity_repo.get_by_ids(list(all_related_ids)) if all_related_ids else []
        )
        related_payload_by_id: dict[str, dict[str, Any]] = {}
        if related_entities:
            enriched_related = await self._related_entities_as_api_dicts(related_entities)
            for rd in enriched_related:
                eid = rd.get("entity_id")
                if isinstance(eid, str) and eid:
                    related_payload_by_id[eid] = rd

        attachments_list = await asyncio.gather(
            *[
                self._attachment_service.get_attachments(eid)
                for eid in entity_ids
                if eid in entities_by_id
            ]
        )
        existing_ids = [eid for eid in entity_ids if eid in entities_by_id]
        attachments_by_entity = dict(zip(existing_ids, attachments_list))

        center_entities = [entities_by_id[eid] for eid in entity_ids if eid in entities_by_id]
        center_payload_by_id: dict[str, dict[str, Any]] = {}
        if center_entities:
            enriched_centers = await build_entity_responses_with_semantic_index(
                self._entity_repo,
                center_entities,
            )
            for resp in enriched_centers:
                center_payload_by_id[resp.entity_id] = resp.model_dump(mode="json")

        result: dict[str, dict[str, Any]] = {}
        for eid in entity_ids:
            entity = entities_by_id.get(eid)
            if not entity:
                continue
            rels = relationships_by_entity.get(eid, [])
            rel_neighbor_ids: set[str] = set()
            for rel in rels:
                neighbor = (
                    rel.target_entity_id if rel.source_entity_id == eid else rel.source_entity_id
                )
                rel_neighbor_ids.add(neighbor)
            result[eid] = {
                "entity": center_payload_by_id[eid],
                "relationships": [
                    {
                        "relationship_id": rel.relationship_id,
                        "company_id": rel.company_id,
                        "namespace": rel.namespace,
                        "source_entity_id": rel.source_entity_id,
                        "target_entity_id": rel.target_entity_id,
                        "relationship_type": rel.relationship_type,
                        "weight": rel.weight,
                        "confidence": rel.confidence,
                        "attributes": rel.attributes,
                        "created_at": rel.created_at.isoformat() if rel.created_at else None,
                        "updated_at": rel.updated_at.isoformat() if rel.updated_at else None,
                    }
                    for rel in rels
                ],
                "related_entities": [
                    related_payload_by_id[nid]
                    for nid in rel_neighbor_ids
                    if nid in related_payload_by_id
                ],
                "attachments": attachments_by_entity.get(eid, []),
            }
        return result

    async def _entity_as_api_dict(self, entity: CRMEntity) -> dict[str, Any]:
        enriched = await build_entity_responses_with_semantic_index(self._entity_repo, [entity])
        if len(enriched) != 1:
            raise ValueError("_entity_as_api_dict: expected a single enriched entity")
        return enriched[0].model_dump(mode="json")

    async def _related_entities_as_api_dicts(
        self, entities: list[CRMEntity]
    ) -> list[dict[str, Any]]:
        if not entities:
            return []
        enriched = await build_entity_responses_with_semantic_index(self._entity_repo, entities)
        return [resp.model_dump(mode="json") for resp in enriched]

    @staticmethod
    def _entity_to_dict(entity: CRMEntity) -> dict[str, Any]:
        """Конвертирует SQLAlchemy CRMEntity в dict."""
        return {
            "entity_id": entity.entity_id,
            "company_id": entity.company_id,
            "namespace": entity.namespace,
            "entity_type": entity.entity_type,
            "entity_subtype": entity.entity_subtype,
            "name": entity.name,
            "description": entity.description,
            "status": entity.status,
            "tags": entity.tags or [],
            "attributes": entity.attributes or {},
            "priority": entity.priority,
            "due_date": entity.due_date.isoformat() if entity.due_date else None,
            "note_date": entity.note_date.isoformat() if entity.note_date else None,
            "assignees": entity.assignees or [],
            "attachment_ids": entity.attachment_ids or [],
            "user_id": entity.user_id,
            "source_entity_id": entity.source_entity_id,
            "source_company_id": entity.source_company_id,
            "relevance": entity.relevance,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }

    async def _deduplicate_entities(
        self,
        extracted_entities: list[AIExtractedEntity],
        namespace: str,
    ) -> list[DeduplicateResult]:
        """
        Проверяет каждую entity на дубликат.

        Логика:
        1. Семантический поиск по name + description (RAG-запросы параллельно)
        2. similarity > 0.95 -> точный дубликат, merge сразу
        3. similarity 0.7-0.95 -> вызов LLM для уточнения (батч deduplicate_batch при >=2 пар)
        4. similarity < 0.7 -> новая entity
        """
        if not extracted_entities:
            return []

        crm_settings = get_crm_settings()
        t_rag = time.perf_counter()
        rag_sem = asyncio.Semaphore(crm_settings.dedup_rag_max_concurrent_searches)

        async def search_one(entity: AIExtractedEntity) -> list[tuple[CRMEntity, float]]:
            search_query = f"{entity.name} {entity.description or ''}"
            async with rag_sem:
                return await self._entity_repo.search_with_similarity(
                    query=search_query,
                    entity_type=entity.entity_type,
                    namespace=namespace,
                    limit=crm_settings.dedup_rag_search_limit,
                )

        scored_per_entity = await asyncio.gather(*[search_one(e) for e in extracted_entities])
        logger.info(
            "crm.dedup.rag_ms=%.1f entities=%s",
            (time.perf_counter() - t_rag) * 1000,
            len(extracted_entities),
        )

        results: list[DeduplicateResult | None] = [None] * len(extracted_entities)
        need_llm: list[tuple[int, AIExtractedEntity, CRMEntity, float]] = []

        for i, entity in enumerate(extracted_entities):
            scored_candidates = scored_per_entity[i]
            if not scored_candidates:
                results[i] = DeduplicateResult(
                    is_duplicate=False,
                    confidence=0.0,
                    reason="No candidates found",
                    action="create",
                )
                continue

            top_candidate, similarity = scored_candidates[0]

            if similarity > 0.95:
                merged_attrs = {**(top_candidate.attributes or {}), **(entity.attributes or {})}
                results[i] = DeduplicateResult(
                    is_duplicate=True,
                    confidence=similarity,
                    reason="High similarity match",
                    action="merge",
                    existing_entity_id=top_candidate.entity_id,
                    existing_entity_name=top_candidate.name,
                    merged_attributes=merged_attrs,
                    merged_description=self._merge_descriptions(
                        top_candidate.description, entity.description
                    ),
                )
            elif similarity >= 0.7:
                need_llm.append((i, entity, top_candidate, similarity))
            else:
                results[i] = DeduplicateResult(
                    is_duplicate=False,
                    confidence=similarity,
                    reason="Low similarity",
                    action="create",
                )

        t_llm = time.perf_counter()
        if need_llm:
            llm_by_index = await self._run_llm_deduplicate_round(need_llm)
            for list_idx, dedup_result in llm_by_index.items():
                results[list_idx] = dedup_result
        logger.info(
            "crm.dedup.llm_ms=%.1f pairs=%s",
            (time.perf_counter() - t_llm) * 1000,
            len(need_llm),
        )

        finalized: list[DeduplicateResult] = []
        for i, r in enumerate(results):
            if r is None:
                raise RuntimeError(f"dedup: не заполнен результат для сущности с индексом {i}")
            finalized.append(r)
        return finalized

    async def _run_llm_deduplicate_round(
        self,
        need_llm: list[tuple[int, AIExtractedEntity, CRMEntity, float]],
    ) -> dict[int, DeduplicateResult]:
        """Несколько пар: чанки по dedup_batch_max_pairs (не больше 5); run_chunked_map из core."""
        crm_settings = get_crm_settings()
        max_pairs = min(5, crm_settings.dedup_batch_max_pairs_per_request)
        max_concurrent = crm_settings.dedup_llm_max_concurrent_batch_requests

        async def run_chunk(
            chunk: list[tuple[int, AIExtractedEntity, CRMEntity, float]],
        ) -> dict[int, DeduplicateResult]:
            if len(chunk) == 1:
                list_idx, extracted, candidate, _sim = chunk[0]
                dr = await self._call_deduplicate_agent(extracted, candidate)
                return {list_idx: dr}
            return await self._call_deduplicate_batch_agent(chunk)

        chunk_results = await run_chunked_map(
            need_llm,
            max_pairs,
            run_chunk,
            max_concurrent=max_concurrent,
        )
        merged: dict[int, DeduplicateResult] = {}
        for part in chunk_results:
            merged.update(part)
        if len(merged) != len(need_llm):
            raise ValueError(
                f"dedup LLM: ожидалось {len(need_llm)} решений, получено {len(merged)}"
            )
        return merged

    def _merge_descriptions(self, existing: str | None, new: str | None) -> str:
        """Объединяет описания"""
        if not existing:
            return new or ""
        if not new:
            return existing
        if new.lower() in existing.lower():
            return existing
        return f"{existing}\n\n{new}"

    async def _call_deduplicate_agent(
        self, extracted: AIExtractedEntity, candidate: CRMEntity
    ) -> DeduplicateResult:
        """Вызывает агента со skill deduplicate для сравнения сущностей"""
        settings = get_settings()
        flows_base_url = settings.server.get_flows_service_url().rstrip("/")

        variables = {
            **_crm_llm_interface_language_vars(),
            "extracted_entity": {
                "type": extracted.entity_type,
                "entity_subtype": extracted.entity_subtype,
                "name": extracted.name,
                "description": extracted.description,
                "attributes": extracted.attributes,
            },
            "candidate_entity": {
                "type": candidate.entity_type,
                "entity_subtype": candidate.entity_subtype,
                "name": candidate.name,
                "description": candidate.description,
                "attributes": candidate.attributes,
            },
        }

        response = await self._a2a_client.send_task(
            base_url=f"{flows_base_url}/flows/api/v1/crm",
            content=f"Compare: {extracted.name} vs {candidate.name}",
            branch_id="deduplicate",
            metadata={"variables": variables},
        )

        result_data = self._extract_data_from_a2a_response(response)
        if not isinstance(result_data, dict):
            result_data = {}
        for _ in range(8):
            if "is_duplicate" in result_data or result_data.get("action"):
                break
            nested = result_data.get("structured_output")
            if isinstance(nested, dict):
                result_data = nested
                continue
            break

        return DeduplicateResult(
            is_duplicate=result_data.get("is_duplicate", False),
            confidence=result_data.get("confidence", 0.0),
            reason=result_data.get("reason", ""),
            action=result_data.get("action", "create"),
            existing_entity_id=candidate.entity_id if result_data.get("is_duplicate") else None,
            existing_entity_name=candidate.name if result_data.get("is_duplicate") else None,
            merged_attributes=result_data.get("merged_attributes"),
            merged_description=result_data.get("merged_description"),
        )

    @staticmethod
    def _normalize_deduplicate_batch_dict(result_data: dict[str, Any]) -> dict[str, Any]:
        """
        Приводит ответ skill deduplicate_batch к виду с ключом decisions: list у корня.

        Structured output и A2A могут дать вложенные structured_output или JSON-строку в decisions.
        """
        if not isinstance(result_data, dict):
            raise ValueError("deduplicate_batch: тело ответа агента должно быть объектом")

        cur: dict[str, Any] = result_data
        for _ in range(8):
            if "decisions" in cur:
                break
            nested = cur.get("structured_output")
            if isinstance(nested, dict):
                cur = nested
                continue
            break

        if "decisions" not in cur:
            raise ValueError(
                "deduplicate_batch: нет поля decisions (проверьте structured_output и артефакты A2A)"
            )

        decisions = cur["decisions"]
        if isinstance(decisions, str) and decisions.strip():
            try:
                parsed = json.loads(decisions)
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(
                    "deduplicate_batch: поле decisions — невалидная JSON-строка"
                ) from e
            if isinstance(parsed, dict) and "pair_index" in parsed:
                parsed = [parsed]
            elif not isinstance(parsed, list):
                raise ValueError(
                    "deduplicate_batch: после разбора JSON поле decisions должно быть массивом"
                )
            out = dict(cur)
            out["decisions"] = parsed
            cur = out

        decisions = cur["decisions"]
        if isinstance(decisions, dict) and "pair_index" in decisions:
            cur = {**cur, "decisions": [decisions]}

        return cur

    async def _call_deduplicate_batch_agent(
        self,
        chunk: list[tuple[int, AIExtractedEntity, CRMEntity, float]],
    ) -> dict[int, DeduplicateResult]:
        """Один LLM-вызов для нескольких пар (извлечённая vs кандидат из RAG)."""
        settings = get_settings()
        flows_base_url = settings.server.get_flows_service_url().rstrip("/")

        pairs_for_prompt: list[dict[str, Any]] = []
        for pair_index, (list_idx, extracted, candidate, similarity) in enumerate(chunk):
            pairs_for_prompt.append(
                {
                    "pair_index": pair_index,
                    "list_index": list_idx,
                    "vector_similarity": similarity,
                    "extracted_entity": {
                        "type": extracted.entity_type,
                        "entity_subtype": extracted.entity_subtype,
                        "name": extracted.name,
                        "description": extracted.description,
                        "attributes": extracted.attributes,
                    },
                    "candidate_entity": {
                        "type": candidate.entity_type,
                        "entity_subtype": candidate.entity_subtype,
                        "name": candidate.name,
                        "description": candidate.description,
                        "attributes": candidate.attributes,
                    },
                }
            )

        variables = {
            **_crm_llm_interface_language_vars(),
            "pairs_json": json.dumps(pairs_for_prompt, ensure_ascii=False),
        }

        response = await self._a2a_client.send_task(
            base_url=f"{flows_base_url}/flows/api/v1/crm",
            content="Batch deduplicate entity pairs",
            branch_id="deduplicate_batch",
            metadata={"variables": variables},
        )

        raw = self._extract_data_from_a2a_response(response)
        result_data = self._normalize_deduplicate_batch_dict(raw)
        decisions = result_data["decisions"]
        if not isinstance(decisions, list):
            raise ValueError("deduplicate_batch: поле decisions должно быть массивом")
        if len(decisions) != len(chunk):
            raise ValueError(
                f"deduplicate_batch: ожидалось {len(chunk)} элементов decisions, получено {len(decisions)}"
            )

        by_pair_index: dict[int, dict[str, Any]] = {}
        for dec in decisions:
            if not isinstance(dec, dict):
                raise ValueError("deduplicate_batch: каждый элемент decisions должен быть объектом")
            pi = dec.get("pair_index")
            if not isinstance(pi, int):
                raise ValueError(
                    "deduplicate_batch: pair_index обязателен и должен быть целым числом"
                )
            by_pair_index[pi] = dec

        out: dict[int, DeduplicateResult] = {}
        for pair_index in range(len(chunk)):
            dec = by_pair_index.get(pair_index)
            if dec is None:
                raise ValueError(f"deduplicate_batch: нет решения для pair_index={pair_index}")
            list_idx, extracted, candidate, _sim = chunk[pair_index]
            is_dup = bool(dec.get("is_duplicate", False))
            action_raw = dec.get("action", "create")
            if action_raw not in ("merge", "create"):
                raise ValueError(
                    f"deduplicate_batch: action должен быть merge или create, получено {action_raw!r}"
                )
            out[list_idx] = DeduplicateResult(
                is_duplicate=is_dup,
                confidence=float(dec.get("confidence", 0.0)),
                reason=str(dec.get("reason", "")),
                action=action_raw,
                existing_entity_id=candidate.entity_id if is_dup else None,
                existing_entity_name=candidate.name if is_dup else None,
                merged_attributes=dec.get("merged_attributes"),
                merged_description=dec.get("merged_description"),
            )
        return out
