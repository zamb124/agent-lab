"""Менеджер запросов: база модели и колонка ``company_id``.

``__database_alias__ = "shared"`` фиксирует алиас ``shared``.
Без ``__global_model__ = True`` запрос получает ``company_id`` активной компании.
"""

from __future__ import annotations

from collections.abc import Coroutine, Iterable
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import ClassVar, Literal, Self, TypeGuard, overload, override
from uuid import UUID

from oxyde import F, Field, Model, QueryManager
from oxyde.exceptions import UniqueViolationError
from oxyde.models.base import OxydeModelMeta
from oxyde.queries.base import SupportsExecute
from oxyde.queries.select import Query

from core.context.scope import current_active_company_id
from core.models.database_alias import ensure_oxyde_alias
from core.types import JsonValue, parse_json_object

type PersistedValue = JsonValue | datetime | date | UUID | Decimal | Enum | F


class BoundQuery[TModel: "PlatformModel"](Query[TModel]):
    """Query, который несёт алиас базы и фильтр компании через ``_clone``."""

    def __init__(
        self,
        model_class: type[TModel],
        *,
        database_alias: str | None = None,
        scope_company: bool = False,
    ) -> None:
        super().__init__(model_class)
        self._database_alias: str | None = database_alias
        self._scope_company: bool = scope_company
        self._company_applied: bool = False

    @override
    def _clone(self) -> Self:
        clone = super()._clone()
        clone._database_alias = self._database_alias
        clone._scope_company = self._scope_company
        clone._company_applied = self._company_applied
        return clone

    def _resolve_alias(self, using: str | None) -> str | None:
        if using is not None:
            return using
        return self._database_alias

    async def _using(self, using: str | None) -> str | None:
        alias = self._resolve_alias(using)
        await ensure_oxyde_alias(alias)
        return alias

    def _company_id(self) -> str:
        company_id = current_active_company_id()
        if not company_id:
            raise RuntimeError("company_id is required")
        return company_id

    def _with_company(self) -> Self:
        if not self._scope_company or self._company_applied:
            return self
        scoped = self.filter(company_id=self._company_id())
        scoped._company_applied = True
        return scoped

    @override
    def all(
        self,
        *,
        using: str | None = None,
        client: SupportsExecute | None = None,
    ) -> Coroutine[None, None, list[TModel]]:
        scoped = self._with_company()
        if scoped is not self:
            return scoped.all(using=using, client=client)
        alias = self._resolve_alias(using)
        query_all = super().all

        async def run_all() -> list[TModel]:
            await ensure_oxyde_alias(alias)
            return await query_all(using=alias, client=client)

        return run_all()

    @override
    async def first(
        self,
        *,
        using: str | None = None,
        client: SupportsExecute | None = None,
    ) -> TModel | None:
        scoped = self._with_company()
        if scoped is not self:
            return await scoped.first(using=using, client=client)
        return await super().first(using=await self._using(using), client=client)

    @override
    async def last(
        self,
        *,
        using: str | None = None,
        client: SupportsExecute | None = None,
    ) -> TModel | None:
        scoped = self._with_company()
        if scoped is not self:
            return await scoped.last(using=using, client=client)
        return await super().last(using=await self._using(using), client=client)

    @override
    async def get(
        self,
        *,
        using: str | None = None,
        client: SupportsExecute | None = None,
    ) -> TModel:
        scoped = self._with_company()
        if scoped is not self:
            return await scoped.get(using=using, client=client)
        return await super().get(using=await self._using(using), client=client)

    @override
    async def get_or_none(
        self,
        *,
        using: str | None = None,
        client: SupportsExecute | None = None,
    ) -> TModel | None:
        scoped = self._with_company()
        if scoped is not self:
            return await scoped.get_or_none(using=using, client=client)
        return await super().get_or_none(using=await self._using(using), client=client)

    @override
    async def exists(
        self,
        *,
        using: str | None = None,
        client: SupportsExecute | None = None,
    ) -> bool:
        scoped = self._with_company()
        if scoped is not self:
            return await scoped.exists(using=using, client=client)
        return await super().exists(using=await self._using(using), client=client)

    @override
    async def count(
        self,
        *,
        using: str | None = None,
        client: SupportsExecute | None = None,
    ) -> int:
        scoped = self._with_company()
        if scoped is not self:
            return await scoped.count(using=using, client=client)
        return await super().count(using=await self._using(using), client=client)

    @override
    async def delete(
        self,
        *,
        using: str | None = None,
        client: SupportsExecute | None = None,
    ) -> int:
        scoped = self._with_company()
        if scoped is not self:
            return await scoped.delete(using=using, client=client)
        return await super().delete(using=await self._using(using), client=client)

    @overload
    async def update(
        self,
        *,
        returning: Literal[True],
        using: str | None = None,
        client: SupportsExecute | None = None,
        **values: PersistedValue,
    ) -> list[TModel]: ...

    @overload
    async def update(
        self,
        *,
        returning: Literal[False] = False,
        using: str | None = None,
        client: SupportsExecute | None = None,
        **values: PersistedValue,
    ) -> int: ...

    @override
    async def update(
        self,
        *,
        returning: bool = False,
        using: str | None = None,
        client: SupportsExecute | None = None,
        **values: PersistedValue,
    ) -> int | list[TModel]:
        scoped = self._with_company()
        if scoped is not self:
            return await scoped.update(
                returning=returning,
                using=using,
                client=client,
                **values,
            )
        return await super().update(
            returning=returning,
            using=await self._using(using),
            client=client,
            **values,
        )

    @override
    async def create(
        self,
        *,
        instance: TModel | None = None,
        using: str | None = None,
        client: SupportsExecute | None = None,
        _skip_hooks: bool = False,
        **data: PersistedValue,
    ) -> TModel:
        if self._scope_company:
            company_id = self._company_id()
            if instance is None:
                _ = data.setdefault("company_id", company_id)
            elif isinstance(instance, CompanyScopedModel) and instance.company_id == "":
                instance.company_id = company_id
        return await super().create(
            instance=instance,
            using=await self._using(using),
            client=client,
            _skip_hooks=_skip_hooks,
            **data,
        )

    @override
    async def bulk_create(
        self,
        objects: Iterable[TModel | dict[str, PersistedValue]],
        *,
        using: str | None = None,
        client: SupportsExecute | None = None,
        batch_size: int | None = None,
    ) -> list[TModel]:
        scoped = self._with_company()
        if scoped is not self:
            return await scoped.bulk_create(
                objects, using=using, client=client, batch_size=batch_size
            )
        return await super().bulk_create(
            objects,
            using=await self._using(using),
            client=client,
            batch_size=batch_size,
        )

    @override
    async def bulk_update(
        self,
        objects: Iterable[TModel],
        fields: Iterable[str],
        *,
        using: str | None = None,
        client: SupportsExecute | None = None,
    ) -> int:
        scoped = self._with_company()
        if scoped is not self:
            return await scoped.bulk_update(
                objects, fields, using=using, client=client
            )
        return await super().bulk_update(
            objects,
            fields,
            using=await self._using(using),
            client=client,
        )


