"""
Репозиторий для CRM entities в PostgreSQL.

Структурные данные -- в crm_entities (CRM DB).
Семантический индекс и поиск -- ``RAGRepository`` (in-process провайдер ``RAG_IN_PROCESS_PROVIDER_ID``, см. ``core/rag/constants.py``).
"""

import base64
import json
from collections.abc import Set as AbstractSet
from datetime import UTC, date, datetime
from typing import ClassVar, override
from typing import cast as type_cast

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    and_,
    cast,
    delete,
    func,
    literal,
    or_,
    select,
    tuple_,
    type_coerce,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import ColumnElement

import core.tracing.attributes as trace_attributes
from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import CRMEntity
from apps.crm.models.api import SemanticTextIndexStatus
from apps.crm.types import JsonObject
from core.config import get_settings
from core.context import get_context
from core.db.utils import get_rowcount
from core.logging import get_logger
from core.rag import RAGRepository
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.post_retrieval_rerank import apply_rerank_after_retrieve
from core.rag.providers.pgvector_provider import PgVectorProvider
from core.tracing.operation_span import traced_operation

logger = get_logger(__name__)

_CRM_HYBRID_RRF_K = 60

type _FilterScalar = str | int | float | bool | date | datetime | None


class EntityRepository(BaseCRMRepository[CRMEntity]):
    """
    Репозиторий для CRM entities.

    CRUD -- через crm_entities (PostgreSQL).
    Семантика -- ``RAGRepository`` (загрузка текста и поиск через in-process провайдер ``RAG_IN_PROCESS_PROVIDER_ID``).
    """

    def __init__(self, db: CRMDatabase, rag_repository: RAGRepository) -> None:
        super().__init__(db=db)
        self._rag: RAGRepository = rag_repository

    @property
    @override
    def model_class(self) -> type[CRMEntity]:
        return CRMEntity

    @property
    @override
    def id_field(self) -> str:
        return "entity_id"

    @override
    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id

    _SKIP_SEARCH_ATTRIBUTE_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "ai_analysis_draft",  # большой JSON-блок, шум в векторном индексе
            "ai_analysis_last_error",
            "ai_analysis_last_error_at",
        }
    )

    def _build_search_text(self, entity: CRMEntity) -> str:
        """Формирует текст для семантического поиска."""
        parts = [entity.name]

        if entity.description:
            parts.append(entity.description)

        for key, value in (entity.attributes or {}).items():
            if not value:
                continue
            if key in self._SKIP_SEARCH_ATTRIBUTE_KEYS:
                continue
            if key == "attachment_summaries" and isinstance(value, list):
                for item in type_cast(list[object], value):
                    if isinstance(item, dict):
                        item_dict = type_cast(dict[str, object], item)
                        raw_filename = item_dict.get("filename", "")
                        raw_summary = item_dict.get("summary", "")
                        filename = raw_filename if isinstance(raw_filename, str) else ""
                        summary = raw_summary if isinstance(raw_summary, str) else ""
                        if summary:
                            label = f"Вложение {filename}: " if filename else ""
                            parts.append(f"{label}{summary}")
                continue
            parts.append(f"{key}: {value}")

        if entity.tags:
            parts.append(f"Теги: {', '.join(entity.tags)}")

        if entity.is_note and entity.entity_subtype:
            parts.append(f"Тип: {entity.entity_subtype}")

        if entity.is_task:
            if entity.priority:
                parts.append(f"Приоритет: {entity.priority}")
            if entity.due_date:
                parts.append(f"Дедлайн: {entity.due_date}")

        return "\n".join(parts)

    def _rag_chunk_metadata(self, entity: CRMEntity) -> dict[str, object]:
        return {
            "document_id": entity.entity_id,
            "company_id": entity.company_id,
            "entity_type": entity.entity_type,
            "ttl_seconds": 0,
        }

    @staticmethod
    def _attribute_text_path_expression(*path: str) -> ColumnElement[str]:
        if not path:
            raise ValueError("JSONB attribute path must not be empty")
        return type_cast(
            ColumnElement[str],
            func.jsonb_extract_path_text(CRMEntity.attributes, *path),
        )

    @staticmethod
    def _attribute_json_path_expression(*path: str) -> ColumnElement[object]:
        if not path:
            raise ValueError("JSONB attribute path must not be empty")
        return type_cast(
            ColumnElement[object],
            type_coerce(func.jsonb_extract_path(CRMEntity.attributes, *path), JSONB),
        )

    async def batch_semantic_text_index_status(
        self,
        entities: list[CRMEntity],
    ) -> dict[str, SemanticTextIndexStatus | None]:
        """
        Статус семантического индекса основного текста (document_id = entity_id).

        Для активного провайдера не-pgvector — по каждой сущности ``None``.
        """
        if not entities:
            return {}
        provider = self._rag.provider
        if not isinstance(provider, PgVectorProvider):
            return {e.entity_id: None for e in entities}
        triples: list[tuple[str, str, str]] = []
        for e in entities:
            ns = (e.namespace or "default").strip()
            triples.append((ns, str(e.entity_id).strip(), str(e.company_id).strip()))
        triple_status = await provider.batch_document_semantic_index_status(triples)
        result: dict[str, SemanticTextIndexStatus | None] = {}
        for e in entities:
            ns = (e.namespace or "default").strip()
            key = (ns, str(e.entity_id).strip(), str(e.company_id).strip())
            status = triple_status[key]
            result[e.entity_id] = status
        return result

    @staticmethod
    def _parse_datetime_filter_value(value: object) -> datetime:
        if isinstance(value, datetime):
            parsed_value = value
        elif isinstance(value, str):
            parsed_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("Unsupported datetime filter value type")
        if parsed_value.tzinfo is None:
            return parsed_value.replace(tzinfo=UTC)
        return parsed_value

    async def find_by_attribute(
        self,
        entity_type: str,
        attribute_key: str,
        attribute_value: str,
        company_id: str | None = None,
    ) -> list[CRMEntity]:
        """Поиск сущностей по типу и значению в attributes (jsonb)."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(CRMEntity).where(
                CRMEntity.company_id == cid,
                CRMEntity.entity_type == entity_type,
                self._attribute_text_path_expression(attribute_key) == attribute_value,
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def find_by_external_ref(
        self,
        *,
        company_id: str,
        namespace: str,
        entity_type: str,
        source_id: str,
        record_id: str,
    ) -> list[CRMEntity]:
        """Поиск по attributes.external_refs[source_id].record_id в пределах company и namespace."""
        cid = company_id
        ns = namespace
        sid = source_id
        rid = str(record_id).strip()
        if not rid:
            return []
        if not sid.strip():
            return []
        async with self._db.session() as session:
            stmt = select(CRMEntity).where(
                CRMEntity.company_id == cid,
                CRMEntity.namespace == ns,
                CRMEntity.entity_type == entity_type,
                self._attribute_text_path_expression("external_refs", sid, "record_id") == rid,
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # -- CRUD --

    @override
    async def create(self, entity: CRMEntity) -> CRMEntity:
        """Создает entity в crm_entities + ставит индексацию search_text в сервисе rag (воркер)."""
        async with self._db.session() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)

        search_text = self._build_search_text(entity)
        rag_namespace = entity.namespace or "default"
        try:
            _ = await self._rag.upload_text(
                namespace_id=rag_namespace,
                text=search_text,
                document_name=entity.entity_id,
                metadata=self._rag_chunk_metadata(entity),
            )
        except Exception as exc:
            logger.warning(
                f"RAG indexing failed for entity {entity.entity_id} (will be retried by reembed task): {exc}"
            )

        logger.info(f"Created entity: {entity.entity_id}, type={entity.full_type}")
        return entity

    @override
    async def get(self, entity_id: str) -> CRMEntity | None:
        """Получает entity по ID."""
        async with self._db.session() as session:
            stmt = select(CRMEntity).where(CRMEntity.entity_id == entity_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_by_entity_ids_ordered(
        self,
        entity_ids: list[str],
        *,
        company_id: str | None = None,
    ) -> list[CRMEntity]:
        cid = company_id or self._get_company_id()
        normalized = [str(eid).strip() for eid in entity_ids if str(eid).strip()]
        if not normalized:
            return []
        async with self._db.session() as session:
            stmt = select(CRMEntity).where(
                CRMEntity.company_id == cid,
                CRMEntity.entity_id.in_(normalized),
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
        by_id = {e.entity_id: e for e in rows}
        return [by_id[eid] for eid in normalized if eid in by_id]

    async def get_by_ids(self, entity_ids: list[str]) -> list[CRMEntity]:
        """Batch загрузка сущностей по списку ID без фильтра по company (для cross-company графов)."""
        normalized = [str(eid).strip() for eid in entity_ids if str(eid).strip()]
        if not normalized:
            return []
        async with self._db.session() as session:
            stmt = select(CRMEntity).where(CRMEntity.entity_id.in_(normalized))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @override
    async def update(self, entity: CRMEntity) -> CRMEntity:
        """Обновляет entity в crm_entities + переиндексирует через сервис rag."""
        async with self._db.session() as session:
            merged = await session.merge(entity)
            await session.commit()
            await session.refresh(merged)

        rag_namespace = entity.namespace or "default"
        try:
            _ = await self._rag.delete_document(rag_namespace, entity.entity_id)
            search_text = self._build_search_text(entity)
            _ = await self._rag.upload_text(
                namespace_id=rag_namespace,
                text=search_text,
                document_name=entity.entity_id,
                metadata=self._rag_chunk_metadata(entity),
            )
        except Exception as exc:
            logger.warning(
                f"RAG re-indexing failed for entity {entity.entity_id} (will be retried by reembed task): {exc}"
            )

        logger.info(f"Updated entity: {entity.entity_id}, type={entity.full_type}")
        return merged

    @override
    async def delete(self, entity_id: str) -> bool:
        """Удаляет entity из crm_entities + индекс в сервисе rag."""
        async with self._db.session() as session:
            namespace_stmt = select(CRMEntity.namespace).where(CRMEntity.entity_id == entity_id)
            namespace_row = await session.execute(namespace_stmt)
            rag_namespace = namespace_row.scalar() or "default"

            stmt = delete(CRMEntity).where(CRMEntity.entity_id == entity_id)
            result = await session.execute(stmt)
            await session.commit()
            deleted = get_rowcount(result) > 0

        if deleted:
            _ = await self._rag.delete_document(rag_namespace, entity_id)
            logger.info(f"Deleted entity: {entity_id}")

        return deleted

    async def rewrite_source_entity_id_references(
        self,
        company_id: str,
        old_entity_id: str,
        new_entity_id: str,
    ) -> int:
        """Поля source_entity_id в crm_entities, указывающие на old, переназначаются на new."""
        if old_entity_id == new_entity_id:
            raise ValueError("old_entity_id и new_entity_id должны различаться")
        async with self._db.session() as session:
            result = await session.execute(
                update(CRMEntity)
                .where(
                    CRMEntity.company_id == company_id,
                    CRMEntity.source_entity_id == old_entity_id,
                )
                .values(source_entity_id=new_entity_id)
            )
            await session.commit()
            return get_rowcount(result)

    # -- List / Filter --

    @staticmethod
    def encode_cursor(created_at: datetime, entity_id: str) -> str:
        payload = json.dumps({"ts": created_at.isoformat(), "id": entity_id})
        return base64.urlsafe_b64encode(payload.encode()).decode()

    @staticmethod
    def decode_cursor(cursor: str) -> tuple[datetime, str]:
        raw_payload = type_cast(
            object,
            json.loads(base64.urlsafe_b64decode(cursor.encode()).decode()),
        )
        if not isinstance(raw_payload, dict):
            raise ValueError("Cursor payload must be an object")
        payload = type_cast(JsonObject, raw_payload)
        raw_ts = payload.get("ts")
        raw_id = payload.get("id")
        if not isinstance(raw_ts, str) or not isinstance(raw_id, str):
            raise ValueError("Cursor payload has invalid shape")
        ts = datetime.fromisoformat(raw_ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts, raw_id

    async def list_by_cursor(
        self,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: JsonObject | None = None,
        filter_field_types: dict[str, str] | None = None,
        limit: int = 100,
        company_id: str | None = None,
        cursor: str | None = None,
        *,
        list_note_family: bool = False,
        note_family_legacy_entity_types: list[str] | None = None,
    ) -> tuple[list[CRMEntity], str | None, bool]:
        """
        Entities c SQL-фильтрами и cursor-пагинацией.

        Returns:
            (entities, next_cursor, has_more)
        """
        cid = company_id or self._get_company_id()

        async with self._db.session() as session:
            stmt = select(CRMEntity).where(CRMEntity.company_id == cid)

            if list_note_family:
                legacy = note_family_legacy_entity_types or []
                if len(legacy) > 0:
                    stmt = stmt.where(
                        or_(
                            CRMEntity.entity_type == "note",
                            CRMEntity.entity_type.in_(legacy),
                        )
                    )
                else:
                    stmt = stmt.where(CRMEntity.entity_type == "note")
            elif entity_type:
                stmt = stmt.where(CRMEntity.entity_type == entity_type)
            if entity_subtype:
                stmt = stmt.where(CRMEntity.entity_subtype == entity_subtype)
            if namespace:
                stmt = stmt.where(CRMEntity.namespace == namespace)

            if filters:
                stmt = stmt.where(self._build_filter_expression(filters, filter_field_types))

            if cursor:
                cursor_ts, cursor_id = self.decode_cursor(cursor)
                stmt = stmt.where(
                    tuple_(CRMEntity.created_at, CRMEntity.entity_id)
                    < tuple_(literal(cursor_ts), literal(cursor_id))
                )

            stmt = stmt.order_by(
                CRMEntity.created_at.desc(),
                CRMEntity.entity_id.desc(),
            ).limit(limit + 1)

            result = await session.execute(stmt)
            rows = list(result.scalars().all())

        has_more = len(rows) > limit
        entities = rows[:limit]

        next_cursor = None
        if has_more and entities:
            last = entities[-1]
            next_cursor = self.encode_cursor(last.created_at, last.entity_id)

        return entities, next_cursor, has_more

    async def count_all(
        self,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: JsonObject | None = None,
        filter_field_types: dict[str, str] | None = None,
        company_id: str | None = None,
    ) -> int:
        """Считает entities с теми же условиями, что и list_by_cursor (без лимита)."""
        cid = company_id or self._get_company_id()

        async with self._db.session() as session:
            stmt = select(func.count(CRMEntity.entity_id)).where(CRMEntity.company_id == cid)

            if entity_type:
                stmt = stmt.where(CRMEntity.entity_type == entity_type)
            if entity_subtype:
                stmt = stmt.where(CRMEntity.entity_subtype == entity_subtype)
            if namespace:
                stmt = stmt.where(CRMEntity.namespace == namespace)

            if filters:
                stmt = stmt.where(self._build_filter_expression(filters, filter_field_types))

            result = await session.execute(stmt)
            value = result.scalar()
            if value is None:
                raise ValueError("Entity count query returned empty value")
            return int(value)

    async def count_notes_with_analysis_draft_not_applied(
        self,
        namespace: str,
        *,
        company_id: str | None = None,
    ) -> int:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(func.count(CRMEntity.entity_id)).where(
                CRMEntity.company_id == cid,
                CRMEntity.namespace == namespace,
                CRMEntity.entity_type == "note",
                CRMEntity.attributes["ai_analysis_draft"].is_not(None),
                CRMEntity.attributes["ai_analysis_applied_at"].is_(None),
            )
            result = await session.execute(stmt)
            value = result.scalar()
            if value is None:
                raise ValueError("Notes draft analysis count returned empty value")
            return int(value)

    async def list_notes_with_analysis_draft_not_applied(
        self,
        namespace: str,
        *,
        limit: int,
        company_id: str | None = None,
    ) -> list[CRMEntity]:
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(CRMEntity)
                .where(
                    CRMEntity.company_id == cid,
                    CRMEntity.namespace == namespace,
                    CRMEntity.entity_type == "note",
                    CRMEntity.attributes["ai_analysis_draft"].is_not(None),
                    CRMEntity.attributes["ai_analysis_applied_at"].is_(None),
                )
                .order_by(CRMEntity.updated_at.desc(), CRMEntity.entity_id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_created_at_bounds(
        self,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        company_id: str | None = None,
    ) -> tuple[datetime | None, datetime | None, int]:
        """Возвращает min/max created_at и количество сущностей."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(
                func.min(CRMEntity.created_at),
                func.max(CRMEntity.created_at),
                func.count(CRMEntity.entity_id),
            ).where(CRMEntity.company_id == cid)
            if entity_type:
                stmt = stmt.where(CRMEntity.entity_type == entity_type)
            if entity_subtype:
                stmt = stmt.where(CRMEntity.entity_subtype == entity_subtype)
            if namespace:
                stmt = stmt.where(CRMEntity.namespace == namespace)
            result = await session.execute(stmt)
            row = type_cast(
                tuple[object | None, object | None, object],
                type_cast(object, result.one()),
            )
            min_created_at, max_created_at, total_entities = row
            if min_created_at is not None and not isinstance(min_created_at, datetime):
                raise ValueError("min(created_at) returned invalid value")
            if max_created_at is not None and not isinstance(max_created_at, datetime):
                raise ValueError("max(created_at) returned invalid value")
            if not isinstance(total_entities, int):
                raise ValueError("count(entity_id) returned invalid value")
            return min_created_at, max_created_at, total_entities

    @staticmethod
    def _parse_date_filter_value(value: object) -> date:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        raise ValueError("Unsupported date filter value type")

    def _build_filter_expression(
        self, node: JsonObject, field_types: dict[str, str] | None
    ) -> ColumnElement[bool]:
        if not field_types:
            raise ValueError("field_types are required when filters are provided")
        if "$and" in node:
            and_nodes = self._filter_node_list(node["$and"], "$and")
            return and_(*[self._build_filter_expression(item, field_types) for item in and_nodes])
        if "$or" in node:
            or_nodes = self._filter_node_list(node["$or"], "$or")
            return or_(*[self._build_filter_expression(item, field_types) for item in or_nodes])

        field_name = self._required_filter_string(node, "field")
        operator = self._required_filter_string(node, "op")
        if "value" not in node:
            raise ValueError("Filter leaf requires value")
        value = node["value"]
        if field_name not in field_types:
            raise ValueError(f"Unknown filter field: {field_name}")
        field_type = field_types[field_name]
        column_expr = self._resolve_field_expression(field_name, field_type)
        return self._build_leaf_expression(column_expr, field_name, field_type, operator, value)

    @staticmethod
    def _filter_node_list(value: object, operator: str) -> list[JsonObject]:
        if not isinstance(value, list):
            raise ValueError(f"{operator} requires non-empty list")
        raw_nodes = type_cast(list[object], value)
        if not raw_nodes:
            raise ValueError(f"{operator} requires non-empty list")
        nodes: list[JsonObject] = []
        for item in raw_nodes:
            if not isinstance(item, dict):
                raise ValueError(f"{operator} items must be filter objects")
            nodes.append(type_cast(JsonObject, item))
        return nodes

    @staticmethod
    def _required_filter_string(node: JsonObject, key: str) -> str:
        raw_value = node.get(key)
        if not isinstance(raw_value, str) or raw_value.strip() == "":
            raise ValueError(f"Filter field {key!r} must be a non-empty string")
        return raw_value

    def _resolve_field_expression(self, field_name: str, field_type: str) -> ColumnElement[object]:
        if field_name.startswith("attributes."):
            attr_name = field_name.split(".", 1)[1]
            attr_text = self._attribute_text_path_expression(attr_name)
            if field_type == "integer":
                return type_cast(ColumnElement[object], cast(attr_text, Integer))
            if field_type == "number":
                return type_cast(ColumnElement[object], cast(attr_text, Float))
            if field_type == "boolean":
                return type_cast(ColumnElement[object], cast(attr_text, Boolean))
            if field_type == "date":
                return type_cast(ColumnElement[object], cast(attr_text, Date))
            if field_type == "datetime":
                return type_cast(
                    ColumnElement[object],
                    cast(attr_text, DateTime(timezone=True)),
                )
            if field_type == "array":
                return self._attribute_json_path_expression(attr_name)
            return type_cast(ColumnElement[object], attr_text)

        if field_name == "entity_type":
            return self._column_expression(CRMEntity.entity_type)
        if field_name == "entity_subtype":
            return self._column_expression(CRMEntity.entity_subtype)
        if field_name == "namespace":
            return self._column_expression(CRMEntity.namespace)
        if field_name == "status":
            return self._column_expression(CRMEntity.status)
        if field_name == "priority":
            return self._column_expression(CRMEntity.priority)
        if field_name == "user_id":
            return self._column_expression(CRMEntity.user_id)
        if field_name == "name":
            return self._column_expression(CRMEntity.name)
        if field_name == "description":
            return self._column_expression(CRMEntity.description)
        if field_name == "note_date":
            return self._column_expression(CRMEntity.note_date)
        if field_name == "due_date":
            return self._column_expression(CRMEntity.due_date)
        if field_name == "created_at":
            return self._column_expression(CRMEntity.created_at)
        if field_name == "tags":
            return self._column_expression(CRMEntity.tags)
        raise ValueError(f"Unsupported filter field: {field_name}")

    def _coerce_scalar_value(self, field_type: str, value: object) -> _FilterScalar:
        if field_type == "integer":
            return self._coerce_int_filter_value(value)
        if field_type == "number":
            return self._coerce_float_filter_value(value)
        if field_type == "boolean":
            if isinstance(value, bool):
                return value
            raise ValueError("Boolean filter value must be bool")
        if field_type == "date":
            return self._parse_date_filter_value(value)
        if field_type == "datetime":
            return self._parse_datetime_filter_value(value)
        if value is None or isinstance(value, str | int | float | bool):
            return value
        raise ValueError("Scalar filter value must be string, number, boolean, or null")

    @staticmethod
    def _coerce_int_filter_value(value: object) -> int:
        if isinstance(value, bool):
            raise ValueError("Integer filter value must not be bool")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip() != "":
            return int(value)
        raise ValueError("Integer filter value must be int or numeric string")

    @staticmethod
    def _coerce_float_filter_value(value: object) -> float:
        if isinstance(value, bool):
            raise ValueError("Number filter value must not be bool")
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str) and value.strip() != "":
            return float(value)
        raise ValueError("Number filter value must be number or numeric string")

    @staticmethod
    def _sql_bool_expression(expression: ColumnElement[bool]) -> ColumnElement[bool]:
        return expression

    @staticmethod
    def _string_expression(column_expr: ColumnElement[object]) -> ColumnElement[str]:
        return type_cast(ColumnElement[str], column_expr)

    @staticmethod
    def _column_expression(expression: object) -> ColumnElement[object]:
        return type_cast(ColumnElement[object], expression)

    @staticmethod
    def _object_list(value: object, operator: str) -> list[object]:
        if not isinstance(value, list):
            raise ValueError(f"{operator} requires non-empty list value")
        values = type_cast(list[object], value)
        if not values:
            raise ValueError(f"{operator} requires non-empty list value")
        return values

    @staticmethod
    def _rank_to_float(value: object) -> float:
        if isinstance(value, bool):
            raise ValueError("FTS rank returned invalid bool value")
        if isinstance(value, int | float):
            return float(value)
        raise ValueError("FTS rank returned invalid value")

    def _build_leaf_expression(
        self,
        column_expr: ColumnElement[object],
        field_name: str,
        field_type: str,
        operator: str,
        value: object,
    ) -> ColumnElement[bool]:
        if operator == "$contains":
            if field_name == "tags":
                return self._sql_bool_expression(CRMEntity.tags.contains([value]))
            if field_type == "array":
                return self._sql_bool_expression(column_expr.contains([value]))
            return self._sql_bool_expression(
                self._string_expression(column_expr).ilike(f"%{value}%")
            )

        if operator in {"$in", "$nin"}:
            values = self._object_list(value, operator)
            coerced_values = [self._coerce_scalar_value(field_type, item) for item in values]
            expression = column_expr.in_(coerced_values)
            if operator == "$nin":
                return self._sql_bool_expression(~expression)
            return self._sql_bool_expression(expression)

        coerced = self._coerce_scalar_value(field_type, value)
        if operator == "$eq":
            return self._sql_bool_expression(column_expr == coerced)
        if operator == "$ne":
            return self._sql_bool_expression(column_expr != coerced)
        if operator == "$gt":
            return self._sql_bool_expression(column_expr > coerced)
        if operator == "$gte":
            return self._sql_bool_expression(column_expr >= coerced)
        if operator == "$lt":
            return self._sql_bool_expression(column_expr < coerced)
        if operator == "$lte":
            return self._sql_bool_expression(column_expr <= coerced)
        raise ValueError(f"Unsupported filter operator: {operator}")

    async def count_by_namespace(
        self,
        namespace: str,
        company_id: str | None = None,
        exclude_entity_types: AbstractSet[str] | None = None,
    ) -> int:
        """Считает количество сущностей в namespace."""
        if not namespace:
            raise ValueError("Namespace is required")

        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(func.count(CRMEntity.entity_id)).where(
                CRMEntity.company_id == cid,
                CRMEntity.namespace == namespace,
            )
            if exclude_entity_types:
                stmt = stmt.where(CRMEntity.entity_type.notin_(exclude_entity_types))
            result = await session.execute(stmt)
            value = result.scalar()
            if value is None:
                raise ValueError("Entity count query returned empty value")
            return int(value)

    async def list_used_entity_types_by_namespace(
        self,
        namespace: str,
        company_id: str | None = None,
        exclude_entity_types: AbstractSet[str] | None = None,
    ) -> list[str]:
        """Возвращает список типов сущностей, используемых в namespace."""
        if not namespace:
            raise ValueError("Namespace is required")

        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(CRMEntity.entity_type)
                .where(
                    CRMEntity.company_id == cid,
                    CRMEntity.namespace == namespace,
                )
                .distinct()
            )
            if exclude_entity_types:
                stmt = stmt.where(CRMEntity.entity_type.notin_(exclude_entity_types))
            result = await session.execute(stmt)
            type_ids = [item for item in result.scalars().all() if item.strip()]
            return sorted(type_ids)

    # -- Semantic Search --

    async def search_with_similarity(
        self,
        query: str,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: JsonObject | None = None,
        filter_field_types: dict[str, str] | None = None,
        limit: int = 10,
        company_id: str | None = None,
    ) -> list[tuple[CRMEntity, float]]:
        """
        Семантический поиск entities с возвратом similarity (0.0-1.0)
        через RAG index + выборку сущностей из CRM БД.
        """
        cid = company_id or self._get_company_id()
        resolved_namespace = namespace or "default"
        actx = get_context()
        if actx is None or str(actx.user.user_id).strip() == "":
            raise ValueError("Контекст пользователя обязателен для семантического поиска CRM.")
        user_id = str(actx.user.user_id).strip()
        async with traced_operation(
            "crm.semantic.search_entities",
            event_type="crm.search",
            operation_category="embedding",
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: cid,
                trace_attributes.ATTR_USER_ID: user_id,
                trace_attributes.ATTR_CRM_QUERY_MODE: "semantic_vector",
                trace_attributes.ATTR_CRM_ENTITY_TYPE: entity_type or "",
                "platform.crm.search_limit": limit,
                "platform.crm.namespace": resolved_namespace,
            },
        ) as search_span:
            search_filters: dict[str, object] = {"company_id": cid}
            if entity_type:
                search_filters["entity_type"] = entity_type

            # Берем больше chunk-результатов, чтобы после дедупа по document_id
            # сохранить достаточное число кандидатов.
            search_results = await self._rag.search(
                namespace_id=resolved_namespace,
                query=query,
                limit=max(limit * 4, limit),
                filters=search_filters,
            )
            settings = get_settings()
            search_results = await apply_rerank_after_retrieve(
                results=search_results,
                query=query,
                provider_name=RAG_IN_PROCESS_PROVIDER_ID,
                request_rerank=None,
                profile_sd=None,
                settings=settings,
            )
            if not search_results:
                logger.info(f"search_with_similarity('{query[:50]}...') -> 0 entities")
                search_span.set_attribute("platform.crm.search_hits_raw", 0)
                return []

            resolved_order: list[str] = []
            score_by_resolved: dict[str, float] = {}
            for item in search_results:
                entity_id = item.document_id
                if entity_id not in score_by_resolved:
                    score_by_resolved[entity_id] = item.score
                    resolved_order.append(entity_id)
                elif item.score > score_by_resolved[entity_id]:
                    score_by_resolved[entity_id] = item.score

            ordered_entity_ids = resolved_order

            async with self._db.session() as session:
                stmt = select(CRMEntity).where(
                    CRMEntity.company_id == cid,
                    CRMEntity.entity_id.in_(ordered_entity_ids),
                )
                if entity_type:
                    stmt = stmt.where(CRMEntity.entity_type == entity_type)
                if entity_subtype:
                    stmt = stmt.where(CRMEntity.entity_subtype == entity_subtype)
                if namespace:
                    stmt = stmt.where(CRMEntity.namespace == namespace)
                if filters:
                    stmt = stmt.where(self._build_filter_expression(filters, filter_field_types))
                result = await session.execute(stmt)
                matched_entities = list(result.scalars().all())

            entities_by_id = {entity.entity_id: entity for entity in matched_entities}
            scored_entities: list[tuple[CRMEntity, float]] = []
            for document_id in ordered_entity_ids:
                entity = entities_by_id.get(document_id)
                if entity is None:
                    continue
                score = score_by_resolved[document_id]
                normalized_similarity = max(0.0, min(1.0, float(score)))
                scored_entities.append((entity, normalized_similarity))
                if len(scored_entities) >= limit:
                    break

            search_span.set_attribute("platform.crm.search_results_count", len(scored_entities))
            logger.info(
                f"search_with_similarity('{query[:50]}...') -> {len(scored_entities)} entities"
            )
            return scored_entities

    async def hybrid_search(
        self,
        query: str,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: JsonObject | None = None,
        filter_field_types: dict[str, str] | None = None,
        limit: int = 10,
        company_id: str | None = None,
    ) -> list[tuple[CRMEntity, float, str]]:
        """
        Гибридный поиск: RRF (Reciprocal Rank Fusion) по tsvector FTS + pgvector semantic.
        Возвращает (entity, rrf_score, match_type).
        match_type: "text" | "semantic" | "hybrid" (найдено обоими).
        """
        k = _CRM_HYBRID_RRF_K
        rrf_max = 2.0 / (k + 1)  # теоретический максимум при ранге 1 в обоих списках

        fts_entities = await self.fts_search_ranked(
            query,
            entity_type,
            entity_subtype,
            namespace,
            filters,
            filter_field_types,
            limit * 3,
            company_id,
        )
        semantic_entities = await self.search_with_similarity(
            query,
            entity_type,
            entity_subtype,
            namespace,
            filters,
            filter_field_types,
            limit * 3,
            company_id,
        )

        fts_ranks: dict[str, int] = {}
        fts_map: dict[str, CRMEntity] = {}
        for rank, (entity, _) in enumerate(fts_entities, start=1):
            fts_ranks[entity.entity_id] = rank
            fts_map[entity.entity_id] = entity

        sem_ranks: dict[str, int] = {}
        sem_map: dict[str, CRMEntity] = {}
        for rank, (entity, _) in enumerate(semantic_entities, start=1):
            sem_ranks[entity.entity_id] = rank
            sem_map[entity.entity_id] = entity

        all_ids = set(fts_ranks.keys()) | set(sem_ranks.keys())
        scored: list[tuple[str, float, str]] = []
        for eid in all_ids:
            rrf_score = 0.0
            in_fts = eid in fts_ranks
            in_sem = eid in sem_ranks
            if in_fts:
                rrf_score += 1.0 / (k + fts_ranks[eid])
            if in_sem:
                rrf_score += 1.0 / (k + sem_ranks[eid])
            match_type = "hybrid" if (in_fts and in_sem) else ("text" if in_fts else "semantic")
            scored.append((eid, rrf_score, match_type))

        scored.sort(key=lambda x: x[1], reverse=True)
        entity_pool = {**fts_map, **sem_map}

        results: list[tuple[CRMEntity, float, str]] = []
        for eid, rrf_score, match_type in scored[:limit]:
            entity = entity_pool[eid]
            normalized_score = min(1.0, rrf_score / rrf_max)
            results.append((entity, normalized_score, match_type))
        return results

    async def fts_search_ranked(
        self,
        query: str,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: JsonObject | None = None,
        filter_field_types: dict[str, str] | None = None,
        limit: int = 30,
        company_id: str | None = None,
    ) -> list[tuple[CRMEntity, float]]:
        """FTS поиск с ts_rank, отсортированный по релевантности."""
        cid = company_id or self._get_company_id()
        tsquery = func.plainto_tsquery("simple", query)
        rank_expr = func.ts_rank(CRMEntity.search_vector, tsquery)

        async with self._db.session() as session:
            stmt = (
                select(CRMEntity, rank_expr.label("fts_rank"))
                .where(
                    CRMEntity.company_id == cid,
                    CRMEntity.search_vector.op("@@")(tsquery),
                )
                .order_by(rank_expr.desc())
                .limit(limit)
            )
            if entity_type:
                stmt = stmt.where(CRMEntity.entity_type == entity_type)
            if entity_subtype:
                stmt = stmt.where(CRMEntity.entity_subtype == entity_subtype)
            if namespace:
                stmt = stmt.where(CRMEntity.namespace == namespace)
            if filters:
                stmt = stmt.where(self._build_filter_expression(filters, filter_field_types))

            result = await session.execute(stmt)
            rows = type_cast(list[tuple[CRMEntity, object]], result.all())

        return [(entity, self._rank_to_float(rank)) for entity, rank in rows]

    async def aggregate_facets(
        self,
        namespace: str | None = None,
        company_id: str | None = None,
    ) -> JsonObject:
        """Фасетная агрегация: по entity_type, status, месяц создания."""
        cid = company_id or self._get_company_id()
        month_expr = func.to_char(CRMEntity.created_at, "YYYY-MM").label("month")

        async with self._db.session() as session:
            base = select(CRMEntity).where(CRMEntity.company_id == cid)
            if namespace:
                base = base.where(CRMEntity.namespace == namespace)

            by_type_stmt = select(CRMEntity.entity_type, func.count().label("cnt")).where(
                CRMEntity.company_id == cid
            )
            if namespace:
                by_type_stmt = by_type_stmt.where(CRMEntity.namespace == namespace)
            by_type_stmt = by_type_stmt.group_by(CRMEntity.entity_type)
            type_rows = (await session.execute(by_type_stmt)).all()

            by_status_stmt = select(CRMEntity.status, func.count().label("cnt")).where(
                CRMEntity.company_id == cid
            )
            if namespace:
                by_status_stmt = by_status_stmt.where(CRMEntity.namespace == namespace)
            by_status_stmt = by_status_stmt.group_by(CRMEntity.status)
            status_rows = (await session.execute(by_status_stmt)).all()

            by_month_stmt = select(month_expr, func.count().label("cnt")).where(
                CRMEntity.company_id == cid
            )
            if namespace:
                by_month_stmt = by_month_stmt.where(CRMEntity.namespace == namespace)
            by_month_stmt = by_month_stmt.group_by(month_expr).order_by(month_expr)
            month_rows = (await session.execute(by_month_stmt)).all()

        return {
            "by_type": {row[0]: row[1] for row in type_rows},
            "by_status": {row[0]: row[1] for row in status_rows},
            "by_month": {row[0]: row[1] for row in month_rows},
        }
