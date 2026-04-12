"""
Репозиторий для CRM entities в PostgreSQL.

Структурные данные -- в crm_entities (CRM DB).
Семантический поиск -- через JOIN с vector_documents (shared DB).
"""

import base64
import json
import logging
from datetime import date, datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Type

from sqlalchemy import delete, func, or_, select, update, text, tuple_

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import CRMEntity
from core.context import get_context
from core.rag import RAGRepository
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation

logger = logging.getLogger(__name__)


class EntityRepository(BaseCRMRepository[CRMEntity]):
    """
    Репозиторий для CRM entities.

    CRUD -- через crm_entities (PostgreSQL).
    Семантический поиск -- через JOIN с vector_documents (pgvector).
    """

    def __init__(self, db: CRMDatabase, rag_repository: RAGRepository):
        super().__init__(db=db)
        self._rag = rag_repository

    @property
    def model_class(self) -> Type[CRMEntity]:
        return CRMEntity

    @property
    def id_field(self) -> str:
        return "entity_id"

    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id

    _SKIP_SEARCH_ATTRIBUTE_KEYS: ClassVar[frozenset[str]] = frozenset({
        "ai_analysis_draft",  # большой JSON-блок, шум в векторном индексе
    })

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
                for item in value:
                    if isinstance(item, dict):
                        filename = item.get("filename", "")
                        summary = item.get("summary", "")
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

    @staticmethod
    def _parse_datetime_filter_value(value: Any) -> datetime:
        if isinstance(value, datetime):
            parsed_value = value
        elif isinstance(value, str):
            parsed_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("Unsupported datetime filter value type")
        if parsed_value.tzinfo is None:
            return parsed_value.replace(tzinfo=timezone.utc)
        return parsed_value

    async def find_by_attribute(
        self,
        entity_type: str,
        attribute_key: str,
        attribute_value: str,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
        """Поиск сущностей по типу и значению в attributes (jsonb)."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(CRMEntity).where(
                CRMEntity.company_id == cid,
                CRMEntity.entity_type == entity_type,
                CRMEntity.attributes[attribute_key].astext == attribute_value,
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # -- CRUD --

    async def create(self, entity: CRMEntity) -> CRMEntity:
        """Создает entity в crm_entities + индексирует search_text в vector_documents."""
        async with self._db.session() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)

        search_text = self._build_search_text(entity)
        rag_namespace = entity.namespace or "default"
        await self._rag.upload_text(
            namespace_id=rag_namespace,
            text=search_text,
            document_name=entity.entity_id,
            metadata={
                "document_id": entity.entity_id,
                "company_id": entity.company_id,
                "entity_type": entity.entity_type,
            },
        )

        logger.info(f"Created entity: {entity.entity_id}, type={entity.full_type}")
        return entity

    async def get(self, entity_id: str) -> Optional[CRMEntity]:
        """Получает entity по ID."""
        async with self._db.session() as session:
            stmt = select(CRMEntity).where(CRMEntity.entity_id == entity_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_by_entity_ids_ordered(
        self,
        entity_ids: List[str],
        *,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
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

    async def update(self, entity: CRMEntity) -> CRMEntity:
        """Обновляет entity в crm_entities + переиндексирует в vector_documents."""
        async with self._db.session() as session:
            merged = await session.merge(entity)
            await session.commit()
            await session.refresh(merged)

        rag_namespace = entity.namespace or "default"
        await self._rag.delete_document(rag_namespace, entity.entity_id)

        search_text = self._build_search_text(entity)
        await self._rag.upload_text(
            namespace_id=rag_namespace,
            text=search_text,
            document_name=entity.entity_id,
            metadata={
                "document_id": entity.entity_id,
                "company_id": entity.company_id,
                "entity_type": entity.entity_type,
            },
        )

        logger.info(f"Updated entity: {entity.entity_id}, type={entity.full_type}")
        return merged

    async def delete(self, entity_id: str) -> bool:
        """Удаляет entity из crm_entities + vector_documents."""
        async with self._db.session() as session:
            namespace_stmt = select(CRMEntity.namespace).where(CRMEntity.entity_id == entity_id)
            namespace_row = await session.execute(namespace_stmt)
            rag_namespace = namespace_row.scalar() or "default"

            stmt = delete(CRMEntity).where(CRMEntity.entity_id == entity_id)
            result = await session.execute(stmt)
            await session.commit()
            deleted = result.rowcount > 0

        if deleted:
            await self._rag.delete_document(rag_namespace, entity_id)
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
            return int(result.rowcount or 0)

    # -- List / Filter --

    @staticmethod
    def encode_cursor(created_at: datetime, entity_id: str) -> str:
        payload = json.dumps({"ts": created_at.isoformat(), "id": entity_id})
        return base64.urlsafe_b64encode(payload.encode()).decode()

    @staticmethod
    def decode_cursor(cursor: str) -> Tuple[datetime, str]:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        ts = datetime.fromisoformat(payload["ts"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts, payload["id"]

    async def list_by_cursor(
        self,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        company_id: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> Tuple[List[CRMEntity], Optional[str], bool]:
        """
        Entities c SQL-фильтрами и cursor-пагинацией.

        Returns:
            (entities, next_cursor, has_more)
        """
        cid = company_id or self._get_company_id()

        async with self._db.session() as session:
            stmt = select(CRMEntity).where(CRMEntity.company_id == cid)

            if entity_type:
                stmt = stmt.where(CRMEntity.entity_type == entity_type)
            if entity_subtype:
                stmt = stmt.where(CRMEntity.entity_subtype == entity_subtype)
            if namespace:
                stmt = stmt.where(CRMEntity.namespace == namespace)

            if filters:
                stmt = self._apply_filters(stmt, filters)

            if cursor:
                cursor_ts, cursor_id = self.decode_cursor(cursor)
                stmt = stmt.where(
                    tuple_(CRMEntity.created_at, CRMEntity.entity_id) < tuple_(cursor_ts, cursor_id)
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
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        company_id: Optional[str] = None,
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
                stmt = self._apply_filters(stmt, filters)

            result = await session.execute(stmt)
            value = result.scalar()
            if value is None:
                raise ValueError("Entity count query returned empty value")
            return int(value)

    async def count_notes_with_analysis_draft_not_applied(
        self,
        namespace: str,
        *,
        company_id: Optional[str] = None,
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

    async def get_created_at_bounds(
        self,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> Tuple[Optional[Any], Optional[Any], int]:
        """Возвращает min/max created_at и количество сущностей."""
        cid = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(
                    func.min(CRMEntity.created_at),
                    func.max(CRMEntity.created_at),
                    func.count(CRMEntity.entity_id),
                )
                .where(CRMEntity.company_id == cid)
            )
            if entity_type:
                stmt = stmt.where(CRMEntity.entity_type == entity_type)
            if entity_subtype:
                stmt = stmt.where(CRMEntity.entity_subtype == entity_subtype)
            if namespace:
                stmt = stmt.where(CRMEntity.namespace == namespace)
            result = await session.execute(stmt)
            min_created_at, max_created_at, total_entities = result.one()
            return min_created_at, max_created_at, int(total_entities or 0)

    def _apply_filters(self, stmt, filters: Dict[str, Any]):
        """Применяет фильтры к SQL-запросу."""
        for key, value in filters.items():
            if key == "search":
                tsquery = func.plainto_tsquery("simple", value)
                stmt = stmt.where(CRMEntity.search_vector.op("@@")(tsquery))
            elif key == "tags":
                if isinstance(value, dict) and "$contains" in value:
                    tag = value["$contains"]
                    stmt = stmt.where(CRMEntity.tags.contains([tag]))
            elif key == "status":
                stmt = stmt.where(CRMEntity.status == value)
            elif key == "priority":
                stmt = stmt.where(CRMEntity.priority == value)
            elif key in ("note_date", "due_date"):
                column = getattr(CRMEntity, key)
                if isinstance(value, dict):
                    for op, op_value in value.items():
                        d = date.fromisoformat(op_value) if isinstance(op_value, str) else op_value
                        if op == "$gte":
                            stmt = stmt.where(column >= d)
                        elif op == "$lte":
                            stmt = stmt.where(column <= d)
                        elif op == "$eq":
                            stmt = stmt.where(column == d)
                elif isinstance(value, str):
                    stmt = stmt.where(column == date.fromisoformat(value))
            elif key == "created_at":
                column = CRMEntity.created_at
                if isinstance(value, dict):
                    for op, op_value in value.items():
                        dt_value = self._parse_datetime_filter_value(op_value)
                        if op == "$gte":
                            stmt = stmt.where(column >= dt_value)
                        elif op == "$lte":
                            stmt = stmt.where(column <= dt_value)
                        elif op == "$eq":
                            stmt = stmt.where(column == dt_value)
                else:
                    dt_value = self._parse_datetime_filter_value(value)
                    stmt = stmt.where(column == dt_value)
            elif isinstance(value, dict):
                for op, op_value in value.items():
                    column = getattr(CRMEntity, key, None)
                    if column is not None:
                        if op == "$eq":
                            stmt = stmt.where(column == op_value)
                        elif op == "$ne":
                            stmt = stmt.where(column != op_value)
            else:
                column = getattr(CRMEntity, key, None)
                if column is not None:
                    stmt = stmt.where(column == value)
        return stmt

    async def count_by_namespace(
        self,
        namespace: str,
        company_id: Optional[str] = None,
        exclude_entity_types: Optional[set[str]] = None,
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
        company_id: Optional[str] = None,
    ) -> List[str]:
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
            result = await session.execute(stmt)
            type_ids = [item for item in result.scalars().all() if isinstance(item, str) and item.strip()]
            return sorted(type_ids)

    # -- Semantic Search --

    async def search_with_similarity(
        self,
        query: str,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        company_id: Optional[str] = None,
    ) -> List[Tuple[CRMEntity, float]]:
        """
        Семантический поиск entities с возвратом similarity (0.0-1.0)
        через RAG index + выборку сущностей из CRM БД.
        """
        cid = company_id or self._get_company_id()
        resolved_namespace = namespace or "default"
        actx = get_context()
        if actx is None or actx.user is None or str(actx.user.user_id).strip() == "":
            raise ValueError("Контекст пользователя обязателен для семантического поиска CRM.")
        async with traced_operation(
            "crm.semantic.search_entities",
            event_type="crm.search",
            operation_category="embedding",
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: cid,
                trace_attributes.ATTR_USER_ID: str(actx.user.user_id).strip(),
                trace_attributes.ATTR_CRM_QUERY_MODE: "semantic_vector",
                trace_attributes.ATTR_CRM_ENTITY_TYPE: entity_type or "",
                "platform.crm.search_limit": limit,
                "platform.crm.namespace": resolved_namespace,
            },
        ) as search_span:
            search_filters: Dict[str, Any] = {"company_id": cid}
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
            if not search_results:
                logger.info(f"search_with_similarity('{query[:50]}...') -> 0 entities")
                search_span.set_attribute("platform.crm.search_hits_raw", 0)
                return []

            resolved_order: List[str] = []
            score_by_resolved: Dict[str, float] = {}
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
                    stmt = self._apply_filters(stmt, filters)
                result = await session.execute(stmt)
                matched_entities = list(result.scalars().all())

            entities_by_id = {entity.entity_id: entity for entity in matched_entities}
            scored_entities: List[Tuple[CRMEntity, float]] = []
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
            logger.info(f"search_with_similarity('{query[:50]}...') -> {len(scored_entities)} entities")
            return scored_entities

    async def hybrid_search(
        self,
        query: str,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        company_id: Optional[str] = None,
    ) -> List[Tuple[CRMEntity, float, str]]:
        """
        Гибридный поиск: RRF (Reciprocal Rank Fusion) по tsvector FTS + pgvector semantic.
        Возвращает (entity, rrf_score, match_type).
        match_type: "text" | "semantic" | "hybrid" (найдено обоими).
        """
        k = 60
        rrf_max = 2.0 / (k + 1)  # теоретический максимум при ранге 1 в обоих списках

        fts_entities = await self.fts_search_ranked(
            query, entity_type, entity_subtype, namespace, filters, limit * 3, company_id,
        )
        semantic_entities = await self.search_with_similarity(
            query, entity_type, entity_subtype, namespace, filters, limit * 3, company_id,
        )

        fts_ranks: Dict[str, int] = {}
        fts_map: Dict[str, CRMEntity] = {}
        for rank, (entity, _) in enumerate(fts_entities, start=1):
            fts_ranks[entity.entity_id] = rank
            fts_map[entity.entity_id] = entity

        sem_ranks: Dict[str, int] = {}
        sem_map: Dict[str, CRMEntity] = {}
        for rank, (entity, _) in enumerate(semantic_entities, start=1):
            sem_ranks[entity.entity_id] = rank
            sem_map[entity.entity_id] = entity

        all_ids = set(fts_ranks.keys()) | set(sem_ranks.keys())
        scored: List[Tuple[str, float, str]] = []
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

        results: List[Tuple[CRMEntity, float, str]] = []
        for eid, rrf_score, match_type in scored[:limit]:
            entity = entity_pool[eid]
            normalized_score = min(1.0, rrf_score / rrf_max)
            results.append((entity, normalized_score, match_type))
        return results

    async def fts_search_ranked(
        self,
        query: str,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 30,
        company_id: Optional[str] = None,
    ) -> List[Tuple[CRMEntity, float]]:
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
                stmt = self._apply_filters(stmt, filters)

            result = await session.execute(stmt)
            rows = result.all()

        return [(row[0], float(row[1])) for row in rows]

    async def aggregate_facets(
        self,
        namespace: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Фасетная агрегация: по entity_type, status, месяц создания."""
        cid = company_id or self._get_company_id()
        month_expr = func.to_char(CRMEntity.created_at, "YYYY-MM").label("month")

        async with self._db.session() as session:
            base = select(CRMEntity).where(CRMEntity.company_id == cid)
            if namespace:
                base = base.where(CRMEntity.namespace == namespace)

            by_type_stmt = (
                select(CRMEntity.entity_type, func.count().label("cnt"))
                .where(CRMEntity.company_id == cid)
            )
            if namespace:
                by_type_stmt = by_type_stmt.where(CRMEntity.namespace == namespace)
            by_type_stmt = by_type_stmt.group_by(CRMEntity.entity_type)
            type_rows = (await session.execute(by_type_stmt)).all()

            by_status_stmt = (
                select(CRMEntity.status, func.count().label("cnt"))
                .where(CRMEntity.company_id == cid)
            )
            if namespace:
                by_status_stmt = by_status_stmt.where(CRMEntity.namespace == namespace)
            by_status_stmt = by_status_stmt.group_by(CRMEntity.status)
            status_rows = (await session.execute(by_status_stmt)).all()

            by_month_stmt = (
                select(month_expr, func.count().label("cnt"))
                .where(CRMEntity.company_id == cid)
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