class BoundQueryManager[TModel: "PlatformModel"](QueryManager[TModel]):
    """Фабрика ``BoundQuery`` для одной модели."""

    def __init__(
        self,
        model_class: type[TModel],
        *,
        database_alias: str | None,
        scope_company: bool,
    ) -> None:
        super().__init__(model_class)
        self._database_alias: str | None = database_alias
        self._scope_company: bool = scope_company

    @override
    def _query(self) -> BoundQuery[TModel]:
        return BoundQuery(
            self.model_class,
            database_alias=self._database_alias,
            scope_company=self._scope_company,
        )


_ALLOWED_DATABASE_ALIASES: frozenset[str | None] = frozenset(
    {
        None,
        "shared",
        "flows",
        "tracing",
        "rag",
        "secrets",
        "realtime",
        "office",
        "worktracker",
        "wiki",
        "search",
        "crm",
        "sync",
        "stock",
        "shop",
        "geo",
    }
)


def _require_database_alias(model_name: str, database: str | None) -> None:
    if database in _ALLOWED_DATABASE_ALIASES:
        return
    allowed = ", ".join(
        repr(a) for a in sorted(a for a in _ALLOWED_DATABASE_ALIASES if a is not None)
    )
    raise RuntimeError(
        f"{model_name} __database_alias__ must be {allowed} or None"
    )


def _is_platform_table(created: type) -> TypeGuard[type[PlatformModel]]:
    if created.__module__ == "core.models.platform_model" and created.__name__ == "PlatformModel":
        return False
    return issubclass(created, PlatformModel)


class PlatformModelMeta(OxydeModelMeta):
    """Метакласс после вывода внешних ключей Oxyde."""

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        **kwargs: object,
    ) -> type:
        # Метод list затеняет builtin list, и разбор list[str] в Python 3.14 падает.
        list_method = namespace.get("list")
        shadowed_list = isinstance(list_method, classmethod)
        if shadowed_list:
            del namespace["list"]
        created = OxydeModelMeta.__new__(mcs, name, bases, namespace, **kwargs)
        if shadowed_list:
            setattr(created, "list", list_method)
        if _is_platform_table(created):
            created.embed_json_documents()
        return created


