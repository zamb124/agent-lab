"""Ребро графа CRM. Ответ API — эта же строка."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, Q, atomic, execute_raw
from oxyde.exceptions import UniqueViolationError
from oxyde.queries.select import Query

from core.context import require_active_company
from core.logging import get_logger
from core.models.platform_model import PlatformModel
from core.pagination import CursorPage
from core.types import JsonObject, parse_json_object, require_json_object

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Relationship(PlatformModel):
    """Строка ``relationships``, алиас ``crm``, ``__global_model__``."""

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "relationships"
        unique_together: list[tuple[str, str, str, str, str]] = [
            (
                "company_id",
                "namespace",
                "source_entity_id",
                "target_entity_id",
                "relationship_type",
            )
        ]
        indexes: list[Index] = [
            Index(["source_entity_id"]),
            Index(["target_entity_id"]),
            Index(["source_entity_id", "target_entity_id"]),
            Index(["company_id", "namespace"]),
        ]

    relationship_id: str = DbField(db_pk=True, max_length=100)
    company_id: str = DbField(max_length=100)
    source_entity_id: str = DbField(max_length=100)
    target_entity_id: str = DbField(max_length=100)
    relationship_type: str = DbField(max_length=100)
    created_at: datetime = DbField(default_factory=_utcnow)
    updated_at: datetime = DbField(default_factory=_utcnow)
    namespace: str = DbField(default="default", max_length=100)
    weight: float = DbField(
        default=1.0,
        description="Сила или стоимость связи; в кратчайшем пути по графу накапливается как расстояние.",
    )
    confidence: float = DbField(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Достоверность связи; на длину пути и на поиск сущностей не влияет.",
    )
    attributes: JsonObject = DbField(default_factory=dict, db_type="JSONB")

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def target_by_source_and_type(
        cls,
        company_id: str,
        source_entity_id: str,
        relationship_type: str,
    ) -> str | None:
        row = await cls.objects.filter(
            company_id=company_id,
            source_entity_id=source_entity_id,
            relationship_type=relationship_type,
        ).first()
        if row is None:
            return None
        return row.target_entity_id

    @classmethod
    async def delete_by_source_and_types(
        cls,
        company_id: str,
        source_entity_id: str,
        relationship_types: list[str],
    ) -> int:
        return await cls.objects.filter(
            company_id=company_id,
            source_entity_id=source_entity_id,
            relationship_type__in=relationship_types,
        ).delete()

    @classmethod
    async def delete_by_company_and_relationship_id(
        cls,
        company_id: str,
        relationship_id: str,
    ) -> int:
        return await cls.objects.filter(
            company_id=company_id,
            relationship_id=relationship_id,
        ).delete()

    @classmethod
    async def by_namespace_source_target_and_type(
        cls,
        *,
        company_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,
        namespace: str,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relationship_type=relationship_type,
            namespace=namespace,
        ).get_or_none()

    @classmethod
    def touching(cls, entity_id: str) -> Query[Self]:
        return cls.objects.filter(
            Q(source_entity_id=entity_id) | Q(target_entity_id=entity_id)
        )

    @classmethod
    def touching_in_company(
        cls, entity_id: str, company_id: str
    ) -> Query[Self]:
        return cls.touching(entity_id).filter(company_id=company_id)

    @classmethod
    def _exact_edge(cls, company_id: str, row: Self) -> Query[Self]:
        return cls.objects.filter(
            company_id=company_id,
            source_entity_id=row.source_entity_id,
            target_entity_id=row.target_entity_id,
            relationship_type=row.relationship_type,
            namespace=row.namespace,
        )

    @classmethod
    async def ensure_edge(cls, row: Self) -> Self:
        company_id = require_active_company().company_id
        existing = await cls._exact_edge(company_id, row).get_or_none()
        if existing is not None:
            return existing
        try:
            return await cls.objects.create(instance=row)
        except UniqueViolationError:
            raced = await cls._exact_edge(company_id, row).get_or_none()
            if raced is None:
                raise
            return raced

    @classmethod
    async def neighbors_for_entities(
        cls,
        entity_ids: list[str],
        relationship_types: list[str] | None = None,
        cross_company: bool = False,
        relationship_namespace: str | None = None,
    ) -> dict[str, list[Relationship]]:
        if len(entity_ids) == 0:
            return {}
        rows = cls.objects.filter(
            Q(source_entity_id__in=entity_ids) | Q(target_entity_id__in=entity_ids)
        )
        if not cross_company:
            rows = rows.filter(company_id=require_active_company().company_id)
        if relationship_types is not None and len(relationship_types) > 0:
            rows = rows.filter(relationship_type__in=relationship_types)
        if relationship_namespace is not None and relationship_namespace.strip() != "":
            rows = rows.filter(namespace=relationship_namespace)
        found = await rows.all()
        neighbors: dict[str, list[Relationship]] = {entity_id: [] for entity_id in entity_ids}
        wanted = set(entity_ids)
        for relationship in found:
            if relationship.source_entity_id in wanted:
                neighbors[relationship.source_entity_id].append(relationship)
            if relationship.target_entity_id in wanted:
                neighbors[relationship.target_entity_id].append(relationship)
        logger.debug(
            "crm.relationship.neighbors_loaded",
            entity_count=len(entity_ids),
            relationship_count=len(found),
        )
        return neighbors

    @classmethod
    async def graph_page(
        cls,
        *,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[Relationship]:
        table_name = cls.get_table_name()
        company_id = require_active_company().company_id
        clauses = ["company_id = $1"]
        params: list[str | datetime | int] = [company_id]
        if cursor is not None:
            payload = parse_json_object(
                base64.urlsafe_b64decode(cursor.encode()).decode(),
                "relationship graph cursor",
            )
            raw_ts = payload.get("ts")
            raw_id = payload.get("id")
            if not isinstance(raw_ts, str) or not isinstance(raw_id, str):
                raise ValueError("relationship graph cursor has invalid shape")
            cursor_ts = datetime.fromisoformat(raw_ts)
            if cursor_ts.tzinfo is None:
                cursor_ts = cursor_ts.replace(tzinfo=UTC)
            params.append(cursor_ts)
            ts_placeholder = f"${len(params)}"
            params.append(raw_id)
            id_placeholder = f"${len(params)}"
            clauses.append(
                f"(created_at, relationship_id) > ({ts_placeholder}, {id_placeholder})"
            )
        params.append(limit + 1)
        limit_placeholder = f"${len(params)}"
        fetched = await execute_raw(
            f"SELECT row_to_json({table_name}) AS item FROM {table_name} WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at, relationship_id LIMIT "
            + limit_placeholder,
            params,
            using="crm",
        )
        parsed = [_relationship_from_row(row) for row in fetched]
        has_more = len(parsed) > limit
        page = parsed[:limit]
        next_cursor: str | None = None
        if has_more and len(page) > 0:
            last = page[-1]
            encoded = json.dumps({"ts": last.created_at.isoformat(), "id": last.relationship_id})
            next_cursor = base64.urlsafe_b64encode(encoded.encode()).decode()
        logger.debug("crm.relationship.graph_loaded", count=len(page), limit=limit)
        return CursorPage[Relationship](items=page, next_cursor=next_cursor, has_more=has_more)

    @classmethod
    async def rewrite_entity_id(
        cls,
        company_id: str,
        old_entity_id: str,
        new_entity_id: str,
    ) -> int:
        if old_entity_id == new_entity_id:
            raise ValueError("old_entity_id and new_entity_id must differ")
        async with atomic(using="crm"):
            source_rows = await cls.objects.filter(
                company_id=company_id,
                source_entity_id=old_entity_id,
            ).update(using="crm", source_entity_id=new_entity_id)
            target_rows = await cls.objects.filter(
                company_id=company_id,
                target_entity_id=old_entity_id,
            ).update(using="crm", target_entity_id=new_entity_id)
        logger.info(
            "crm.rewrote.entity_id.source_rows.target_rows",
            old_entity_id=old_entity_id,
            new_entity_id=new_entity_id,
            source_rows=source_rows,
            target_rows=target_rows,
        )
        return source_rows + target_rows

    @classmethod
    async def deduplicate_for_entity(cls, entity_id: str) -> None:
        company_id = require_active_company().company_id
        rows = await cls.touching_in_company(entity_id, company_id).all()
        deleted_count = 0
        for relationship in rows:
            if relationship.source_entity_id != relationship.target_entity_id:
                continue
            deleted = await cls.objects.filter(
                company_id=company_id,
                relationship_id=relationship.relationship_id,
            ).delete()
            if deleted > 0:
                deleted_count += 1
        rows = await cls.touching_in_company(entity_id, company_id).all()
        groups: dict[tuple[str, str, str, str], list[Relationship]] = {}
        for relationship in rows:
            key = (
                relationship.namespace,
                relationship.source_entity_id,
                relationship.target_entity_id,
                relationship.relationship_type,
            )
            groups.setdefault(key, []).append(relationship)
        for group in groups.values():
            if len(group) <= 1:
                continue
            keeper = min(group, key=lambda item: item.relationship_id)
            for relationship in group:
                if relationship.relationship_id == keeper.relationship_id:
                    continue
                deleted = await cls.objects.filter(
                    company_id=company_id,
                    relationship_id=relationship.relationship_id,
                ).delete()
                if deleted > 0:
                    deleted_count += 1
        if deleted_count > 0:
            logger.info(
                "crm.deduplicated.relationships.entity",
                deleted_count=deleted_count,
                entity_id=entity_id,
            )


def _relationship_from_row(row: object) -> Relationship:
    parsed = require_json_object(row, "relationship")
    raw_item = parsed["item"]
    if isinstance(raw_item, str):
        payload = parse_json_object(raw_item, "relationship")
    else:
        payload = require_json_object(raw_item, "relationship")
    raw_attributes = payload.get("attributes")
    if isinstance(raw_attributes, str):
        payload["attributes"] = parse_json_object(raw_attributes, "relationship.attributes")
    return Relationship.model_validate(payload)
