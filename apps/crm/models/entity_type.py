"""Тип сущности CRM и поколение его каталога."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import ClassVar, Self, TypedDict

from oxyde import Field as DbField
from oxyde import Index, atomic, execute_raw
from oxyde.exceptions import UniqueViolationError
from oxyde.queries.select import Query
from pydantic import model_validator

from core.context import require_active_company
from core.models.platform_model import PlatformModel
from core.types import JsonObject

CATALOG_MAX_ROWS = 50_000


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _default_public_fields() -> list[str]:
    return ["name", "entity_type", "tags"]


class EntityTypeFieldUpdate(TypedDict, total=False):
    parent_type_id: str | None
    name: str
    description: str | None
    prompt: str | None
    required_fields: JsonObject
    optional_fields: JsonObject
    icon: str | None
    color: str | None
    is_system: bool
    is_event: bool
    check_duplicates: bool
    weight_coefficient: float
    public_fields: list[str]
    is_context_anchor: bool
    is_voice_target: bool
    extractable: bool
    auto_resolve_suggests: bool


class EntityType(PlatformModel):
    """Строка ``entity_types``.

    Ключ строки — ``entity_type_row_id`` из ``company_id``, ``namespace`` и ``type_id``.
    Один ``type_id`` живёт в каждом пространстве компании отдельно.
    """

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "entity_types"
        unique_together: list[tuple[str, str, str]] = [("company_id", "namespace", "type_id")]
        indexes: list[Index] = [
            Index(["parent_type_id"]),
            Index(["is_system"]),
            Index(["company_id", "namespace"]),
        ]

    entity_type_row_id: str = DbField(default="", db_pk=True, db_type="TEXT")
    company_id: str = DbField(max_length=100)
    namespace: str = DbField(max_length=100)
    type_id: str = DbField(max_length=100, db_index=True)
    name: str = DbField(max_length=200)
    created_at: datetime = DbField(default_factory=_utcnow)
    parent_type_id: str | None = DbField(default=None, max_length=100)
    description: str | None = DbField(default=None, db_type="TEXT")
    prompt: str | None = DbField(default=None, db_type="TEXT")
    required_fields: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    optional_fields: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    public_fields: list[str] = DbField(default_factory=_default_public_fields, db_type="JSONB")
    icon: str | None = DbField(default=None, max_length=50)
    color: str | None = DbField(default=None, max_length=20)
    is_system: bool = DbField(default=False)
    is_event: bool = DbField(default=False)
    check_duplicates: bool = DbField(default=True)
    weight_coefficient: float = DbField(default=1.0)
    is_context_anchor: bool = DbField(default=False)
    extractable: bool = DbField(default=True)
    is_voice_target: bool = DbField(default=False)
    auto_resolve_suggests: bool = DbField(default=False)

    @classmethod
    def row_id(cls, company_id: str, namespace: str, type_id: str) -> str:
        if company_id == "" or namespace == "" or type_id == "":
            raise ValueError("entity type row requires company_id, namespace and type_id")
        return f"{len(company_id)}:{company_id}:{len(namespace)}:{namespace}:{type_id}"

    @model_validator(mode="after")
    def bind_row_id(self) -> Self:
        expected = type(self).row_id(self.company_id, self.namespace, self.type_id)
        if self.entity_type_row_id == "":
            self.entity_type_row_id = expected
        elif self.entity_type_row_id != expected:
            raise ValueError("entity_type_row_id does not match company_id, namespace and type_id")
        return self

    @classmethod
    def in_company(
        cls,
        company_id: str,
        *,
        namespace: str | None = None,
        include_system: bool = True,
    ) -> Query[Self]:
        rows = cls.objects.filter(company_id=company_id)
        if namespace is not None:
            rows = rows.filter(namespace=namespace)
        if not include_system:
            return rows.filter(is_system=False)
        return rows

    @classmethod
    def by_company_namespace_and_type_id(
        cls,
        *,
        company_id: str,
        namespace: str,
        type_id: str,
    ) -> Query[Self]:
        return cls.objects.filter(
            company_id=company_id,
            namespace=namespace,
            type_id=type_id,
        )

    @classmethod
    async def catalog(
        cls,
        *,
        namespace: str | None = None,
        company_id: str | None = None,
    ) -> list[EntityType]:
        resolved_company_id = resolve_entity_type_company(company_id)
        revision_before = await EntityTypeCatalogRevision.catalog_revision(resolved_company_id)
        cached = get_entry(resolved_company_id, namespace)
        if cached is not None and cached[0] == revision_before:
            return list(cached[1])
        items = await (
            cls.in_company(resolved_company_id, namespace=namespace)
            .order_by("-is_system", "type_id")
            .limit(CATALOG_MAX_ROWS + 1)
            .all()
        )
        if len(items) > CATALOG_MAX_ROWS:
            raise RuntimeError(
                f"EntityType catalog for company {resolved_company_id!r} exceeds {CATALOG_MAX_ROWS} rows"
            )
        revision_after = await EntityTypeCatalogRevision.catalog_revision(resolved_company_id)
        if revision_before == revision_after:
            put_entry(
                resolved_company_id,
                namespace,
                revision_after,
                items,
            )
        return list(items)

    @classmethod
    async def create(cls, row: Self) -> Self:
        async with atomic(using="crm"):
            created = await cls.objects.create(instance=row)
            await EntityTypeCatalogRevision.bump_catalog_revision(row.company_id)
        invalidate_company(row.company_id)
        return created

    @classmethod
    async def update_fields(
        cls,
        type_id: str,
        *,
        namespace: str,
        company_id: str | None = None,
        patch: EntityTypeFieldUpdate,
    ) -> None:
        if len(patch) == 0:
            raise ValueError("entity type update requires fields")
        resolved_company_id = resolve_entity_type_company(company_id)
        async with atomic(using="crm"):
            updated = await cls.by_company_namespace_and_type_id(
                company_id=resolved_company_id,
                namespace=namespace,
                type_id=type_id,
            ).update(using="crm", **patch)
            if updated != 1:
                raise ValueError(
                    f"EntityType {type_id!r} not found for company {resolved_company_id!r} namespace {namespace!r}"
                )
            await EntityTypeCatalogRevision.bump_catalog_revision(resolved_company_id)
        invalidate_company(resolved_company_id)

    @classmethod
    async def merge_optional_fields(
        cls,
        type_id: str,
        *,
        namespace: str,
        company_id: str,
        extra: JsonObject,
    ) -> None:
        if len(extra) == 0:
            return
        async with atomic(using="crm"):
            entity_type = await cls.by_company_namespace_and_type_id(
                company_id=company_id,
                namespace=namespace,
                type_id=type_id,
            ).get_or_none()
            if entity_type is None:
                raise ValueError(
                    f"EntityType {type_id!r} not found for company {company_id!r} namespace {namespace!r}"
                )
            current = dict(entity_type.optional_fields)
            changed = False
            for key, value in extra.items():
                if key not in current:
                    current[key] = value
                    changed = True
            if not changed:
                return
            updated = await cls.by_company_namespace_and_type_id(
                company_id=company_id,
                namespace=namespace,
                type_id=type_id,
            ).update(using="crm", optional_fields=current)
            if updated != 1:
                raise ValueError(
                    f"EntityType {type_id!r} not found for company {company_id!r} namespace {namespace!r}"
                )
            await EntityTypeCatalogRevision.bump_catalog_revision(company_id)
        invalidate_company(company_id)

    @classmethod
    async def ensure_in_namespace(
        cls,
        type_id: str,
        *,
        source_namespace: str,
        target_namespace: str,
        company_id: str | None = None,
    ) -> Self:
        resolved_company_id = resolve_entity_type_company(company_id)
        source = await cls.by_company_namespace_and_type_id(
            company_id=resolved_company_id,
            namespace=source_namespace,
            type_id=type_id,
        ).get_or_none()
        if source is None:
            raise ValueError(f"EntityType {type_id!r} not found in namespace {source_namespace!r}")
        existing = await cls.by_company_namespace_and_type_id(
            company_id=resolved_company_id,
            namespace=target_namespace,
            type_id=type_id,
        ).get_or_none()
        if existing is not None:
            return existing
        clone = cls(
            company_id=resolved_company_id,
            namespace=target_namespace,
            type_id=source.type_id,
            parent_type_id=source.parent_type_id,
            name=source.name,
            description=source.description,
            prompt=source.prompt,
            required_fields=dict(source.required_fields),
            optional_fields=dict(source.optional_fields),
            icon=source.icon,
            color=source.color,
            is_system=source.is_system,
            is_event=source.is_event,
            check_duplicates=source.check_duplicates,
            weight_coefficient=source.weight_coefficient,
            public_fields=list(source.public_fields),
            is_context_anchor=source.is_context_anchor,
            extractable=source.extractable,
            is_voice_target=source.is_voice_target,
            auto_resolve_suggests=source.auto_resolve_suggests,
            created_at=datetime.now(UTC),
        )
        try:
            return await cls.create(clone)
        except UniqueViolationError:
            raced = await cls.by_company_namespace_and_type_id(
                company_id=resolved_company_id,
                namespace=target_namespace,
                type_id=type_id,
            ).get_or_none()
            if raced is None:
                raise
            return raced

    @classmethod
    async def delete_by_company_namespace_and_type_id(
        cls,
        type_id: str,
        *,
        namespace: str,
        company_id: str | None = None,
    ) -> bool:
        resolved_company_id = resolve_entity_type_company(company_id)
        async with atomic(using="crm"):
            deleted = await cls.by_company_namespace_and_type_id(
                company_id=resolved_company_id,
                namespace=namespace,
                type_id=type_id,
            ).delete()
            if deleted > 0:
                await EntityTypeCatalogRevision.bump_catalog_revision(resolved_company_id)
        if deleted > 0:
            invalidate_company(resolved_company_id)
        return deleted > 0


class EntityTypeCatalogRevision(PlatformModel):
    """Поколение каталога ``EntityType``. Плюс один в той же транзакции, что запись типа."""

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "entity_type_catalog_revision"

    company_id: str = DbField(db_pk=True, max_length=100)
    revision: int

    @classmethod
    async def catalog_revision(cls, company_id: str) -> int:
        row = await cls.objects.filter(company_id=company_id).get_or_none()
        if row is None:
            return 0
        return row.revision

    @classmethod
    async def bump_catalog_revision(cls, company_id: str) -> None:
        _ = cls
        _ = await execute_raw(
            "INSERT INTO entity_type_catalog_revision (company_id, revision) VALUES ($1, 1) ON CONFLICT (company_id) DO UPDATE SET revision = entity_type_catalog_revision.revision + 1",
            [company_id],
            using="crm",
        )


def resolve_entity_type_company(company_id: str | None) -> str:
    if company_id is None:
        return require_active_company().company_id
    if company_id == "":
        raise ValueError("company_id is required")
    return company_id


_CatalogKey = tuple[str, str | None]

_lock = threading.Lock()
_store: dict[_CatalogKey, tuple[int, tuple[EntityType, ...]]] = {}


def get_entry(
    company_id: str, namespace: str | None
) -> tuple[int, tuple[EntityType, ...]] | None:
    with _lock:
        entry = _store.get((company_id, namespace))
        if entry is None:
            return None
        revision, items = entry
        return (revision, items)


def put_entry(
    company_id: str,
    namespace: str | None,
    revision: int,
    items: Sequence[EntityType],
) -> None:
    with _lock:
        _store[(company_id, namespace)] = (revision, tuple(items))


def invalidate_company(company_id: str) -> None:
    with _lock:
        for key in [cached_key for cached_key in _store if cached_key[0] == company_id]:
            del _store[key]


def clear_catalog_cache() -> None:
    with _lock:
        _store.clear()


