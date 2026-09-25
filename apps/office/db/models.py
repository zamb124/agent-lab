"""Таблицы platform_office."""

import json
import uuid
from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index as OxydeIndex
from oxyde import atomic, execute_raw

from core.models.platform_model import CompanyScopedModel, PlatformModel
from core.types import JsonObject


class OfficeDocumentCatalog(PlatformModel):
    """Каталог документов. Глобальная таблица: публичная ссылка читается без компании запроса."""

    __database_alias__: ClassVar[str | None] = "office"
    __global_model__: ClassVar[bool] = True

    catalog_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100, db_index=True)
    title: str = DbField(max_length=500)
    owner_user_id: str = DbField(max_length=100)
    created_at: datetime = DbField()
    namespace: str = DbField(default="default", max_length=64)
    parent_catalog_id: str | None = DbField(default=None, max_length=64, db_index=True)
    rag_index_enabled: bool = DbField(default=False)
    rag_index_include_subcatalogs: bool = DbField(default=False)
    rag_index_search_options: JsonObject | None = DbField(default=None, db_type="JSONB")
    rag_index_updated_at: datetime | None = DbField(default=None)
    link_enabled: bool = DbField(default=False)
    link_token_hash: str | None = DbField(default=None, max_length=128, db_unique=True)
    link_permission: str = DbField(default="viewer", max_length=16)
    link_updated_at: datetime | None = DbField(default=None)

    class Meta:
        is_table: bool = True
        table_name: str = "office_document_catalogs"
        indexes: list[OxydeIndex] = [
            OxydeIndex(["company_id", "namespace"]),
            OxydeIndex(["company_id", "namespace", "parent_catalog_id"]),
        ]

    @classmethod
    async def list_by_created_at(cls, *, limit: int | None) -> list[Self]:
        query = cls.objects.order_by("created_at")
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be >= 1")
            query = query.limit(limit)
        return await query.all()

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
    async def catalog_for_company(
        cls,
        catalog_id: str,
        company_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            catalog_id=catalog_id,
            company_id=company_id,
        ).get_or_none()

    @classmethod
    async def child_catalogs(
        cls,
        company_id: str,
        namespace: str,
        parent_catalog_id: str,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            parent_catalog_id=parent_catalog_id,
        ).all()

    @classmethod
    async def child_catalogs_by_title(
        cls,
        company_id: str,
        namespace: str,
        parent_catalog_id: str,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            parent_catalog_id=parent_catalog_id,
        ).order_by("title").all()

    @classmethod
    async def count_child_catalogs(cls, parent_catalog_id: str) -> int:
        return await cls.objects.filter(
            parent_catalog_id=parent_catalog_id,
        ).count()

    @classmethod
    async def catalog_by_title(
        cls,
        company_id: str,
        namespace: str,
        title: str,
        parent_catalog_id: str | None,
    ) -> Self | None:
        """Старейший каталог с этим названием у родителя: название у родителя не уникально."""
        return await (
            cls.objects.filter(
                company_id=company_id,
                namespace=namespace,
                title=title,
                parent_catalog_id=parent_catalog_id,
            )
            .order_by("created_at")
            .first()
        )

    @classmethod
    async def ensure_child_catalog(
        cls,
        *,
        company_id: str,
        namespace: str,
        parent_catalog_id: str | None,
        title: str,
        owner_user_id: str,
    ) -> tuple[Self, bool]:
        """Каталог с названием у родителя; параллельные вызовы создают его один раз."""
        parent_key = "" if parent_catalog_id is None else parent_catalog_id
        async with atomic(using="office"):
            _ = await execute_raw(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                [f"office_catalog:{company_id}:{namespace}:{parent_key}:{title}"],
                using="office",
            )
            existing = await cls.catalog_by_title(company_id, namespace, title, parent_catalog_id)
            if existing is not None:
                return existing, False
            if owner_user_id.strip() == "":
                raise ValueError("owner_user_id is required")
            created = await cls.objects.create(
                instance=cls(
                    catalog_id=uuid.uuid4().hex,
                    company_id=company_id,
                    namespace=namespace,
                    parent_catalog_id=parent_catalog_id,
                    title=title,
                    owner_user_id=owner_user_id,
                    created_at=datetime.now(timezone.utc),
                )
            )
            return created, True

    @classmethod
    async def catalogs_in_namespace(
        cls,
        company_id: str,
        namespace: str,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
        ).order_by("created_at").all()

    @classmethod
    async def search_catalogs_by_title(
        cls,
        company_id: str,
        query: str,
        limit: int,
    ) -> list[Self]:
        rows = cls.objects.filter(company_id=company_id)
        if query != "":
            rows = rows.filter(title__icontains=query)
        return await rows.order_by("title").limit(limit).all()

    @classmethod
    async def catalog_by_enabled_link_token(cls, token_hash: str) -> Self | None:
        return await cls.objects.filter(
            link_token_hash=token_hash,
            link_enabled=True,
        ).get_or_none()

    @classmethod
    async def create_catalog(cls, catalog: Self) -> Self:
        return await cls.objects.create(instance=catalog)

    @classmethod
    async def set_catalog_title(cls, catalog: Self, title: str) -> Self:
        catalog.title = title
        _ = await catalog.save()
        return catalog

    @classmethod
    async def delete_catalog_in_namespace(
        cls,
        catalog_id: str,
        company_id: str,
        namespace: str,
    ) -> int:
        return await cls.objects.filter(
            catalog_id=catalog_id,
            company_id=company_id,
            namespace=namespace,
        ).delete(using="office")


