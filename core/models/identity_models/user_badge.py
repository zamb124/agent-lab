"""Платформенный бейдж сотрудника — таблица ``user_badges`` в ``platform_shared``.

Бейдж — тенантный credential: пара ``(company_id, code)`` уникально
указывает на пользователя. Любой терминал платформы (ТСД stock, POS и
т.д.) логинит через общий ``POST /auth/login/badge`` — скан кода вместо
пароля; привязку/отзыв делает консоль компании, а не складское
приложение. Складской ``stock_barcodes``-индекс про физические метки
сущностей и бейджи не знает — разные домены, разные таблицы.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from oxyde.exceptions import UniqueViolationError

from core.errors.boundary import PlatformConflictError
from core.models.platform_model import PlatformModel
from core.utils.ids import new_id
from core.utils.time import utcnow


class UserBadge(PlatformModel):
    """``(company_id, code)`` → ``user_id``. Глобальная таблица в ``platform_shared``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    badge_id: str = DbField(
        db_pk=True,
        title="ID бейджа",
        description="Уникальный ID привязки",
        json_schema_extra={"readonly": True},
    )

    class Meta:
        is_table: bool = True
        table_name: str = "user_badges"
        indexes: list[Index] = [
            Index(["company_id", "code"], unique=True),
            Index(["company_id", "user_id"]),
        ]

    company_id: str = DbField(
        title="Компания",
        description="Тенант бейджа: номера переиспользуются между компаниями",
        json_schema_extra={"readonly": True},
    )
    code: str = DbField(
        title="Код бейджа",
        description="Сканируемая строка с физического носителя",
        json_schema_extra={"readonly": True},
    )
    user_id: str = DbField(
        title="Пользователь",
        description="Сотрудник-владелец бейджа",
        json_schema_extra={"readonly": True},
    )
    created_at: datetime = DbField(
        title="Создан",
        description="Время привязки",
        json_schema_extra={"readonly": True},
    )

    @classmethod
    async def bind(
        cls, *, company_id: str, code: str, user_id: str
    ) -> Self:
        """Привязать код к сотруднику — единственная точка записи.

        ``unique (company_id, code)`` — один физический код = один
        носитель. Повторная привязка того же кода тому же сотруднику —
        no-op; другому — ``badge_conflict``.
        """
        normalized = code.strip()
        if normalized == "":
            raise PlatformConflictError(
                "Badge code must be non-empty", error_code="badge_empty"
            )
        existing = await cls.resolve(company_id, normalized)
        if existing is not None:
            if existing.user_id == user_id:
                return existing
            raise PlatformConflictError(
                "Badge code is already bound to another user",
                error_code="badge_conflict",
            )
        try:
            return await cls.objects.create(
                instance=cls(
                    badge_id=new_id("ubg"),
                    company_id=company_id,
                    code=normalized,
                    user_id=user_id,
                    created_at=utcnow(),
                )
            )
        except UniqueViolationError as exc:
            raise PlatformConflictError(
                "Badge code is already bound to another user",
                error_code="badge_conflict",
            ) from exc

    @classmethod
    async def resolve(cls, company_id: str, code: str) -> Self | None:
        """Код → привязка внутри тенанта. Пустой code — ValueError."""
        if company_id == "" or code == "":
            raise ValueError("company_id and code are required")
        return await cls.objects.filter(
            company_id=company_id, code=code
        ).get_or_none()

    @classmethod
    async def unbind(cls, company_id: str, code: str) -> int:
        """Отозвать бейдж: удалить привязку. Возвращает число строк."""
        return await cls.objects.filter(
            company_id=company_id, code=code.strip()
        ).delete()

    @classmethod
    async def list_for_user(cls, company_id: str, user_id: str) -> list[Self]:
        """Все бейджи сотрудника (консоль: замена утерянного бейджа)."""
        return await cls.objects.filter(
            company_id=company_id, user_id=user_id
        ).all()
