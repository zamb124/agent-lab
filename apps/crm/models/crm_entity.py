"""Сущность CRM. Ответ списка и карточки — ``EntityResponse``: туда добавляются поля поиска и доступа."""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from datetime import UTC, date, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw
from pydantic import PrivateAttr, computed_field

from core.context import require_active_company
from core.logging import get_logger
from core.models.platform_model import PlatformModel
from core.pagination import CursorPage
from core.rag import BaseRAGProvider
from core.rag.models import RAGMetadata
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_object,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)

_SKIP_SEARCH_ATTRIBUTE_KEYS = frozenset(
    {
        "ai_analysis_draft",
        "ai_analysis_last_error",
        "ai_analysis_last_error_at",
    }
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _note_date_value(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value != "":
        return date.fromisoformat(value[:10])
    raise ValueError("note_date is required")


class CRMEntity(PlatformModel):
    """Строка ``crm_entities``, алиас ``crm``, ``__global_model__``.

    ``search_vector`` — generated ``tsvector`` и полем модели не является.
    """

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "crm_entities"
        indexes: list[Index] = [
            Index(["company_id", "entity_type"]),
            Index(["company_id", "namespace", "entity_type"]),
            Index(["company_id", "status"]),
            Index(["company_id", "user_id"]),
            Index(["company_id", "namespace"]),
            Index(["tags"], method="gin"),
            Index(["note_date"]),
        ]

    entity_id: str = DbField(db_pk=True, max_length=100)
    company_id: str = DbField(max_length=100)
    namespace: str = DbField(default="default", max_length=100)
    entity_type: str = DbField(max_length=100)
    name: str = DbField(max_length=500)
    user_id: str = DbField(max_length=100)
    created_at: datetime = DbField(default_factory=_utcnow)
    updated_at: datetime = DbField(default_factory=_utcnow)
    entity_subtype: str | None = DbField(default=None, max_length=100)
    description: str | None = DbField(default=None, db_type="TEXT")
    status: str = DbField(default="active", max_length=50)
    tags: list[str] = DbField(default_factory=list)
    attributes: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    note_date: date | None = DbField(default=None)
    attachment_ids: list[str] = DbField(default_factory=list)
    source_entity_id: str | None = DbField(default=None, max_length=100)
    source_company_id: str | None = DbField(default=None, max_length=100)
    relevance: float = DbField(
        default=1.0,
        description="Значение в БД; на ранжирование результатов поиска не влияет.",
    )
    _access_level: str = PrivateAttr(default="owner")

    @property
    def access_level(self) -> str:
        return self._access_level

    @access_level.setter
    def access_level(self, value: str) -> None:
        self._access_level = value

    @property
    def is_note(self) -> bool:
        return self.entity_type == "note"

    @computed_field
    @property
    def full_type(self) -> str:
        if self.entity_subtype is not None and self.entity_subtype != "":
            return f"{self.entity_type}:{self.entity_subtype}"
        return self.entity_type

    @classmethod
    async def distinct_note_company_ids_since(cls, since_date: date) -> list[str]:
        rows = await execute_raw(
            "SELECT DISTINCT company_id FROM crm_entities WHERE entity_type = 'note' AND note_date IS NOT NULL AND note_date >= $1 ORDER BY company_id",
            [since_date],
            using="crm",
        )
        company_ids: list[str] = []
        for row in rows:
            parsed = require_json_object(row, "company_id")
            company_id = parsed.get("company_id")
            if not isinstance(company_id, str) or company_id == "":
                raise ValueError("company_id is required")
            company_ids.append(company_id)
        return company_ids

    @classmethod
    async def distinct_note_scopes_since(
        cls,
        since_date: date,
        company_id: str,
    ) -> list[tuple[str, str, date]]:
        rows = await execute_raw(
            "SELECT DISTINCT company_id, namespace, note_date FROM crm_entities WHERE entity_type = 'note' AND note_date IS NOT NULL AND note_date >= $1 AND company_id = $2",
            [since_date, company_id],
            using="crm",
        )
        scopes: list[tuple[str, str, date]] = []
        for row in rows:
            parsed = require_json_object(row, "note_date")
            row_company_id = parsed.get("company_id")
            namespace = parsed.get("namespace")
            note_date = _note_date_value(parsed.get("note_date"))
            if not isinstance(row_company_id, str) or row_company_id == "":
                raise ValueError("company_id is required")
            if not isinstance(namespace, str) or namespace == "":
                raise ValueError("namespace is required")
            scopes.append((row_company_id, namespace, note_date))
        return scopes

    @classmethod
    async def all_ordered_by_created_at(cls) -> list[Self]:
        return await cls.objects.order_by("created_at").all()

    @classmethod
    async def find_in_company(
        cls,
        company_id: str,
        entity_id: str,
    ) -> Self | None:
        if company_id == "":
            raise ValueError("company_id cannot be empty.")
        if entity_id == "":
            raise ValueError("entity_id cannot be empty.")
        return await cls.objects.filter(
            entity_id=entity_id,
            company_id=company_id,
        ).get_or_none()

    @classmethod
    async def create(cls, entity: Self) -> Self:
        created = await cls.objects.create(instance=entity)
        logger.info("crm.entity.created", entity_id=created.entity_id, entity_type=created.full_type)
        return created

    @classmethod
    async def save_loaded(cls, entity: Self) -> Self:
        saved = await entity.save(using="crm")
        logger.info("crm.entity.updated", entity_id=saved.entity_id, entity_type=saved.full_type)
        return saved

    @classmethod
    async def take_by_id(cls, entity_id: str) -> Self | None:
        row = await cls.get(entity_id)
        if row is None:
            return None
        deleted = await cls.objects.filter(entity_id=entity_id).delete()
        if deleted == 0:
            return None
        logger.info("crm.entity.deleted", entity_id=entity_id)
        return row

    @classmethod
    async def update_attributes(
        cls,
        entity_id: str,
        attributes: JsonObject,
    ) -> CRMEntity:
        company_id = require_active_company().company_id
        rows = await cls.objects.filter(
            entity_id=entity_id,
            company_id=company_id,
        ).update(returning=True, using="crm", attributes=attributes, updated_at=datetime.now(UTC))
        if len(rows) != 1:
            raise ValueError(f"Entity not found: {entity_id}")
        row = rows[0]
        logger.info(
            "crm.entity.attributes_updated",
            entity_id=row.entity_id,
            entity_type=row.full_type,
        )
        return row

    @classmethod
    async def update_description_if_current(
        cls,
        entity_id: str,
        *,
        expected_description: str,
        description: str,
    ) -> CRMEntity | None:
        company_id = require_active_company().company_id
        rows = await cls.objects.filter(
            entity_id=entity_id,
            company_id=company_id,
            description=expected_description,
        ).update(
            returning=True,
            using="crm",
            description=description,
            updated_at=datetime.now(UTC),
        )
        if len(rows) != 1:
            return None
        row = rows[0]
        logger.info(
            "crm.entity.description_updated",
            entity_id=row.entity_id,
            entity_type=row.full_type,
        )
        return row

    @classmethod
    async def all_by_entity_type_and_attribute(
        cls,
        entity_type: str,
        attribute_key: str,
        attribute_value: str,
        company_id: str | None = None,
    ) -> list[CRMEntity]:
        table = cls.get_table_name()
        fetched = await execute_raw(
            f"SELECT row_to_json({table}) AS item FROM {table} WHERE company_id = $1 AND entity_type = $2 AND jsonb_extract_path_text(attributes, $3) = $4",
            [resolve_crm_company_id(company_id), entity_type, attribute_key, attribute_value],
            using="crm",
        )
        return [crm_entity_from_row(row) for row in fetched]

    @classmethod
    async def all_by_namespace_entity_type_and_external_ref(
        cls,
        *,
        company_id: str,
        namespace: str,
        entity_type: str,
        source_id: str,
        record_id: str,
    ) -> list[CRMEntity]:
        table = cls.get_table_name()
        rid = record_id.strip()
        sid = source_id.strip()
        if rid == "" or sid == "":
            return []
        fetched = await execute_raw(
            f"SELECT row_to_json({table}) AS item FROM {table} WHERE company_id = $1 AND namespace = $2 AND entity_type = $3 AND jsonb_extract_path_text(attributes, 'external_refs', $4, 'record_id') = $5",
            [company_id, namespace, entity_type, sid, rid],
            using="crm",
        )
        return [crm_entity_from_row(row) for row in fetched]

    @classmethod
    async def list_by_name(
        cls,
        company_id: str,
        query: str,
        *,
        limit: int,
    ) -> list[Self]:
        rows = cls.objects.filter(company_id=company_id)
        if query != "":
            rows = rows.filter(name__icontains=query)
        return await rows.order_by("name").limit(limit).all()


    @classmethod
    async def list_by_ids_in_order(
        cls,
        entity_ids: list[str],
        *,
        company_id: str | None = None,
    ) -> list[Self]:
        normalized = [entity_id.strip() for entity_id in entity_ids if entity_id.strip() != ""]
        if len(normalized) == 0:
            return []
        rows = await cls.objects.filter(
            company_id=resolve_crm_company_id(company_id),
            entity_id__in=normalized,
        ).all()
        by_id = {row.entity_id: row for row in rows}
        return [by_id[entity_id] for entity_id in normalized if entity_id in by_id]

    @classmethod
    async def list_by_ids(
        cls,
        entity_ids: list[str],
    ) -> list[Self]:
        normalized = [entity_id.strip() for entity_id in entity_ids if entity_id.strip() != ""]
        if len(normalized) == 0:
            return []
        return await cls.objects.filter(entity_id__in=normalized).all()

    @classmethod
    async def rewrite_source_entity_id(
        cls,
        company_id: str,
        old_entity_id: str,
        new_entity_id: str,
    ) -> int:
        if old_entity_id == new_entity_id:
            raise ValueError("old_entity_id and new_entity_id must differ")
        updated = await cls.objects.filter(
            company_id=company_id,
            source_entity_id=old_entity_id,
        ).update(using="crm", source_entity_id=new_entity_id)
        return updated

    @classmethod
    async def cursor_page(
        cls,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: JsonObject | None = None,
        filter_field_types: dict[str, str] | None = None,
        limit: int = 100,
        company_id: str | None = None,
        cursor: str | None = None,
    ) -> CursorPage[CRMEntity]:
        sql = EntityFilterSql()
        where = entity_filter_where(
            sql,
            company_id=resolve_crm_company_id(company_id),
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters,
            filter_field_types=filter_field_types,
        )
        if cursor is not None:
            cursor_ts, cursor_id = decode_entity_cursor(cursor)
            ts_param = sql.add(cursor_ts)
            id_param = sql.add(cursor_id)
            where.append(
                f"(created_at, entity_id) < ({ts_param}::timestamptz, {id_param})"
            )
        limit_param = sql.add(limit + 1)
        fetched = await execute_raw(
            "SELECT row_to_json(crm_entities) AS item FROM crm_entities WHERE "
            + " AND ".join(where)
            + f" ORDER BY created_at DESC, entity_id DESC LIMIT {limit_param}",
            sql.params,
            using="crm",
        )
        parsed = [crm_entity_from_row(row) for row in fetched]
        has_more = len(parsed) > limit
        page = parsed[:limit]
        next_cursor = None
        if has_more and len(page) > 0:
            last = page[-1]
            next_cursor = encode_entity_cursor(last.created_at, last.entity_id)
        return CursorPage[CRMEntity](items=page, next_cursor=next_cursor, has_more=has_more)

    @classmethod
    async def count_for_filter(
        cls,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: JsonObject | None = None,
        filter_field_types: dict[str, str] | None = None,
        company_id: str | None = None,
    ) -> int:
        sql = EntityFilterSql()
        where = entity_filter_where(
            sql,
            company_id=resolve_crm_company_id(company_id),
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters,
            filter_field_types=filter_field_types,
        )
        fetched = await execute_raw(
            "SELECT COUNT(entity_id) AS total FROM crm_entities WHERE " + " AND ".join(where),
            sql.params,
            using="crm",
        )
        return _int_cell(fetched, "total", "Entity count query returned empty value")

    @classmethod
    async def count_notes_with_analysis_draft_not_applied(
        cls,
        namespace: str,
        *,
        company_id: str | None = None,
    ) -> int:
        table = cls.get_table_name()
        sql = EntityFilterSql()
        company = sql.add(resolve_crm_company_id(company_id))
        ns = sql.add(namespace)
        fetched = await execute_raw(
            f"SELECT COUNT(entity_id) AS total FROM {table} WHERE company_id = {company} AND namespace = {ns} AND entity_type = 'note' AND (attributes -> 'ai_analysis_draft') IS NOT NULL AND (attributes -> 'ai_analysis_applied_at') IS NULL",
            sql.params,
            using="crm",
        )
        return _int_cell(fetched, "total", "Notes draft analysis count returned empty value")

    @classmethod
    async def list_notes_with_analysis_draft_not_applied(
        cls,
        namespace: str,
        *,
        limit: int,
        company_id: str | None = None,
    ) -> list[CRMEntity]:
        table = cls.get_table_name()
        sql = EntityFilterSql()
        company = sql.add(resolve_crm_company_id(company_id))
        ns = sql.add(namespace)
        limit_param = sql.add(limit)
        fetched = await execute_raw(
            f"SELECT row_to_json({table}) AS item FROM {table} WHERE company_id = {company} AND namespace = {ns} AND entity_type = 'note' AND (attributes -> 'ai_analysis_draft') IS NOT NULL AND (attributes -> 'ai_analysis_applied_at') IS NULL ORDER BY updated_at DESC, entity_id DESC LIMIT {limit_param}",
            sql.params,
            using="crm",
        )
        return [crm_entity_from_row(row) for row in fetched]

    @classmethod
    async def created_at_bounds(
        cls,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        company_id: str | None = None,
    ) -> tuple[datetime | None, datetime | None, int]:
        sql = EntityFilterSql()
        where = entity_filter_where(
            sql,
            company_id=resolve_crm_company_id(company_id),
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=None,
            filter_field_types=None,
        )
        fetched = await execute_raw(
            "SELECT MIN(created_at) AS min_created_at, MAX(created_at) AS max_created_at, COUNT(entity_id) AS total FROM "
            + cls.get_table_name()
            + " WHERE "
            + " AND ".join(where),
            sql.params,
            using="crm",
        )
        if len(fetched) != 1:
            raise ValueError("created_at bounds query returned empty value")
        row = require_json_object(fetched[0], "created_at bounds")
        min_created_at = _optional_datetime(row.get("min_created_at"), "min(created_at)")
        max_created_at = _optional_datetime(row.get("max_created_at"), "max(created_at)")
        total = row.get("total")
        if isinstance(total, bool) or not isinstance(total, int):
            raise ValueError("count(entity_id) returned invalid value")
        return min_created_at, max_created_at, total


    @classmethod
    async def count_for_namespace(
        cls,
        namespace: str,
        company_id: str | None = None,
        exclude_entity_types: AbstractSet[str] | None = None,
    ) -> int:
        if namespace == "":
            raise ValueError("Namespace is required")
        rows = cls.objects.filter(company_id=resolve_crm_company_id(company_id), namespace=namespace)
        if exclude_entity_types is not None and len(exclude_entity_types) > 0:
            rows = rows.exclude(entity_type__in=list(exclude_entity_types))
        return await rows.count()


    @classmethod
    async def used_entity_types_for_namespace(
        cls,
        namespace: str,
        company_id: str | None = None,
        exclude_entity_types: AbstractSet[str] | None = None,
    ) -> list[str]:
        if namespace == "":
            raise ValueError("Namespace is required")
        sql = EntityFilterSql()
        company = sql.add(resolve_crm_company_id(company_id))
        ns = sql.add(namespace)
        clause = f"company_id = {company} AND namespace = {ns}"
        if exclude_entity_types is not None and len(exclude_entity_types) > 0:
            placeholders = ", ".join(sql.add(item) for item in sorted(exclude_entity_types))
            clause = f"{clause} AND entity_type NOT IN ({placeholders})"
        table = cls.get_table_name()
        fetched = await execute_raw(
            f"SELECT DISTINCT entity_type FROM {table} WHERE {clause}",
            sql.params,
            using="crm",
        )
        type_ids: list[str] = []
        for row in fetched:
            parsed = require_json_object(row, "entity_type")
            raw = parsed.get("entity_type")
            if not isinstance(raw, str) or raw.strip() == "":
                continue
            type_ids.append(raw)
        return sorted(type_ids)

    @classmethod
    async def fts_ranked(
        cls,
        query: str,
        entity_type: str | None = None,
        entity_subtype: str | None = None,
        namespace: str | None = None,
        filters: JsonObject | None = None,
        filter_field_types: dict[str, str] | None = None,
        limit: int = 30,
        company_id: str | None = None,
    ) -> list[tuple[CRMEntity, float]]:
        sql = EntityFilterSql()
        where = entity_filter_where(
            sql,
            company_id=resolve_crm_company_id(company_id),
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters,
            filter_field_types=filter_field_types,
        )
        ts_param = sql.add(query)
        where.append(f"search_vector @@ plainto_tsquery('simple', {ts_param})")
        limit_param = sql.add(limit)
        fetched = await execute_raw(
            (
                f"SELECT row_to_json(crm_entities) AS item, ts_rank(search_vector, plainto_tsquery('simple', {ts_param}))::float8 AS fts_rank FROM crm_entities WHERE "
                + " AND ".join(where)
                + f" ORDER BY fts_rank DESC LIMIT {limit_param}"
            ),
            sql.params,
            using="crm",
        )
        ranked: list[tuple[CRMEntity, float]] = []
        for row in fetched:
            parsed = require_json_object(row, "fts row")
            ranked.append((crm_entity_from_row(row), _rank_to_float(parsed.get("fts_rank"))))
        return ranked

    @classmethod
    async def facet_counts(
        cls,
        namespace: str | None = None,
        company_id: str | None = None,
    ) -> JsonObject:
        table = cls.get_table_name()
        sql = EntityFilterSql()
        company = sql.add(resolve_crm_company_id(company_id))
        clause = f"company_id = {company}"
        if namespace is not None and namespace != "":
            ns = sql.add(namespace)
            clause = f"{clause} AND namespace = {ns}"
        by_type = await execute_raw(
            f"SELECT entity_type, COUNT(*) AS cnt FROM {table} WHERE {clause} GROUP BY entity_type",
            sql.params,
            using="crm",
        )
        by_status = await execute_raw(
            f"SELECT status, COUNT(*) AS cnt FROM {table} WHERE {clause} GROUP BY status",
            sql.params,
            using="crm",
        )
        by_month = await execute_raw(
            f"SELECT to_char(created_at, 'YYYY-MM') AS month, COUNT(*) AS cnt FROM {table} WHERE {clause} GROUP BY month ORDER BY month",
            sql.params,
            using="crm",
        )
        return {
            "by_type": _facet_map(by_type, "entity_type"),
            "by_status": _facet_map(by_status, "status"),
            "by_month": _facet_map(by_month, "month"),
        }


    @classmethod
    async def matching_by_ids(
        cls,
        *,
        company_id: str,
        entity_ids: list[str],
        entity_type: str | None,
        entity_subtype: str | None,
        namespace: str | None,
        filters: JsonObject | None,
        filter_field_types: dict[str, str] | None,
    ) -> Sequence[CRMEntity]:
        if len(entity_ids) == 0:
            return []
        if filters is None:
            rows = cls.objects.filter(company_id=company_id, entity_id__in=entity_ids)
            if entity_type is not None and entity_type != "":
                rows = rows.filter(entity_type=entity_type)
            if entity_subtype is not None and entity_subtype != "":
                rows = rows.filter(entity_subtype=entity_subtype)
            if namespace is not None and namespace != "":
                rows = rows.filter(namespace=namespace)
            return await rows.all()
        sql = EntityFilterSql()
        where = entity_filter_where(
            sql,
            company_id=company_id,
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters,
            filter_field_types=filter_field_types,
        )
        placeholders = ", ".join(sql.add(entity_id) for entity_id in entity_ids)
        where.append(f"entity_id IN ({placeholders})")
        fetched = await execute_raw(
            "SELECT row_to_json(crm_entities) AS item FROM crm_entities WHERE " + " AND ".join(where),
            sql.params,
            using="crm",
        )
        return [crm_entity_from_row(row) for row in fetched]




def entity_namespace(entity: CRMEntity) -> str:
    ns = entity.namespace.strip()
    if ns == "":
        raise ValueError(
            f"CRMEntity.namespace is empty for entity_id={entity.entity_id!r} company_id={entity.company_id!r}"
        )
    return ns


def resolve_crm_company_id(company_id: str | None) -> str:
    if company_id is None or company_id == "":
        return require_active_company().company_id
    return company_id


def _index_text(entity: CRMEntity) -> str:
    parts = [entity.name]
    if entity.description is not None and entity.description != "":
        parts.append(entity.description)
    for key, value in entity.attributes.items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        if key in _SKIP_SEARCH_ATTRIBUTE_KEYS:
            continue
        if key == "attachment_summaries" and isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                item_object = require_json_object(item, "attachment_summaries")
                raw_filename = item_object.get("filename", "")
                raw_summary = item_object.get("summary", "")
                filename = raw_filename if isinstance(raw_filename, str) else ""
                summary = raw_summary if isinstance(raw_summary, str) else ""
                if summary != "":
                    label = f"Вложение {filename}: " if filename != "" else ""
                    parts.append(f"{label}{summary}")
            continue
        parts.append(f"{key}: {value}")
    if len(entity.tags) > 0:
        parts.append(f"Теги: {', '.join(entity.tags)}")
    if entity.entity_type == "note" and entity.entity_subtype is not None and entity.entity_subtype != "":
        parts.append(f"Тип: {entity.entity_subtype}")
    return "\n".join(parts)


def _rag_metadata(entity: CRMEntity) -> RAGMetadata:
    return {
        "document_id": entity.entity_id,
        "company_id": entity.company_id,
        "entity_type": entity.entity_type,
        "ttl_seconds": 0,
    }


async def index_crm_entity(rag: BaseRAGProvider, entity: CRMEntity, *, replace: bool) -> None:
    rag_namespace = entity_namespace(entity)
    if replace:
        _ = await rag.delete_document(rag_namespace, entity.entity_id)
    _ = await rag.upload_document_from_text(
        namespace_id=rag_namespace,
        text=_index_text(entity),
        document_name=entity.entity_id,
        metadata=_rag_metadata(entity),
    )


def crm_entity_from_row(row: object) -> CRMEntity:
    parsed = require_json_object(row, "crm entity")
    raw_item = parsed["item"] if "item" in parsed else parsed
    if isinstance(raw_item, str):
        payload = parse_json_object(raw_item, "crm entity")
    else:
        payload = require_json_object(raw_item, "crm entity")
    raw_attributes = payload.get("attributes")
    if isinstance(raw_attributes, str):
        payload["attributes"] = parse_json_object(raw_attributes, "crm entity.attributes")
    _ = payload.pop("search_vector", None)
    return CRMEntity.model_validate(payload)

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COLUMNS = frozenset(
    {
        "entity_type",
        "entity_subtype",
        "namespace",
        "status",
        "user_id",
        "name",
        "description",
        "note_date",
        "created_at",
        "tags",
    }
)
type _FilterScalar = str | int | float | bool | date | datetime | None
type _Param = str | int | float | bool | date | datetime | None


class EntityFilterSql:
    def __init__(self) -> None:
        self.params: list[_Param] = []

    def add(self, value: _Param) -> str:
        self.params.append(value)
        return f"${len(self.params)}"


def encode_entity_cursor(created_at: datetime, entity_id: str) -> str:
    payload = json.dumps({"ts": created_at.isoformat(), "id": entity_id})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_entity_cursor(cursor: str) -> tuple[datetime, str]:
    payload = parse_json_object(
        base64.urlsafe_b64decode(cursor.encode()).decode(),
        "entity cursor",
    )
    raw_ts = payload.get("ts")
    raw_id = payload.get("id")
    if not isinstance(raw_ts, str) or not isinstance(raw_id, str):
        raise ValueError("Cursor payload has invalid shape")
    ts = datetime.fromisoformat(raw_ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts, raw_id


def _ident(name: str) -> str:
    if _IDENT.fullmatch(name) is None:
        raise ValueError(f"Unsupported filter field: {name}")
    return name




def entity_filter_where(
    sql: EntityFilterSql,
    *,
    company_id: str,
    entity_type: str | None,
    entity_subtype: str | None,
    namespace: str | None,
    filters: JsonObject | None,
    filter_field_types: dict[str, str] | None,
) -> list[str]:
    where = [f"company_id = {sql.add(company_id)}"]
    if entity_type is not None and entity_type != "":
        where.append(f"entity_type = {sql.add(entity_type)}")
    if entity_subtype is not None and entity_subtype != "":
        where.append(f"entity_subtype = {sql.add(entity_subtype)}")
    if namespace is not None and namespace != "":
        where.append(f"namespace = {sql.add(namespace)}")
    if filters is not None:
        where.append(_filter_sql(sql, filters, filter_field_types))
    return where


def _filter_sql(
    sql: EntityFilterSql,
    node: JsonObject,
    field_types: dict[str, str] | None,
) -> str:
    if field_types is None or len(field_types) == 0:
        raise ValueError("field_types are required when filters are provided")
    if "$and" in node:
        parts = [_filter_sql(sql, item, field_types) for item in _filter_nodes(node["$and"], "$and")]
        return "(" + " AND ".join(parts) + ")"
    if "$or" in node:
        parts = [_filter_sql(sql, item, field_types) for item in _filter_nodes(node["$or"], "$or")]
        return "(" + " OR ".join(parts) + ")"
    field_name = _required_string(node, "field")
    operator = _required_string(node, "op")
    if "value" not in node:
        raise ValueError("Filter leaf requires value")
    if field_name not in field_types:
        raise ValueError(f"Unknown filter field: {field_name}")
    return _leaf_sql(sql, field_name, field_types[field_name], operator, node["value"])


def _leaf_sql(
    sql: EntityFilterSql,
    field_name: str,
    field_type: str,
    operator: str,
    value: JsonValue,
) -> str:
    column = _field_sql(sql, field_name, field_type)
    if operator == "$contains":
        if field_name == "tags" or field_type == "array":
            if not isinstance(value, str):
                raise ValueError("contains filter value must be string")
            param = sql.add(value)
            if field_name.startswith("attributes."):
                return f"{column} @> to_jsonb(ARRAY[{param}]::text[])"
            return f"{column}::text[] @> ARRAY[{param}]::text[]"
        if not isinstance(value, str):
            raise ValueError("contains filter value must be string")
        return f"{column} ILIKE {sql.add('%' + value + '%')}"
    if operator in {"$in", "$nin"}:
        values = require_json_array(value, operator)
        if len(values) == 0:
            raise ValueError(f"{operator} requires non-empty list value")
        placeholders = ", ".join(
            _typed_param(sql.add(_coerce_scalar(field_type, item)), field_type)
            for item in values
        )
        expression = f"{column} IN ({placeholders})"
        if operator == "$nin":
            return f"NOT ({expression})"
        return expression
    coerced = _coerce_scalar(field_type, value)
    param = _typed_param(sql.add(coerced), field_type)
    if operator == "$eq":
        return f"{column} = {param}"
    if operator == "$ne":
        return f"{column} <> {param}"
    if operator == "$gt":
        return f"{column} > {param}"
    if operator == "$gte":
        return f"{column} >= {param}"
    if operator == "$lt":
        return f"{column} < {param}"
    if operator == "$lte":
        return f"{column} <= {param}"
    raise ValueError(f"Unsupported filter operator: {operator}")


def _field_sql(sql: EntityFilterSql, field_name: str, field_type: str) -> str:
    if field_name.startswith("attributes."):
        attr_name = field_name.split(".", 1)[1]
        key = sql.add(attr_name)
        text_expr = f"jsonb_extract_path_text(attributes, {key})"
        if field_type == "integer":
            return f"({text_expr})::bigint"
        if field_type == "number":
            return f"({text_expr})::double precision"
        if field_type == "boolean":
            return f"({text_expr})::boolean"
        if field_type == "date":
            return f"({text_expr})::date"
        if field_type == "datetime":
            return f"({text_expr})::timestamptz"
        if field_type == "array":
            return f"jsonb_extract_path(attributes, {key})"
        return text_expr
    if field_name not in _COLUMNS:
        raise ValueError(f"Unsupported filter field: {field_name}")
    return _ident(field_name)


def _typed_param(param: str, field_type: str) -> str:
    if field_type == "date":
        return f"{param}::date"
    if field_type == "datetime":
        return f"{param}::timestamptz"
    return param


def _filter_nodes(value: JsonValue, operator: str) -> list[JsonObject]:
    items = require_json_array(value, operator)
    if len(items) == 0:
        raise ValueError(f"{operator} requires non-empty list")
    return [require_json_object(item, operator) for item in items]


def _required_string(node: JsonObject, key: str) -> str:
    raw_value = node.get(key)
    if not isinstance(raw_value, str) or raw_value.strip() == "":
        raise ValueError(f"Filter field {key!r} must be a non-empty string")
    return raw_value


def _coerce_scalar(field_type: str, value: object) -> _FilterScalar:
    if field_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            if isinstance(value, str) and value.strip() != "":
                return int(value)
            raise ValueError("Integer filter value must be int or numeric string")
        return value
    if field_type == "number":
        if isinstance(value, bool):
            raise ValueError("Number filter value must not be bool")
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str) and value.strip() != "":
            return float(value)
        raise ValueError("Number filter value must be number or numeric string")
    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        raise ValueError("Boolean filter value must be bool")
    if field_type == "date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        raise ValueError("Unsupported date filter value type")
    if field_type == "datetime":
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("Unsupported datetime filter value type")
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise ValueError("Scalar filter value must be string, number, boolean, or null")


def _int_cell(rows: Sequence[object], key: str, message: str) -> int:
    if len(rows) != 1:
        raise ValueError(message)
    parsed = require_json_object(rows[0], key)
    value = parsed.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(message)
    return value


def _optional_datetime(value: object, label: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    raise ValueError(f"{label} returned invalid value")



def _rank_to_float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("FTS rank returned invalid value")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError("FTS rank returned invalid value") from exc
    raise ValueError("FTS rank returned invalid value")


def _facet_map(rows: Sequence[object], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        parsed = require_json_object(row, key)
        label = parsed.get(key)
        count = parsed.get("cnt")
        if not isinstance(label, str):
            raise ValueError(f"{key} facet label must be string")
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError(f"{key} facet count must be int")
        result[label] = count
    return result
