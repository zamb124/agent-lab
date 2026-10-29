"""Правила размещения (stock_putaway_rules) — «положить туда-то».

Правило «товары категории X кладём в зону Z»: настраиваемая логика
putaway по категориям/товарам. Это первый уровень стратегии — до типов
хранения: система сначала смотрит правило «для этого продукта мы
договорились хранить в морозилке», и только потом выбирает конкретную
ячейку морозилки по ограничениям storage type.
"""

from __future__ import annotations

from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import STOCK_DB, new_id
from core.models.platform_model import PlatformModel


class StockPutawayRule(PlatformModel):
    """Правило putaway. Таблица ``stock_putaway_rules``."""

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_putaway_rules"
        indexes: list[Index] = [
            Index(["company_id", "warehouse_id", "location_in_id", "sequence"])
        ]

    rule_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    product_id: str | None = DbField(default=None, max_length=64)
    category: str | None = DbField(default=None, max_length=128)
    owner_entity_id: str | None = DbField(default=None, max_length=64)
    """Владелец консигнации: «зона владельца X» на складе ответхранения.
    Правило с владельцем срабатывает только на его запас и сильнее
    общего правила (частное > общее)."""
    location_in_id: str = DbField(max_length=64)
    location_out_id: str = DbField(max_length=64)
    sequence: int = DbField(default=0)
    is_active: bool = DbField(default=True)
    """Пауза правила без удаления: сезонная зона, временный запрет."""

    @classmethod
    async def list_active_matched_by_sequence_asc_and_specificity_desc(
        cls,
        *,
        company_id: str,
        warehouse_id: str,
        product_id: str,
        category: str,
        location_ids: list[str],
        owner_entity_id: str | None = None,
    ) -> list[Self]:
        """Активные правила склада для location_ids. Товар, категория и владелец: None в правиле подходит всем, иначе точное совпадение. Порядок — sequence ASC, затем более частное правило раньше. Пустой location_ids в теле не отсекается."""
        rows = await cls.objects.filter(
            company_id=company_id,
            warehouse_id=warehouse_id,
            location_in_id__in=location_ids,
            is_active=True,
        ).order_by("sequence").all()
        matched = [
            r
            for r in rows
            if (r.product_id is None or r.product_id == product_id)
            and (r.category is None or r.category == category)
            and (
                r.owner_entity_id is None
                or r.owner_entity_id == owner_entity_id
            )
        ]
        matched.sort(
            key=lambda r: (
                r.sequence,
                -(r.product_id is not None)
                - (r.category is not None)
                - (r.owner_entity_id is not None),
            )
        )
        return matched

    @classmethod
    async def create(
        cls,
        *,
        company_id: str,
        warehouse_id: str,
        location_in_id: str,
        location_out_id: str,
        product_id: str | None = None,
        category: str | None = None,
        owner_entity_id: str | None = None,
        sequence: int = 0,
    ) -> Self:
        """Вставляет правило. rule_id новый."""
        return await cls.objects.create(
            instance=cls(
                rule_id=new_id("pur"),
                company_id=company_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                category=category,
                owner_entity_id=owner_entity_id,
                location_in_id=location_in_id,
                location_out_id=location_out_id,
                sequence=sequence,
            )
        )

    @classmethod
    async def list_for_warehouse_by_sequence_and_rule_id_asc(
        cls, company_id: str, warehouse_id: str
    ) -> list[Self]:
        """Все правила размещения склада, ORDER BY sequence, rule_id ASC. Предела нет."""
        return await cls.objects.filter(
            company_id=company_id, warehouse_id=warehouse_id
        ).order_by("sequence", "rule_id").all()

    @classmethod
    async def by_id(cls, company_id: str, rule_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, rule_id=rule_id
        ).get_or_none()

    @classmethod
    async def update_locations_filters_and_sequence(
        cls,
        company_id: str,
        rule_id: str,
        *,
        location_in_id: str | None = None,
        location_out_id: str | None = None,
        product_id: str | None = None,
        category: str | None = None,
        owner_entity_id: str | None = None,
        sequence: int | None = None,
    ) -> Self | None:
        """Пишет только переданные поля: локации, product_id, category, owner_entity_id, sequence. None не пишет поле и не очищает его. Все None — строка не сохраняется. Нет строки — None."""
        rule = await cls.by_id(company_id, rule_id)
        if rule is None:
            return None
        fields: list[str] = []
        for name, value in (
            ("location_in_id", location_in_id),
            ("location_out_id", location_out_id),
            ("product_id", product_id),
            ("category", category),
            ("owner_entity_id", owner_entity_id),
            ("sequence", sequence),
        ):
            if value is not None:
                setattr(rule, name, value)
                fields.append(name)
        if fields:
            _ = await rule.save(using=STOCK_DB, update_fields=fields)
        return rule

    @classmethod
    async def update_is_active(
        cls, company_id: str, rule_id: str, active: bool
    ) -> None:
        """Пишет is_active по company_id и rule_id. updated_at не трогает. Нет строки — ничего не меняет."""
        _ = await cls.objects.filter(
            company_id=company_id, rule_id=rule_id
        ).update(using=STOCK_DB, is_active=active)

    @classmethod
    async def delete_rule(cls, company_id: str, rule_id: str) -> None:
        _ = await cls.objects.filter(
            company_id=company_id, rule_id=rule_id
        ).delete()
