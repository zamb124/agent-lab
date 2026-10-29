"""Единицы складского ресурса (stock_resources) — техника и люди.

«Ресурс» — это конкретная единица, которая физически выполняет задание
на складе: погрузчик №3, штабелёр, тележка, пеший отборщик. Каждая
единица имеет код, штрихкод и тип (``StockResourceType`` — его
возможности: до какого яруса достаёт, что возит).

Оператор «входит на ресурс» сканированием его штрихкода в начале
смены — с этого момента система знает «этот человек сейчас на этом
погрузчике» и может выдавать задания с учётом возможностей техники.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.barcode_index import StockBarcodeIndex
from apps.stock.models.common import STOCK_DB, stock_warehouse_lane
from apps.stock.models.enums import StockBarcodeEntityType
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.lanes import LaneOutcome, LaneRun, LaneScope, run_in_lanes
from core.models import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockResourceLogoutResult(StrictBaseModel):
    """Результат выхода: id ресурса, с которого снят вход (или None)."""

    resource_id: str | None = None


class StockResource(PlatformModel):
    """Конкретная единица техники/ресурса склада. Таблица ``stock_resources``.

    ``code`` — инвентарный номер («Погрузчик-3»); метка входа сканом
    привязана в ``stock_barcodes`` (``entity_type=resource``);
    ``current_user_id`` — кто сейчас на нём работает.
    Одна единица — один оператор, один оператор — одна единица на
    складе (иначе задания поедут «не на ту машину»).
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_resources"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id", "code"], unique=True),
            Index(["company_id", "current_user_id"]),
        ]

    resource_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    resource_type_id: str = DbField(max_length=64)
    code: str = DbField(max_length=64)
    current_user_id: str | None = DbField(default=None, max_length=64)
    logged_in_at: datetime | None = DbField(default=None)
    is_active: bool = DbField(default=True)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, resource_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, resource_id=resource_id
        ).get_or_none()


    @classmethod
    async def by_user(
        cls, company_id: str, warehouse_id: str, user_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            warehouse_id=warehouse_id,
            current_user_id=user_id,
        ).get_or_none()

    @classmethod
    async def list_for_warehouse_by_code_asc(
        cls, company_id: str, warehouse_id: str
    ) -> list[Self]:
        """Все ресурсы склада, ORDER BY code ASC. Предела нет."""
        return await cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        ).order_by("code").all()

    @classmethod
    async def login_in_lane(
        cls,
        *,
        company_id: str,
        warehouse_id: str,
        resource_id: str | None,
        barcode: str | None,
        user_id: str,
        idempotency_key: str,
        command_type: str,
    ) -> LaneRun[Self]:
        """Вход оператора на ресурс сканом — «начало смены на технике».

        Правила занятости:
          * ресурс занят другим оператором → ``resource_occupied``;
          * оператор уже на другом ресурсе склада →
            ``resource_user_bound»;
          * ресурс выведен из эксплуатации → ``resource_inactive``.

        Сериализовано полосой склада: два оператора одновременно не
        «сядут» на одну машину.
        """

        async def body(_scope: LaneScope) -> LaneOutcome[Self]:
            resource: Self | None = None
            if resource_id is not None:
                resource = await cls.objects.filter(
                    company_id=company_id, resource_id=resource_id
                ).for_update().get_or_none()
            elif barcode is not None:
                entry = await StockBarcodeIndex.resolve(
                    company_id, barcode.strip()
                )
                if (
                    entry is not None
                    and entry.entity_type == StockBarcodeEntityType.RESOURCE
                ):
                    resource = await cls.objects.filter(
                        company_id=company_id,
                        warehouse_id=warehouse_id,
                        resource_id=entry.entity_id,
                    ).for_update().get_or_none()
            if resource is None or resource.warehouse_id != warehouse_id:
                raise PlatformNotFoundError(
                    "Resource not found", error_code="resource_not_found"
                )
            if not resource.is_active:
                raise PlatformConflictError(
                    "Resource is inactive", error_code="resource_inactive"
                )
            if (
                resource.current_user_id is not None
                and resource.current_user_id != user_id
            ):
                raise PlatformConflictError(
                    "Resource is occupied by another user",
                    error_code="resource_occupied",
                )
            existing = await cls.by_user(company_id, warehouse_id, user_id)
            if existing is not None and existing.resource_id != resource.resource_id:
                raise PlatformConflictError(
                    "User already logged in on another resource",
                    error_code="resource_user_bound",
                )
            now = utcnow()
            _ = await cls.objects.filter(
                company_id=company_id, resource_id=resource.resource_id
            ).update(
                using=STOCK_DB,
                current_user_id=user_id,
                logged_in_at=now,
                updated_at=now,
            )
            resource.current_user_id = user_id
            resource.logged_in_at = now
            return LaneOutcome(result=resource, events=[])

        return await run_in_lanes(
            [stock_warehouse_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=user_id,
            result_type=cls,
            body=body,
        )

    @classmethod
    async def logout_in_lane(
        cls,
        *,
        company_id: str,
        warehouse_id: str,
        user_id: str,
        idempotency_key: str,
        command_type: str,
    ) -> LaneRun[StockResourceLogoutResult]:
        """Выход оператора с ресурса — «конец смены» (no-op без входа).

        Снимает привязку ``current_user_id``: техника свободна для
        следующего. Если входа не было — просто возвращает
        ``resource_id=None`` без ошибки.
        """

        async def body(_scope: LaneScope) -> LaneOutcome[StockResourceLogoutResult]:
            resource = await cls.objects.filter(
                company_id=company_id,
                warehouse_id=warehouse_id,
                current_user_id=user_id,
            ).for_update().get_or_none()
            if resource is None:
                return LaneOutcome(
                    result=StockResourceLogoutResult(resource_id=None), events=[]
                )
            _ = await cls.objects.filter(
                company_id=company_id, resource_id=resource.resource_id
            ).update(
                using=STOCK_DB,
                current_user_id=None,
                logged_in_at=None,
                updated_at=utcnow(),
            )
            return LaneOutcome(
                result=StockResourceLogoutResult(
                    resource_id=resource.resource_id
                ),
                events=[],
            )

        return await run_in_lanes(
            [stock_warehouse_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=user_id,
            result_type=StockResourceLogoutResult,
            body=body,
        )
