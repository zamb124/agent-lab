"""
Репозиторий для relationships (граф связей).

Для сложных связей с метаданными.
Все связи ТОЛЬКО здесь (нет linked_entity_ids в CRMEntity)!
"""

import base64
import json as _json
from typing import Dict, List, Optional, Tuple

from sqlalchemy import delete, or_, select, tuple_, update
from sqlalchemy.exc import IntegrityError

from apps.crm.db.base import BaseCRMRepository
from apps.crm.db.models import Relationship
from core.db.utils import get_rowcount
from core.logging import get_logger

logger = get_logger(__name__)


class RelationshipRepository(BaseCRMRepository[Relationship]):
    """Репозиторий для relationships в PostgreSQL"""

    @property
    def model_class(self) -> type[Relationship]:
        return Relationship

    @property
    def id_field(self) -> str:
        return "relationship_id"

    async def get_by_entity(self, entity_id: str) -> List[Relationship]:
        """Получает все связи сущности (source и target)"""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                Relationship.company_id == company_id,
                or_(
                    Relationship.source_entity_id == entity_id,
                    Relationship.target_entity_id == entity_id,
                ),
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_by_entity_for_graph(
        self,
        entity_id: str,
        cross_company: bool = False,
        relationship_namespace: Optional[str] = None,
    ) -> List[Relationship]:
        """
        Получает relationships для graph traversal.

        Args:
            entity_id: ID entity
            cross_company: Если True - игнорирует company_id фильтр
                          (для cross-company графов через grants)
            relationship_namespace: Если задан непустой — оставляем только связи
                с `Relationship.namespace == relationship_namespace`.

        Returns:
            List relationships где entity_id участвует (source или target)
        """
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                or_(
                    Relationship.source_entity_id == entity_id,
                    Relationship.target_entity_id == entity_id,
                )
            )

            if not cross_company:
                company_id = self._get_company_id()
                stmt = stmt.where(Relationship.company_id == company_id)

            if relationship_namespace is not None and relationship_namespace.strip() != "":
                stmt = stmt.where(Relationship.namespace == relationship_namespace)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def find_exact(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        *,
        namespace: Optional[str] = None,
    ) -> Optional[Relationship]:
        """Находит связь по (company, source, target, type); при namespace задан — с тем же пространством."""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                Relationship.company_id == company_id,
                Relationship.source_entity_id == source_id,
                Relationship.target_entity_id == target_id,
                Relationship.relationship_type == rel_type,
            )
            if namespace is not None:
                stmt = stmt.where(Relationship.namespace == namespace)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def ensure_edge(self, row: Relationship) -> Relationship:
        """
        Вставляет связь или возвращает уже существующую с тем же ключом uq_relationships_unique_edge.
        Защита от гонок параллельных вставок и дубликатов резолва черновика.
        """
        existing = await self.find_exact(
            row.source_entity_id,
            row.target_entity_id,
            row.relationship_type,
            namespace=row.namespace,
        )
        if existing is not None:
            return existing
        try:
            return await self.create(row)
        except IntegrityError as exc:
            if "uq_relationships_unique_edge" not in str(exc):
                raise
            existing_after = await self.find_exact(
                row.source_entity_id,
                row.target_entity_id,
                row.relationship_type,
                namespace=row.namespace,
            )
            if existing_after is not None:
                return existing_after
            raise

    async def delete_outgoing_by_source_and_types(
        self,
        source_entity_id: str,
        relationship_types: List[str],
    ) -> int:
        """Удаляет исходящие связи от source с указанными типами."""
        if not relationship_types:
            return 0
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = delete(Relationship).where(
                Relationship.company_id == company_id,
                Relationship.source_entity_id == source_entity_id,
                Relationship.relationship_type.in_(relationship_types),
            )
            result = await session.execute(stmt)
            await session.commit()
            return get_rowcount(result)

    async def delete_by_entity(self, entity_id: str) -> int:
        """Удаляет все связи сущности"""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = delete(Relationship).where(
                Relationship.company_id == company_id,
                or_(
                    Relationship.source_entity_id == entity_id,
                    Relationship.target_entity_id == entity_id,
                ),
            )
            result = await session.execute(stmt)
            await session.commit()

            count = get_rowcount(result)
            logger.info(f"Deleted {count} relationships for entity:{entity_id}")
            return count

    async def get_outgoing(
        self, source_entity_id: str, relationship_type: Optional[str] = None
    ) -> List[Relationship]:
        """Получает исходящие связи от сущности"""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(
                Relationship.company_id == company_id,
                Relationship.source_entity_id == source_entity_id,
            )

            if relationship_type:
                stmt = stmt.where(Relationship.relationship_type == relationship_type)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_neighbors(
        self,
        entity_ids: List[str],
        relationship_types: Optional[List[str]] = None,
        cross_company: bool = False,
        relationship_namespace: Optional[str] = None,
    ) -> Dict[str, List[Relationship]]:
        """
        Batch получение соседей для списка entities.

        Args:
            entity_ids: Список ID entities
            relationship_types: Фильтр по типам связей (опционально)
            cross_company: Если True — без фильтра по company_id (для cross-company графов)
            relationship_namespace: Если задан непустой — оставляем только связи
                с `Relationship.namespace == relationship_namespace`. Без него
                возвращаются связи всех пространств — нужно для UI «связи сущности»,
                не привязанного к одному namespace.

        Returns:
            Dict где ключ - entity_id, значение - список relationships
        """
        if not entity_ids:
            return {}

        async with self._db.session() as session:
            stmt = select(Relationship).where(
                or_(
                    Relationship.source_entity_id.in_(entity_ids),
                    Relationship.target_entity_id.in_(entity_ids),
                )
            )

            if not cross_company:
                company_id = self._get_company_id()
                stmt = stmt.where(Relationship.company_id == company_id)

            if relationship_types:
                stmt = stmt.where(Relationship.relationship_type.in_(relationship_types))

            if relationship_namespace is not None and relationship_namespace.strip() != "":
                stmt = stmt.where(Relationship.namespace == relationship_namespace)

            result = await session.execute(stmt)
            relationships = list(result.scalars().all())

            neighbors_map: Dict[str, List[Relationship]] = {eid: [] for eid in entity_ids}
            for rel in relationships:
                if rel.source_entity_id in entity_ids:
                    neighbors_map[rel.source_entity_id].append(rel)
                if rel.target_entity_id in entity_ids:
                    neighbors_map[rel.target_entity_id].append(rel)

            logger.debug(
                f"Loaded neighbors for {len(entity_ids)} entities: {len(relationships)} relationships"
            )
            return neighbors_map

    async def get_all_for_graph(
        self,
        limit: int = 1000,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Relationship], Optional[str], bool]:
        """
        Relationships компании с cursor-пагинацией для безопасного обхода.

        Returns:
            (relationships, next_cursor, has_more)
        """
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(Relationship).where(Relationship.company_id == company_id)

            if cursor is not None:
                payload = _json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                stmt = stmt.where(
                    tuple_(Relationship.created_at, Relationship.relationship_id)
                    > tuple_(payload["ts"], payload["id"])
                )

            stmt = stmt.order_by(
                Relationship.created_at.asc(),
                Relationship.relationship_id.asc(),
            ).limit(limit + 1)

            result = await session.execute(stmt)
            rows = list(result.scalars().all())

        has_more = len(rows) > limit
        relationships = rows[:limit]

        next_cursor: Optional[str] = None
        if has_more and relationships:
            last = relationships[-1]
            payload = _json.dumps({"ts": last.created_at.isoformat(), "id": last.relationship_id})
            next_cursor = base64.urlsafe_b64encode(payload.encode()).decode()

        logger.debug(f"Loaded {len(relationships)} relationships for graph (limit={limit})")
        return relationships, next_cursor, has_more

    async def rewrite_entity_id(
        self,
        company_id: str,
        old_entity_id: str,
        new_entity_id: str,
    ) -> int:
        """
        Заменяет old_entity_id на new_entity_id в source и target.
        Возвращает суммарное число затронутых строк (две операции UPDATE).
        """
        if old_entity_id == new_entity_id:
            raise ValueError("old_entity_id и new_entity_id должны различаться")
        async with self._db.session() as session:
            res_src = await session.execute(
                update(Relationship)
                .where(
                    Relationship.company_id == company_id,
                    Relationship.source_entity_id == old_entity_id,
                )
                .values(source_entity_id=new_entity_id)
            )
            res_tgt = await session.execute(
                update(Relationship)
                .where(
                    Relationship.company_id == company_id,
                    Relationship.target_entity_id == old_entity_id,
                )
                .values(target_entity_id=new_entity_id)
            )
            await session.commit()
            n_src = get_rowcount(res_src)
            n_tgt = get_rowcount(res_tgt)
            logger.info(
                f"Rewrote entity_id {old_entity_id} -> {new_entity_id}: "
                f"source_rows={n_src} target_rows={n_tgt}"
            )
            return n_src + n_tgt

    async def delete_by_relationship_id(self, relationship_id: str) -> bool:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = delete(Relationship).where(
                Relationship.company_id == company_id,
                Relationship.relationship_id == relationship_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return get_rowcount(result) > 0

    async def deduplicate_relationships_for_entity(self, entity_id: str) -> None:
        """
        Удаляет петли source==target и дубликаты по ключу
        (namespace, source, target, relationship_type), оставляя запись с минимальным relationship_id.
        """
        self._get_company_id()
        rels = await self.get_by_entity(entity_id)
        loops = [r for r in rels if r.source_entity_id == r.target_entity_id]
        for r in loops:
            await self.delete_by_relationship_id(r.relationship_id)

        rels = await self.get_by_entity(entity_id)
        groups: Dict[tuple[str, str, str, str], List[Relationship]] = {}
        for r in rels:
            key = (
                r.namespace,
                r.source_entity_id,
                r.target_entity_id,
                r.relationship_type,
            )
            groups.setdefault(key, []).append(r)
        for group in groups.values():
            if len(group) <= 1:
                continue
            keeper = min(group, key=lambda x: x.relationship_id)
            for r in group:
                if r.relationship_id != keeper.relationship_id:
                    await self.delete_by_relationship_id(r.relationship_id)
