"""Карта склада (stock_locations) — где что лежит и что куда едет.

Каждая строка — одно место: зона, стеллаж, ячейка, паллета, виртуальный
конец движения. Дерево задаётся через ``parent_id`` + ``parent_path``
(материализованный путь ``/id/id/``) — как каталоги на диске: «Зона
A / стеллаж 3 / ячейка A-03-14».

Типы локаций (``usage``) и что они значат для бизнеса:

    view        — зоны и стеллажи: группирующий уровень, товара на
                  «зоне» физически нет — это логика навигации
    bin         — ячейка хранения: реальная полка, здесь лежит остаток
    container   — контейнер (паллета/короб/тоут/тележка): сам является
                  локацией и может содержать quant'ы и вложенные
                  контейнеры; «переезд контейнера» = смена parent_id
    partner     — виртуальный конец «поставщик/клиент/подрядчик»
                  (``partner_role``): наши деньги пересекают границу
    transit     — виртуальная «дорога между складами»: товар в пути
                  числится на ней до приёмки на другом конце
    adjustment  — виртуальная «инвентаризация»: недостачи уходят в неё,
                  излишки приходят из неё

Виртуальные локации создаются один раз на компанию (init_company_stock)
с детерминированными id ``{company}:partner:vendor`` и т.п. — это
концы движения, а не полки: остатков на них нет (quant не пишется), но
любой приход/расход начинается или заканчивается ими.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from apps.stock.models.common import STOCK_DB, new_id
from apps.stock.models.enums import (
    StockLocationUsage,
    StockPartnerRole,
)
from core.errors.boundary import PlatformConflictError
from core.models.platform_model import PlatformModel
from core.types import require_json_object
from core.utils.time import utcnow


class StockLocation(PlatformModel):
    """Одно место на карте склада. Таблица ``stock_locations``.

    Поля навигации и правил:

    * ``parent_id``/``parent_path`` — дерево; ``parent_path`` вида
      ``/root_id/parent_id/self_id/`` даёт «всё поддерево одним
      запросом» (префиксный LIKE) — для «что лежит в зоне A» и для
      переезда контейнера со всем содержимым.
    * ``usage``/``partner_role`` — тип места (см. модульный docstring);
      ``partner_role=vendor/customer`` различает партнёрские концы.
    * ``storage_type_id`` — тип хранения ячейки: правила «что сюда
      можно класть» (только паллеты/россыпь, смешивание, ёмкость).
    * ``container_type_id`` — если это контейнер: его тип (паллета,
      короб...) с габаритами и правилами вложения.
    * ``level`` — ярус (1 — пол); ``pick_sequence`` — порядок обхода
      при сборке (змейка по зоне, чтобы оператор шёл без возвратов).
    * ``putaway_blocked``/``removal_blocked`` — «закрыто на приёмку/
      отгрузку»: карантинная зона или ячейка под ревизией.
    * ``allow_negative`` — разрешить уходить в минус (зона списаний);
      обычные ячейки минус запрещают — ``insufficient_stock``.
    * ``warehouse_id`` — NULL у виртуальных локаций компании
      (partner/adjustment/transit живут вне складов).
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_locations"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id", "parent_id"]),
            Index(["company_id", "usage"]),
            Index(["company_id", "parent_path"]),
        ]

    location_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str | None = DbField(default=None, max_length=64)
    parent_id: str | None = DbField(default=None, max_length=64)
    parent_path: str = DbField(default="/", max_length=2048)
    """Материализованный путь ``/id/id/`` — префиксные запросы поддерева."""
    complete_name: str = DbField(default="", max_length=512)
    name: str = DbField(max_length=255)
    usage: StockLocationUsage = DbField()
    partner_role: StockPartnerRole | None = DbField(default=None, max_length=32)
    storage_type_id: str | None = DbField(default=None, max_length=64)
    container_type_id: str | None = DbField(default=None, max_length=64)
    level: int = DbField(default=1)
    """Ярус ячейки (1 — пол/нижний), для ресурсных ограничений."""
    pick_sequence: int = DbField(default=0)
    """Порядок обхода при отборе (змейка по зоне)."""
    putaway_blocked: bool = DbField(default=False)
    removal_blocked: bool = DbField(default=False)
    is_active: bool = DbField(default=True)
    allow_negative: bool = DbField(default=False)
    last_count_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField()

    @classmethod
    def build_path(cls, parent_path: str, location_id: str) -> str:
        return f"{parent_path}{location_id}/"

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def create_with_parent_path(
        cls,
        *,
        company_id: str,
        warehouse_id: str | None,
        parent: Self | None,
        name: str,
        usage: StockLocationUsage,
        allow_negative: bool = False,
        storage_type_id: str | None = None,
        container_type_id: str | None = None,
        pick_sequence: int | None = None,
        level: int | None = None,
        partner_role: StockPartnerRole | None = None,
    ) -> Self:
        """Вставляет локацию. parent None — корень: parent_id None, путь от /, complete_name = name. Иначе путь и complete_name от родителя. pick_sequence None — 0. level None — 1."""
        location_id = new_id("loc")
        parent_path = parent.parent_path if parent is not None else "/"
        if parent is None:
            parent_name = ""
        elif parent.complete_name != "":
            parent_name = parent.complete_name
        else:
            parent_name = parent.name
        row = cls(
            location_id=location_id,
            company_id=company_id,
            warehouse_id=warehouse_id,
            parent_id=parent.location_id if parent is not None else None,
            parent_path=cls.build_path(parent_path, location_id),
            complete_name=f"{parent_name}/{name}" if parent_name else name,
            name=name,
            usage=usage,
            allow_negative=allow_negative,
            storage_type_id=storage_type_id,
            container_type_id=container_type_id,
            pick_sequence=pick_sequence if pick_sequence is not None else 0,
            level=level if level is not None else 1,
            partner_role=partner_role,
            created_at=utcnow(),
        )
        return await cls.create(row)

    @classmethod
    async def by_id(cls, company_id: str, location_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, location_id=location_id
        ).get_or_none()

    @classmethod
    async def by_id_locked(cls, company_id: str, location_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, location_id=location_id
        ).for_update().get_or_none()

    @classmethod
    async def found_in_company_by_ids(cls, company_id: str, location_ids: list[str]) -> dict[str, Self]:
        """Найденные локации компании по id. Пустой список — {}. Отсутствующие id не входят. Порядка нет."""
        if not location_ids:
            return {}
        rows = await cls.objects.filter(
            company_id=company_id, location_id__in=location_ids
        ).all()
        return {row.location_id: row for row in rows}


    @classmethod
    async def list_by_usage_and_name(cls, company_id: str) -> list[Self]:
        """Все локации компании, ORDER BY usage, name. Предела нет."""
        return await cls.objects.filter(company_id=company_id).order_by(
            "usage", "name"
        ).all()

    @classmethod
    async def list_containers(
        cls,
        company_id: str,
        warehouse_id: str | None = None,
        parent_location_id: str | None = None,
    ) -> list[Self]:
        """Список контейнеров (паллет/коробов) на складе или внутри места.

        Контейнер — локация ``usage=container``: сам хранит quant'ы и
        детей, физически перемещается как единица. ``parent_location_id``
        — «что лежит в этом контейнере» (вложенные контейнеры).
        """
        query = cls.objects.filter(
            company_id=company_id,
            usage=StockLocationUsage.CONTAINER,
            is_active=True,
        )
        if warehouse_id is not None:
            query = query.filter(warehouse_id=warehouse_id)
        if parent_location_id is not None:
            query = query.filter(parent_id=parent_location_id)
        return await query.order_by("complete_name").all()

    @classmethod
    async def list_child_containers(
        cls, company_id: str, parent_ids: list[str]
    ) -> dict[str, list[Self]]:
        """Контейнеры-дети по набору родителей: ``parent_id → [container]``.

        Для снимков «что стоит в ячейке» при подсказках размещения:
        одна выборка на всех кандидатов вместо запроса на ячейку.
        """
        if not parent_ids:
            return {}
        rows = await cls.objects.filter(
            company_id=company_id,
            parent_id__in=parent_ids,
            usage=StockLocationUsage.CONTAINER,
            is_active=True,
        ).all()
        result: dict[str, list[Self]] = {}
        for row in rows:
            if row.parent_id is not None:
                result.setdefault(row.parent_id, []).append(row)
        return result

    @classmethod
    async def list_in_subtree(
        cls,
        company_id: str,
        root: Self,
        *,
        usage: StockLocationUsage | None = None,
        active_only: bool = True,
        limit: int = 500,
        offset: int = 0,
    ) -> list[Self]:
        """Всё содержимое зоны/контейнера — потомки по ``parent_path``.

        «Что лежит в зоне A» = все локации, чей путь начинается с
        ``root.parent_path``: ячейки, контейнеры, вложенные уровни.
        Порядок — по ``pick_sequence`` (маршрут обхода при сборке).
        """
        query = cls.objects.filter(
            company_id=company_id,
            parent_path__startswith=root.parent_path,
        )
        if usage is not None:
            query = query.filter(usage=usage)
        if active_only:
            query = query.filter(is_active=True)
        return await query.order_by("pick_sequence", "complete_name").limit(
            limit
        ).offset(offset).all()

    @classmethod
    async def list_subtree_ids(cls, company_id: str, root_id: str) -> list[str]:
        """Id всех потомков одним запросом — «весь объём этой зоны».

        Используется при сборе остатков и при переезде контейнера:
        поддерево — это ``root_id`` плюс все, у кого ``parent_path``
        начинается с его пути.
        """
        root = await cls.by_id(company_id, root_id)
        if root is None:
            return []
        rows = await execute_raw(
            "SELECT location_id FROM stock_locations WHERE company_id = $1 AND parent_path LIKE $2 || '%' ORDER BY parent_path",
            [company_id, root.parent_path],
            using=STOCK_DB,
        )
        return [
            str(parsed["location_id"])
            for row in rows
            if (parsed := require_json_object(row, "stock_subtree")).get(
                "location_id"
            )
            is not None
        ]

    @classmethod
    async def list_count_bins(
        cls,
        company_id: str,
        warehouse_id: str,
        *,
        due_before: datetime,
        limit: int,
    ) -> list[Self]:
        """Ячейки склада, чей пересчёт просрочен — очередь cycle count.

        «Давно не считали» = ``last_count_at`` пуст (ещё ни разу) или
        старше порога. Порог — свой у каждой ячейки: ``cycle_count_days``
        её типа хранения (мороз реже, овощи чаще), без типа/дней —
        глобальный ``due_before``. Порядок — самые старые первыми,
        так тик равномерно обносит склад.
        """
        from apps.stock.models.storage_type import StockStorageType

        # Нижняя граница выборки — самый мягкий порог (минимальный
        # интервал): без неё per-type фильтрация уронила бы строки,
        # которые глобальный порог считает свежими.
        storage_types = await StockStorageType.list_by_name_for_warehouse(
            company_id, warehouse_id
        )
        type_days = {
            t.storage_type_id: t.cycle_count_days
            for t in storage_types
            if t.cycle_count_days is not None
        }
        candidates = await cls.objects.filter(
            company_id=company_id,
            warehouse_id=warehouse_id,
            usage=StockLocationUsage.BIN,
            is_active=True,
        ).order_by("last_count_at").limit(limit * 5).all()
        now = utcnow()
        due: list[Self] = []
        for loc in candidates:
            days = (
                type_days.get(loc.storage_type_id)
                if loc.storage_type_id is not None
                else None
            )
            threshold = (
                now - timedelta(days=days)
                if days is not None
                else due_before
            )
            if loc.last_count_at is None or loc.last_count_at < threshold:
                due.append(loc)
                if len(due) >= limit:
                    break
        return due

    @classmethod
    async def touch_counted(
        cls, company_id: str, location_ids: list[str], *, at: datetime
    ) -> None:
        """Отметить ячейки «пересчитаны» — из lane коммита инвентаризации."""
        if not location_ids:
            return
        _ = await cls.objects.filter(
            company_id=company_id, location_id__in=location_ids
        ).update(using=STOCK_DB, last_count_at=at)

    @classmethod
    async def virtual_by_usage(
        cls,
        company_id: str,
        usage: StockLocationUsage,
        partner_role: StockPartnerRole | None = None,
    ) -> Self | None:
        """Виртуальный конец компании по типу — «поставщик», «клиент» и т.п.

        Эти локации одни на компанию (``warehouse_id IS NULL``) и
        создаются инициализацией; движения к ним — это пересечение
        границы запаса (приход/расход/инвентаризация), а не перекладка.
        """
        query = cls.objects.filter(
            company_id=company_id, usage=usage, warehouse_id=None
        )
        if partner_role is not None:
            query = query.filter(partner_role=partner_role)
        return await query.get_or_none()

    @classmethod
    async def rebind_subtree(
        cls,
        *,
        company_id: str,
        root: Self,
        new_parent: Self,
        new_warehouse_id: str | None,
    ) -> int:
        """Переезд контейнера со всем содержимым — один UPDATE по пути.

        Контейнер (и всё его поддерево — вложенные контейнеры, остатки)
        переподчиняется новому родителю: ``parent_path`` каждого потомка
        переписывается префиксной заменой («папка переехала → адреса
        всех файлов поменялись»), ``warehouse_id`` синхронно обновляется
        если переехал на другой склад. Quant'ы остатков сам не трогает —
        денормализацию обновляет вызывающий (строка ``kind=container``).

        Ограничение вложения: внутрь контейнера можно класть только
        контейнеры (``container_nesting_invalid``) — «короб на паллете»
        да, «ячейка в коробе» нет.
        """
        if new_parent.usage == StockLocationUsage.CONTAINER and (
            root.usage != StockLocationUsage.CONTAINER
        ):
            raise PlatformConflictError(
                "Only containers nest inside containers",
                error_code="container_nesting_invalid",
            )
        old_path = root.parent_path
        new_path = cls.build_path(new_parent.parent_path, root.location_id)
        rows = await execute_raw(
            "UPDATE stock_locations SET parent_path = $3 || substring(parent_path from length($4) + 1), complete_name = $5 || substring(complete_name from length($6) + 1), warehouse_id = $7 WHERE company_id = $1 AND parent_path LIKE $2 || '%' RETURNING location_id",
            [
                company_id,
                old_path,
                new_path,
                old_path,
                new_parent.complete_name or new_parent.name,
                root.complete_name or root.name,
                new_warehouse_id,
            ],
            using=STOCK_DB,
        )
        _ = await cls.objects.filter(
            company_id=company_id, location_id=root.location_id
        ).update(
            using=STOCK_DB,
            parent_id=new_parent.location_id,
            warehouse_id=new_warehouse_id,
        )
        return len(rows)
