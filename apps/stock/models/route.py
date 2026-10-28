"""Маршрут движения товара (``stock_routes``) — цепочка плеч склада.

Маршрут описывает, по каким операциям товар идёт от точки входа к
финальному месту хранения или отгрузки: «приёмка → контроль
качества → хранение», «отбор → упаковка → отгрузка», межскладская
перевозка через транзитную локацию.

Плечи маршрута — это упорядоченный список ``steps`` внутри строки
маршрута (JSONB): шаг не живёт отдельно от маршрута, не имеет своих
состояний и ссылок — это чистая часть агрегата, как строка заказа в
заказе. Когда строка накладной создаётся с ``route_id``, движок
разворачивает её в цепочку связанных ``move``: первый шаг работает
сразу, последующие ждут в ``waiting`` и активируются по мере
проводки предыдущих (pull-семантика — спрос тянет товар вперёд по
цепочке).
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from pydantic import Field

from apps.stock.models.common import STOCK_DB, new_id
from core.models import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockRouteStepSpec(StrictBaseModel):
    """Одно плечо маршрута: тип операции + границы плеча.

    ``operation_type_id`` задаёт детали плеча (дефолтные локации,
    политику резерва, печать документов); явные
    ``source_location_id``/``dest_location_id`` перекрывают дефолты
    типа операции. ``sequence`` — порядок плеча в цепочке: 10, 20,
    30… (место для вставки между существующими без перенумерации).
    """

    sequence: int = Field(default=10, ge=0)
    operation_type_id: str
    source_location_id: str | None = None
    dest_location_id: str | None = None


class StockRoute(PlatformModel):
    """Именованный маршрут: заголовок и плечи цепочки. ``stock_routes``.

    ``warehouse_id=None`` — межскладской маршрут (шаги могут вести в
    другой склад через транзитную локацию); иначе маршрут локальный
    для одного склада.

    ``steps`` — упорядоченные плечи (JSONB): одна строка маршрута
    целиком описывает цепочку — чтение маршрута это одна запись,
    а не join по таблице шагов.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_routes"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id"]),
        ]

    route_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str | None = DbField(default=None, max_length=64)
    name: str = DbField(max_length=255)
    code: str = DbField(default="", max_length=64)
    steps: list[StockRouteStepSpec] = DbField(
        default_factory=list, db_type="JSONB"
    )
    """Плечи цепочки по возрастанию ``sequence`` — порядок движения."""
    is_active: bool = DbField(default=True)
    created_at: datetime = DbField()

    @classmethod
    async def by_id(cls, company_id: str, route_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, route_id=route_id
        ).get_or_none()

    @classmethod
    async def list_active_by_name(
        cls,
        company_id: str,
        *,
        warehouse_id: str | None = None,
        limit: int = 200,
    ) -> list[Self]:
        """Активные маршруты компании, ORDER BY name, limit по умолчанию 200, без offset. warehouse_id None не фильтрует."""
        q = cls.objects.filter(company_id=company_id, is_active=True)
        if warehouse_id is not None:
            q = q.filter(warehouse_id=warehouse_id)
        return await q.order_by("name").limit(limit).all()

    @classmethod
    async def create(
        cls,
        *,
        company_id: str,
        warehouse_id: str | None,
        name: str,
        code: str = "",
        steps: list[StockRouteStepSpec] | None = None,
    ) -> Self:
        """Вставляет маршрут. route_id новый. steps None становится пустым списком и сортируется по sequence. code по умолчанию пустая строка."""
        return await cls.objects.create(
            instance=cls(
                route_id=new_id("rte"),
                company_id=company_id,
                warehouse_id=warehouse_id,
                name=name,
                code=code,
                steps=sorted(steps or [], key=lambda s: s.sequence),
                created_at=utcnow(),
            )
        )
