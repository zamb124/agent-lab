"""Дерево каталогов Документов. Живёт в platform_shared рядом с FileRecord."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index as OxydeIndex
from oxyde import atomic, execute_raw

from core.documents.names import title_key, validate_segment
from core.models.platform_model import PlatformModel
from core.types import JsonObject

_MAX_DEPTH = 32


def _ancestor_catalog_id(raw: JsonObject) -> str:
    value = raw.get("catalog_id")
    if isinstance(value, str) and value != "":
        return value
    raise RuntimeError("ancestor query returned a non-string catalog_id")


class DocumentCatalog(PlatformModel):
    """Каталог. Глобальная таблица: сверка прав идёт без компании запроса."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    catalog_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100, db_index=True)
    namespace: str = DbField(max_length=64)
    parent_catalog_id: str | None = DbField(default=None, max_length=64, db_index=True)
    title: str = DbField(max_length=255)
    title_key: str = DbField(max_length=255)
    managed: bool = DbField(default=False)
    source_object: str | None = DbField(default=None, max_length=255)
    company_visible: bool = DbField(default=False)
    owner_user_id: str = DbField(max_length=100)
    authz_synced_at: datetime | None = DbField(default=None)
    rag_index_enabled: bool = DbField(default=False)
    rag_index_include_subcatalogs: bool = DbField(default=False)
    rag_index_search_options: JsonObject | None = DbField(default=None, db_type="JSONB")
    rag_index_updated_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    class Meta:
        is_table: bool = True
        table_name: str = "document_catalogs"
        indexes: list[OxydeIndex] = [
            OxydeIndex(["company_id", "namespace", "parent_catalog_id"]),
            OxydeIndex(
                ["parent_catalog_id", "title_key"],
                unique=True,
                where="parent_catalog_id IS NOT NULL",
            ),
            OxydeIndex(
                ["company_id", "namespace", "title_key"],
                unique=True,
                where="parent_catalog_id IS NULL",
            ),
            OxydeIndex(
                ["company_id", "namespace", "source_object"],
                unique=True,
                where="source_object IS NOT NULL",
            ),
        ]

    @classmethod
    async def catalog_in_namespace(
        cls,
        catalog_id: str,
        company_id: str,
        namespace: str,
    ) -> Self | None:
        return await cls.objects.filter(
            catalog_id=catalog_id,
            company_id=company_id,
            namespace=namespace,
        ).get_or_none()

    @classmethod
    async def child_by_title_key(
        cls,
        *,
        company_id: str,
        namespace: str,
        parent_catalog_id: str | None,
        key: str,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            parent_catalog_id=parent_catalog_id,
            title_key=key,
        ).get_or_none()

    @classmethod
    async def by_source_object(
        cls,
        *,
        company_id: str,
        namespace: str,
        source_object: str,
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            source_object=source_object,
        ).get_or_none()

    @classmethod
    async def children_page(
        cls,
        *,
        company_id: str,
        namespace: str,
        parent_catalog_id: str | None,
    ) -> list[Self]:
        return await (
            cls.objects.filter(
                company_id=company_id,
                namespace=namespace,
                parent_catalog_id=parent_catalog_id,
            )
            .order_by("title_key")
            .all()
        )

    @classmethod
    async def list_by_title(cls, company_id: str, query: str, limit: int) -> list[Self]:
        """Каталоги компании по возрастанию title, не больше limit. Пустой query не фильтрует заголовок."""
        rows = cls.objects.filter(company_id=company_id)
        if query != "":
            rows = rows.filter(title__icontains=query)
        return await rows.order_by("title").limit(limit).all()

    @classmethod
    async def list_by_title_key_in_namespace(cls, company_id: str, namespace: str) -> list[Self]:
        """Каталоги компании в namespace, ORDER BY title_key. Предела нет."""
        return await (
            cls.objects.filter(company_id=company_id, namespace=namespace).order_by("title_key").all()
        )

    @classmethod
    async def count_children(cls, parent_catalog_id: str) -> int:
        return await cls.objects.filter(parent_catalog_id=parent_catalog_id).count()

    @classmethod
    async def list_pending_authz_by_created_at(cls, *, limit: int) -> list[Self]:
        """Каталоги с пустым authz_synced_at, ORDER BY created_at, не больше limit."""
        return await (
            cls.objects.filter(authz_synced_at__isnull=True).order_by("created_at").limit(limit).all()
        )

    @classmethod
    async def list_all_by_created_at(cls, *, limit: int | None) -> list[Self]:
        """Все каталоги, ORDER BY created_at. limit is None не ограничивает. limit < 1 — ValueError."""
        query = cls.objects.order_by("created_at")
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be >= 1")
            query = query.limit(limit)
        return await query.all()

    @classmethod
    async def mark_authz_synced(cls, catalog_id: str, synced_at: datetime) -> None:
        _ = await cls.objects.filter(catalog_id=catalog_id).update(authz_synced_at=synced_at)

    @classmethod
    async def ensure_child(
        cls,
        *,
        company_id: str,
        namespace: str,
        parent_catalog_id: str | None,
        title: str,
        owner_user_id: str,
        managed: bool = False,
        source_object: str | None = None,
        company_visible: bool = False,
    ) -> tuple[Self, bool]:
        segment = validate_segment(title)
        key = title_key(segment)
        existing = await cls.child_by_title_key(
            company_id=company_id,
            namespace=namespace,
            parent_catalog_id=parent_catalog_id,
            key=key,
        )
        if existing is not None:
            return existing, False
        if owner_user_id.strip() == "":
            raise ValueError("owner_user_id is required")
        catalog_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        async with atomic(using="shared"):
            if parent_catalog_id is None:
                inserted = await execute_raw(
                    """
                    INSERT INTO document_catalogs (
                        catalog_id, company_id, namespace, parent_catalog_id, title, title_key,
                        managed, source_object, company_visible, owner_user_id, authz_synced_at,
                        rag_index_enabled, rag_index_include_subcatalogs, rag_index_search_options,
                        rag_index_updated_at, created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, NULL, $4, $5, $6, $7, $8, $9, NULL,
                        FALSE, FALSE, NULL, NULL, $10, $10
                    )
                    ON CONFLICT (company_id, namespace, title_key) WHERE parent_catalog_id IS NULL
                    DO NOTHING
                    RETURNING catalog_id
                    """,
                    [
                        catalog_id,
                        company_id,
                        namespace,
                        segment,
                        key,
                        managed,
                        source_object,
                        company_visible,
                        owner_user_id,
                        now,
                    ],
                    using="shared",
                )
            else:
                inserted = await execute_raw(
                    """
                    INSERT INTO document_catalogs (
                        catalog_id, company_id, namespace, parent_catalog_id, title, title_key,
                        managed, source_object, company_visible, owner_user_id, authz_synced_at,
                        rag_index_enabled, rag_index_include_subcatalogs, rag_index_search_options,
                        rag_index_updated_at, created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NULL,
                        FALSE, FALSE, NULL, NULL, $11, $11
                    )
                    ON CONFLICT (parent_catalog_id, title_key) WHERE parent_catalog_id IS NOT NULL
                    DO NOTHING
                    RETURNING catalog_id
                    """,
                    [
                        catalog_id,
                        company_id,
                        namespace,
                        parent_catalog_id,
                        segment,
                        key,
                        managed,
                        source_object,
                        company_visible,
                        owner_user_id,
                        now,
                    ],
                    using="shared",
                )
            row = await cls.child_by_title_key(
                company_id=company_id,
                namespace=namespace,
                parent_catalog_id=parent_catalog_id,
                key=key,
            )
        if row is None:
            raise RuntimeError("catalog ensure did not return a row")
        return row, bool(inserted)

    @classmethod
    async def ancestors(cls, catalog_id: str) -> list[Self]:
        rows = await execute_raw(
            """
            WITH RECURSIVE chain AS (
                SELECT catalog_id, parent_catalog_id, 0 AS depth
                FROM document_catalogs WHERE catalog_id = $1
                UNION ALL
                SELECT parent.catalog_id, parent.parent_catalog_id, chain.depth + 1
                FROM document_catalogs AS parent
                JOIN chain ON parent.catalog_id = chain.parent_catalog_id
                WHERE chain.depth < $2
            )
            SELECT catalog_id FROM chain ORDER BY depth DESC
            """,
            [catalog_id, _MAX_DEPTH],
            using="shared",
        )
        ordered: list[Self] = []
        for raw in rows:
            catalog_key = _ancestor_catalog_id(raw)
            catalog = await cls.get(catalog_key)
            if catalog is None:
                raise RuntimeError(f"ancestor catalog missing: {catalog_key}")
            ordered.append(catalog)
        return ordered

    @classmethod
    async def delete_in_namespace(cls, catalog_id: str, company_id: str, namespace: str) -> int:
        return await cls.objects.filter(
            catalog_id=catalog_id,
            company_id=company_id,
            namespace=namespace,
        ).delete(using="shared")

    @classmethod
    async def set_title(cls, catalog: Self, title: str) -> Self:
        segment = validate_segment(title)
        catalog.title = segment
        catalog.title_key = title_key(segment)
        catalog.updated_at = datetime.now(timezone.utc)
        _ = await catalog.save()
        return catalog

    @classmethod
    async def set_parent(cls, catalog: Self, parent_catalog_id: str | None) -> Self:
        catalog.parent_catalog_id = parent_catalog_id
        catalog.updated_at = datetime.now(timezone.utc)
        _ = await catalog.save()
        return catalog
