"""Таблица идентичности."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import execute_raw
from pydantic import ConfigDict, Field

from core.models.identity_models.contracts import (
    UserStatus,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object


class User(PlatformModel):
    """Пользователь. Глобальная таблица ``users`` в ``platform_shared``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(json_schema_extra={"storage_prefix": "user"})

    user_id: str = DbField(
        db_pk=True,
        title="ID пользователя",
        description="Уникальный ID пользователя в системе",
        json_schema_extra={"readonly": True},
    )

    class Meta:
        is_table: bool = True
        table_name: str = "users"

    name: str = DbField(
        title="Имя",
        description="Отображаемое имя; при сохранении ФИО может выставляться из имени и фамилии",
        max_length=200,
        json_schema_extra={"placeholder": "Иван Иванов"},
    )
    first_name: str | None = Field(
        default=None,
        title="Имя",
        description="Имя для профиля и сопоставления на графе",
        max_length=100,
    )
    last_name: str | None = Field(
        default=None,
        title="Фамилия",
        description="Фамилия для профиля и сопоставления на графе",
        max_length=100,
    )
    status: UserStatus = Field(
        default=UserStatus.ACTIVE,
        title="Статус",
        description="Статус пользователя",
        json_schema_extra={
            "groups": {"admin": {"editable_in_table": True}, "user": {"readonly": True}}
        },
    )
    groups: list[str] = Field(
        default_factory=lambda: ["user"],
        title="Группы",
        description="Группы пользователя (admin, user, bot_editor, guest)",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    companies: dict[str, list[str]] = Field(
        default_factory=dict,
        title="Компании и роли",
        description="company_id -> [role1, role2]",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    active_company_id: str = Field(
        default="",
        title="Активная компания",
        description="ID текущей активной компании",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    emails: list[str] = Field(
        default_factory=list, title="Email адреса", description="Список email адресов пользователя"
    )

    @property
    def email(self) -> str:
        """Первый email для JWT и вызовов, где ожидается одна строка."""
        if not self.emails:
            return ""
        return self.emails[0]

    phones: list[str] = Field(
        default_factory=list, title="Телефоны", description="Список телефонных номеров"
    )
    messengers: dict[str, str] = Field(
        default_factory=dict,
        title="Мессенджеры",
        description="Контакты в мессенджерах: {telegram: @username, whatsapp: +123, slack: U12345}",
    )
    avatar_url: str | None = Field(
        default=None, title="Аватар", description="URL аватара пользователя"
    )
    bio: str | None = Field(
        default=None,
        title="О себе",
        description="Биография пользователя для ИИ и интерфейса",
        max_length=4000,
    )
    ui_preferences: JsonObject = Field(
        default_factory=dict, title="UI настройки", description="Настройки интерфейса пользователя"
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        title="Атрибуты",
        description="Дополнительные service-specific данные",
    )
    password_hash: str | None = Field(
        default=None,
        title="Хеш пароля",
        description="Bcrypt-хеш; используется только для демо-учётки (auth.demo), не для OAuth",
        json_schema_extra={"groups": {"admin": {"hidden": True}, "user": {"hidden": True}}},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создан",
        description="Время создания пользователя",
        json_schema_extra={"readonly": True},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлен",
        description="Время последнего обновления",
        json_schema_extra={"readonly": True},
    )

    @classmethod
    async def find_by_email(cls, email: str) -> User | None:
        matches = await cls.find_all_by_email_ci(email)
        if not matches:
            return None
        return matches[0]

    @classmethod
    async def find_all_by_email_ci(cls, email: str) -> list[User]:
        norm = email.strip().lower()
        if not norm:
            raise ValueError("search email cannot be empty")
        table = cls.get_table_name()
        rows = await execute_raw(
            f"""
            SELECT row_to_json({table}) AS item
            FROM {table}
            WHERE EXISTS (
                SELECT 1 FROM unnest(emails) AS email
                WHERE lower(email) = $1
            )
            ORDER BY user_id
            """,
            [norm],
            using="shared",
        )
        return [_user_from_row(row) for row in rows]

    @classmethod
    async def search_by_query(cls, query: str, limit: int = 20) -> list[User]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        table = cls.get_table_name()
        pattern = _like_contains(query)
        rows = await execute_raw(
            f"""
            SELECT row_to_json({table}) AS item
            FROM {table}
            WHERE name ILIKE $1 ESCAPE '\\'
               OR EXISTS (
                    SELECT 1 FROM unnest(emails) AS email
                    WHERE email ILIKE $1 ESCAPE '\\'
               )
            ORDER BY user_id
            LIMIT $2
            """,
            [pattern, limit],
            using="shared",
        )
        return [_user_from_row(row) for row in rows]

def _like_contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"

def _user_from_row(row: JsonValue) -> User:
    parsed = require_json_object(row, "user")
    raw_item = parsed["item"] if "item" in parsed else parsed
    if isinstance(raw_item, str):
        payload = parse_json_object(raw_item, "user")
    else:
        payload = require_json_object(raw_item, "user")
    return User.model_validate(payload)
