"""Каталог системных и контекстных переменных (read-only, не хранятся в secrets).

Используется UI autocomplete и help-панелями вместо flows variables API.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from core.models import StrictBaseModel


class SystemVariableCategory(StrEnum):
    RUNTIME_DATETIME = "runtime_datetime"
    IDENTITY = "identity"
    CONTEXT = "context"


class SystemVariableCatalogEntry(StrictBaseModel):
    variable_key: str
    category: SystemVariableCategory
    description_ru: str
    description_en: str
    resolvable_at_runtime: bool = Field(
        default=True,
        description="True — подставляется движком при запуске flow без записи в secrets",
    )


SYSTEM_VARIABLE_CATALOG: tuple[SystemVariableCatalogEntry, ...] = (
    SystemVariableCatalogEntry(
        variable_key="current_date",
        category=SystemVariableCategory.RUNTIME_DATETIME,
        description_ru="Текущая дата (YYYY-MM-DD) на момент запуска",
        description_en="Current date (YYYY-MM-DD) at run time",
    ),
    SystemVariableCatalogEntry(
        variable_key="current_time",
        category=SystemVariableCategory.RUNTIME_DATETIME,
        description_ru="Текущее время (HH:MM) на момент запуска",
        description_en="Current time (HH:MM) at run time",
    ),
    SystemVariableCatalogEntry(
        variable_key="current_datetime",
        category=SystemVariableCategory.RUNTIME_DATETIME,
        description_ru="Текущие дата и время на момент запуска",
        description_en="Current date and time at run time",
    ),
    SystemVariableCatalogEntry(
        variable_key="current_year",
        category=SystemVariableCategory.RUNTIME_DATETIME,
        description_ru="Текущий год",
        description_en="Current calendar year",
    ),
    SystemVariableCatalogEntry(
        variable_key="current_month",
        category=SystemVariableCategory.RUNTIME_DATETIME,
        description_ru="Текущий месяц (1–12)",
        description_en="Current month (1–12)",
    ),
    SystemVariableCatalogEntry(
        variable_key="current_day",
        category=SystemVariableCategory.RUNTIME_DATETIME,
        description_ru="Текущий день месяца",
        description_en="Current day of month",
    ),
    SystemVariableCatalogEntry(
        variable_key="user_id",
        category=SystemVariableCategory.IDENTITY,
        description_ru="ID пользователя-исполнителя",
        description_en="Executor user ID",
    ),
    SystemVariableCatalogEntry(
        variable_key="user_name",
        category=SystemVariableCategory.IDENTITY,
        description_ru="Имя пользователя-исполнителя",
        description_en="Executor display name",
    ),
    SystemVariableCatalogEntry(
        variable_key="user_email",
        category=SystemVariableCategory.IDENTITY,
        description_ru="Email пользователя из контекста сессии",
        description_en="User email from session context",
    ),
    SystemVariableCatalogEntry(
        variable_key="user_first_name",
        category=SystemVariableCategory.IDENTITY,
        description_ru="Имя пользователя (first name)",
        description_en="User first name",
    ),
    SystemVariableCatalogEntry(
        variable_key="user_last_name",
        category=SystemVariableCategory.IDENTITY,
        description_ru="Фамилия пользователя (last name)",
        description_en="User last name",
    ),
    SystemVariableCatalogEntry(
        variable_key="company_id",
        category=SystemVariableCategory.CONTEXT,
        description_ru="ID активной компании",
        description_en="Active company ID",
    ),
    SystemVariableCatalogEntry(
        variable_key="company_name",
        category=SystemVariableCategory.CONTEXT,
        description_ru="Название активной компании",
        description_en="Active company name",
    ),
    SystemVariableCatalogEntry(
        variable_key="active_namespace",
        category=SystemVariableCategory.CONTEXT,
        description_ru="Активный namespace исполнения",
        description_en="Active execution namespace",
    ),
    SystemVariableCatalogEntry(
        variable_key="user_language",
        category=SystemVariableCategory.CONTEXT,
        description_ru="Язык пользователя из контекста",
        description_en="User language from context",
    ),
    SystemVariableCatalogEntry(
        variable_key="interface_language_code",
        category=SystemVariableCategory.CONTEXT,
        description_ru="Код языка интерфейса",
        description_en="UI language code",
    ),
    SystemVariableCatalogEntry(
        variable_key="interface_language_name",
        category=SystemVariableCategory.CONTEXT,
        description_ru="Название языка интерфейса",
        description_en="UI language display name",
    ),
)

SYSTEM_VARIABLE_KEYS: frozenset[str] = frozenset(
    entry.variable_key for entry in SYSTEM_VARIABLE_CATALOG
)


def catalog_entry(variable_key: str) -> SystemVariableCatalogEntry | None:
    for entry in SYSTEM_VARIABLE_CATALOG:
        if entry.variable_key == variable_key:
            return entry
    return None


__all__ = [
    "SYSTEM_VARIABLE_CATALOG",
    "SYSTEM_VARIABLE_KEYS",
    "SystemVariableCatalogEntry",
    "SystemVariableCategory",
    "catalog_entry",
]