class PlatformModel(Model, metaclass=PlatformModelMeta):
    """Модель платформы. ``objects`` знает базу и, если надо, компанию.

    ``__database_alias__ = "shared"`` — алиас shared, иначе база процесса.
    ``__global_model__ = True`` — без фильтра ``company_id``.
    """

    __database_alias__: ClassVar[str | None] = None
    __database_aliases__: ClassVar[tuple[str, ...]] = ()
    __global_model__: ClassVar[bool] = False

    @override
    async def save(
        self,
        *,
        client: SupportsExecute | None = None,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> Self:
        alias = using
        if alias is None:
            aliases = type(self).__database_aliases__
            if len(aliases) > 1:
                raise RuntimeError(f"{type(self).__name__} save requires using")
            if len(aliases) == 1:
                alias = aliases[0]
            else:
                alias = type(self).__database_alias__
        await ensure_oxyde_alias(alias)
        return await super().save(client=client, using=alias, update_fields=update_fields)

    @classmethod
    def table_name(cls) -> str:
        name = cls._db_meta.table_name
        if not isinstance(name, str) or name == "":
            raise RuntimeError(f"{cls.__name__} has no table name")
        return name

    @classmethod
    def primary_key_name(cls) -> str:
        pk = cls._db_meta.pk_field
        if pk is None:
            raise RuntimeError(f"{cls.__name__} has no primary key")
        return pk

    @classmethod
    def _require_id(cls, entity_id: str) -> str:
        if entity_id == "":
            raise ValueError(f"{cls.__name__} {cls.primary_key_name()} is required")
        return entity_id

    @classmethod
    def _entity_id(cls, entity: Self) -> str:
        pk = cls.primary_key_name()
        payload = parse_json_object(entity.model_dump_json(include={pk}), pk)
        if pk not in payload:
            raise RuntimeError(f"{cls.__name__} has no field {pk}")
        raw = payload[pk]
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__}.{pk} must be str")
        return cls._require_id(raw)

    @classmethod
    async def get(cls, entity_id: str) -> Self | None:
        pk = cls.primary_key_name()
        return await cls.objects.filter(**{pk: cls._require_id(entity_id)}).get_or_none()

    @classmethod
    async def set(cls, entity: Self) -> bool:
        entity_id = cls._entity_id(entity)
        existing = await cls.get(entity_id)
        if existing is None:
            try:
                _ = await cls.objects.create(instance=entity)
            except UniqueViolationError:
                raced = await cls.get(entity_id)
                if raced is None:
                    raise
                _ = await entity.save()
            return True
        _ = await entity.save()
        return True

    @classmethod
    async def delete_by_id(cls, entity_id: str) -> bool:
        pk = cls.primary_key_name()
        deleted = await cls.objects.filter(**{pk: cls._require_id(entity_id)}).delete()
        return deleted > 0

    @classmethod
    async def list(cls, *, limit: int, offset: int = 0) -> list[Self]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        return await cls.objects.limit(limit).offset(offset).all()

    @classmethod
    async def count_all(cls) -> int:
        return await cls.objects.count()

    @classmethod
    async def get_many(cls, entity_ids: list[str]) -> dict[str, Self]:
        if len(entity_ids) == 0:
            return {}
        pk = cls.primary_key_name()
        for entity_id in entity_ids:
            _ = cls._require_id(entity_id)
        rows = await cls.objects.filter(**{f"{pk}__in": entity_ids}).all()
        found: dict[str, Self] = {}
        for row in rows:
            found[cls._entity_id(row)] = row
        return found

    @classmethod
    def embed_json_documents(cls) -> None:
        """Oxyde считает аннотацию другой таблицы внешним ключом.

        ``db_type`` JSON/JSONB значит, что в колонке лежит сам документ.
        """
        if not cls._is_table:
            return
        synthetic_names: list[str] = []
        for field_name, column in cls._db_meta.field_metadata.items():
            foreign_key = column.foreign_key
            if foreign_key is None or column.db_type is None:
                continue
            if column.db_type.strip().upper() not in {"JSON", "JSONB"}:
                continue
            column.foreign_key = None
            column.db_column = field_name
            synthetic_names.append(foreign_key.column_name)
        if not synthetic_names:
            return
        for synthetic_name in synthetic_names:
            if synthetic_name in cls.model_fields:
                del cls.model_fields[synthetic_name]
            if synthetic_name in cls.__pydantic_fields__:
                del cls.__pydantic_fields__[synthetic_name]
            if synthetic_name in cls.__annotations__:
                del cls.__annotations__[synthetic_name]
            if synthetic_name in cls._db_meta.field_metadata:
                del cls._db_meta.field_metadata[synthetic_name]
        cls._db_meta.column_types = None
        _ = cls.model_rebuild(force=True)
        cls._compute_column_types()
    shared: ClassVar[QueryManager[Self]]
    company: ClassVar[QueryManager[Self]]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not cls._is_table:
            return
        database_aliases = cls.__database_aliases__
        if database_aliases:
            for database_alias in database_aliases:
                _require_database_alias(cls.__name__, database_alias)
        else:
            _require_database_alias(cls.__name__, cls.__database_alias__)
        database = cls.__database_alias__
        global_model = cls.__global_model__
        if not global_model and "company_id" not in cls.model_fields:
            raise RuntimeError(f"{cls.__name__} requires company_id")
        manager: QueryManager[Self] = BoundQueryManager(
            cls,
            database_alias=database,
            scope_company=not global_model,
        )
        setattr(cls, "objects", manager)
        if database == "shared":
            cls.shared = manager
        if not global_model:
            cls.company = manager


class CompanyScopedModel(PlatformModel):
    """Таблица с обязательной колонкой ``company_id``."""

    company_id: str = Field(db_index=True)