class OfficeDocumentBinding(PlatformModel):
    """Привязка файла. Первичный ключ ``file_id``: одна привязка на файл."""

    __database_alias__: ClassVar[str | None] = "office"
    __global_model__: ClassVar[bool] = True

    file_id: str = DbField(db_pk=True, max_length=128)
    company_id: str = DbField(max_length=100, db_index=True)
    catalog_id: str = DbField(max_length=64, db_index=True)
    file_category: str = DbField(max_length=32)
    title: str = DbField(max_length=500)
    created_by_user_id: str = DbField(max_length=100)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    namespace: str = DbField(default="default", max_length=64)
    onlyoffice_document_type: str | None = DbField(default=None, max_length=16)
    deleted_at: datetime | None = DbField(default=None)
    deleted_by_user_id: str | None = DbField(default=None, max_length=100)
    link_enabled: bool = DbField(default=False)
    link_token_hash: str | None = DbField(default=None, max_length=128)
    link_permission: str = DbField(default="viewer", max_length=16)
    link_updated_at: datetime | None = DbField(default=None)

    class Meta:
        is_table: bool = True
        table_name: str = "office_document_bindings"
        indexes: list[OxydeIndex] = [
            OxydeIndex(["company_id", "namespace", "created_at"]),
            OxydeIndex(["company_id", "namespace", "deleted_at"]),
            OxydeIndex(
                ["company_id", "namespace", "file_id"],
                unique=True,
                where="deleted_at IS NULL",
            ),
            OxydeIndex(["link_token_hash"], unique=True, where="link_token_hash IS NOT NULL"),
        ]

    @classmethod
    async def list_by_created_at(cls, *, limit: int | None) -> list[Self]:
        query = cls.objects.order_by("created_at")
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be >= 1")
            query = query.limit(limit)
        return await query.all()

    @classmethod
    async def active_bindings_in_catalog(
        cls,
        *,
        company_id: str,
        namespace: str,
        catalog_id: str,
    ) -> list[Self]:
        return await (
            cls.objects.filter(
                company_id=company_id,
                namespace=namespace,
                catalog_id=catalog_id,
                deleted_at=None,
            )
            .order_by("-created_at")
            .all()
        )

    @classmethod
    async def active_bindings_in_catalogs(
        cls,
        *,
        company_id: str,
        namespace: str,
        catalog_ids: list[str],
    ) -> list[Self]:
        return await (
            cls.objects.filter(
                company_id=company_id,
                namespace=namespace,
                catalog_id__in=catalog_ids,
                deleted_at=None,
            )
            .order_by("-created_at")
            .all()
        )

    @classmethod
    async def binding_in_namespace(
        cls,
        file_id: str,
        company_id: str,
        namespace: str,
    ) -> Self | None:
        return await cls.objects.filter(
            file_id=file_id,
            company_id=company_id,
            namespace=namespace,
        ).get_or_none()

    @classmethod
    async def trashed_binding_in_namespace(
        cls,
        file_id: str,
        company_id: str,
        namespace: str,
    ) -> Self | None:
        return await cls.objects.filter(
            file_id=file_id,
            company_id=company_id,
            namespace=namespace,
            deleted_at__isnull=False,
        ).get_or_none()

    @classmethod
    async def deleted_bindings_in_namespace(
        cls,
        company_id: str,
        namespace: str,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            deleted_at__isnull=False,
        ).order_by("-deleted_at").all()

    @classmethod
    async def search_alive_bindings_in_namespace(
        cls,
        company_id: str,
        namespace: str,
        title_query: str,
        limit: int,
    ) -> list[Self]:
        return await cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            deleted_at=None,
            title__icontains=title_query,
        ).order_by("-updated_at").limit(limit).all()

    @classmethod
    async def binding_for_company(
        cls,
        file_id: str,
        company_id: str,
    ) -> Self | None:
        return await cls.objects.filter(
            file_id=file_id,
            company_id=company_id,
        ).get_or_none()

    @classmethod
    async def search_bindings_by_title(
        cls,
        company_id: str,
        query: str,
        limit: int,
    ) -> list[Self]:
        rows = cls.objects.filter(company_id=company_id, deleted_at=None)
        if query != "":
            rows = rows.filter(title__icontains=query)
        return await rows.order_by("title").limit(limit).all()

    @classmethod
    async def count_alive_bindings(cls, company_id: str) -> int:
        return await cls.objects.filter(
            company_id=company_id,
            deleted_at=None,
        ).count()

    @classmethod
    async def count_bindings_in_catalog(cls, catalog_id: str) -> int:
        return await cls.objects.filter(
            catalog_id=catalog_id,
            deleted_at=None,
        ).count()

    @classmethod
    async def binding_by_enabled_link_token(cls, token_hash: str) -> Self | None:
        return await cls.objects.filter(
            link_token_hash=token_hash,
            link_enabled=True,
            deleted_at=None,
        ).get_or_none()

    @classmethod
    async def create_binding(cls, binding: Self) -> Self:
        return await cls.objects.create(instance=binding)

    @classmethod
    async def rename_binding(cls, binding: Self, title: str) -> Self:
        binding.title = title
        binding.updated_at = datetime.now(timezone.utc)
        _ = await binding.save()
        return binding

    @classmethod
    async def mark_binding_deleted(cls, binding: Self, *, user_id: str, deleted_at: datetime) -> Self:
        binding.deleted_at = deleted_at
        binding.deleted_by_user_id = user_id
        binding.updated_at = deleted_at
        _ = await binding.save()
        return binding

    @classmethod
    async def restore_binding(cls, binding: Self) -> Self:
        binding.deleted_at = None
        binding.deleted_by_user_id = None
        binding.updated_at = datetime.now(timezone.utc)
        _ = await binding.save()
        return binding

    @classmethod
    async def move_binding(cls, binding: Self, catalog_id: str) -> Self:
        binding.catalog_id = catalog_id
        binding.updated_at = datetime.now(timezone.utc)
        _ = await binding.save()
        return binding

    @classmethod
    async def delete_binding_in_namespace(
        cls,
        file_id: str,
        company_id: str,
        namespace: str,
    ) -> int:
        return await cls.objects.filter(
            file_id=file_id,
            company_id=company_id,
            namespace=namespace,
        ).delete(using="office")


