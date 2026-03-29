"""
Репозиторий для CRM entities в PostgreSQL.

Структурные данные -- в crm_entities (CRM DB).
Семантический поиск -- через JOIN с vector_documents (shared DB).
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Type

from sqlalchemy import delete, select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import CRMEntity
from core.context import get_context
from core.db.models import VectorDocument
from core.rag import RAGRepository

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

    def _build_search_text(self, entity: CRMEntity) -> str:
        """Формирует текст для семантического поиска."""
        parts = [entity.name]

        if entity.description:
            parts.append(entity.description)

        for key, value in (entity.attributes or {}).items():
            if value:
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

    # -- CRUD --

    async def create(self, entity: CRMEntity) -> CRMEntity:
        """Создает entity в crm_entities + индексирует search_text в vector_documents."""
        async with self._db.session() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)

        search_text = self._build_search_text(entity)
        await self._rag.upload_text(
            namespace_id="default",
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

    async def update(self, entity: CRMEntity) -> CRMEntity:
        """Обновляет entity в crm_entities + переиндексирует в vector_documents."""
        async with self._db.session() as session:
            merged = await session.merge(entity)
            await session.commit()
            await session.refresh(merged)

        await self._rag.delete_document("default", entity.entity_id)

        search_text = self._build_search_text(entity)
        await self._rag.upload_text(
            namespace_id="default",
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
            stmt = delete(CRMEntity).where(CRMEntity.entity_id == entity_id)
            result = await session.execute(stmt)
            await session.commit()
            deleted = result.rowcount > 0

        if deleted:
            await self._rag.delete_document("default", entity_id)
            logger.info(f"Deleted entity: {entity_id}")

        return deleted

    # -- List / Filter --

    async def list_all(
        self,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
        """Получает список entities c SQL-фильтрами."""
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

            stmt = stmt.order_by(CRMEntity.created_at.desc()).limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    def _apply_filters(self, stmt, filters: Dict[str, Any]):
        """Применяет фильтры к SQL-запросу."""
        for key, value in filters.items():
            if key == "tags":
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

    async def search(
        self,
        query: str,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
        """
        Семантический поиск entities через JOIN с vector_documents.

        1. Генерирует embedding для query
        2. JOIN crm_entities <-> vector_documents по entity_id == document_id
        3. Фильтрует по company_id, entity_type и т.д.
        4. Сортирует по cosine distance
        """
        cid = company_id or self._get_company_id()

        embedding_service = self._rag.provider._embedding_service
        query_embedding = await embedding_service.generate_embedding(query)

        async with self._db.session() as session:
            distance_expr = VectorDocument.embedding.cosine_distance(query_embedding)

            stmt = (
                select(CRMEntity)
                .join(VectorDocument, CRMEntity.entity_id == VectorDocument.document_id)
                .where(CRMEntity.company_id == cid)
                .where(VectorDocument.embedding.isnot(None))
                .order_by(distance_expr)
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
            entities = list(result.scalars().all())

        logger.info(f"search('{query[:50]}...') -> {len(entities)} entities")
        return entities

    # -- Convenience methods --

    async def get_notes(
        self,
        note_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict] = None,
        limit: int = 100,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
        """Получает заметки."""
        return await self.list_all(
            entity_type="note",
            entity_subtype=note_subtype,
            namespace=namespace,
            filters=filters,
            limit=limit,
            company_id=company_id,
        )

    async def search_notes(
        self,
        query: str,
        note_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 10,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
        """Семантический поиск по заметкам."""
        return await self.search(
            query=query,
            entity_type="note",
            entity_subtype=note_subtype,
            namespace=namespace,
            limit=limit,
            company_id=company_id,
        )

    async def get_tasks(
        self,
        namespace: Optional[str] = None,
        filters: Optional[Dict] = None,
        limit: int = 100,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
        """Получает задачи."""
        return await self.list_all(
            entity_type="task",
            namespace=namespace,
            filters=filters,
            limit=limit,
            company_id=company_id,
        )

    async def search_tasks(
        self,
        query: str,
        namespace: Optional[str] = None,
        limit: int = 10,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
        """Семантический поиск по задачам."""
        return await self.search(
            query=query,
            entity_type="task",
            namespace=namespace,
            limit=limit,
            company_id=company_id,
        )

    async def get_by_type(
        self,
        entity_type: str,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict] = None,
        limit: int = 100,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
        """Получает entities по типу."""
        return await self.list_all(
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters,
            limit=limit,
            company_id=company_id,
        )

    async def search_by_type(
        self,
        query: str,
        entity_type: str,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 10,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
        """Семантический поиск по типу."""
        return await self.search(
            query=query,
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            limit=limit,
            company_id=company_id,
        )

    async def get_by_tag(
        self,
        tag: str,
        entity_type: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 100,
        company_id: Optional[str] = None,
    ) -> List[CRMEntity]:
        """Получает entities по тегу."""
        filters = {"tags": {"$contains": tag}}
        return await self.list_all(
            entity_type=entity_type,
            namespace=namespace,
            filters=filters,
            limit=limit,
            company_id=company_id,
        )