class OfficeDocumentRevision(PlatformModel):
    """Снимок версии документа. ``file_id`` — привязка, ``revision_file_id`` — файл снимка."""

    __database_alias__: ClassVar[str | None] = "office"
    __global_model__: ClassVar[bool] = True

    revision_id: str = DbField(db_pk=True, max_length=64)
    file_id: str = DbField(max_length=128, db_index=True)
    revision_file_id: str = DbField(max_length=128)
    revision_number: int = DbField()
    created_by_user_id: str = DbField(max_length=100)
    created_at: datetime = DbField()

    class Meta:
        is_table: bool = True
        table_name: str = "office_document_revisions"
        indexes: list[OxydeIndex] = [
            OxydeIndex(["file_id", "revision_number"]),
        ]

    @classmethod
    async def list_for_file(cls, file_id: str, *, limit: int) -> list[Self]:
        return await (
            cls.objects.filter(file_id=file_id)
            .order_by("-revision_number")
            .limit(limit)
            .all()
        )

    @classmethod
    async def append_document_revision(
        cls,
        *,
        file_id: str,
        revision_file_id: str,
        created_by_user_id: str,
    ) -> Self:
        async with atomic(using="office"):
            _ = await execute_raw(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                [file_id],
                using="office",
            )
            latest = await (
                cls.objects.filter(file_id=file_id)
                .order_by("-revision_number")
                .first()
            )
            revision_number = 1 if latest is None else latest.revision_number + 1
            return await cls.objects.create(
                instance=cls(
                    revision_id=uuid.uuid4().hex,
                    file_id=file_id,
                    revision_file_id=revision_file_id,
                    revision_number=revision_number,
                    created_by_user_id=created_by_user_id,
                    created_at=datetime.now(timezone.utc),
                )
            )


class OfficeDocumentEvent(CompanyScopedModel):
    """Журнал активности по документу. ``payload_json`` — JSON-текст строки."""

    __database_alias__: ClassVar[str | None] = "office"

    class Meta:
        is_table: bool = True
        table_name: str = "office_document_events"

    event_id: str = DbField(db_pk=True, max_length=64)
    file_id: str = DbField(max_length=128, db_index=True)
    event_type: str = DbField(max_length=64)
    user_id: str = DbField(max_length=100)
    payload_json: str = DbField(db_type="TEXT")
    created_at: datetime = DbField()

    @classmethod
    async def list_for_file(cls, file_id: str, *, limit: int) -> list[Self]:
        return await (
            cls.objects.filter(file_id=file_id)
            .order_by("-created_at")
            .limit(limit)
            .all()
        )

    @classmethod
    async def record_document_event(
        cls,
        *,
        file_id: str,
        company_id: str,
        event_type: str,
        user_id: str,
        payload: JsonObject,
    ) -> None:
        _ = await cls.objects.create(
            instance=cls(
                event_id=uuid.uuid4().hex,
                file_id=file_id,
                company_id=company_id,
                event_type=event_type,
                user_id=user_id,
                payload_json=json.dumps(payload, ensure_ascii=False),
                created_at=datetime.now(timezone.utc),
            )
        )
