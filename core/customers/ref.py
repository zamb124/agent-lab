"""`CustomerRef` — лёгкая ссылка на покупателя для `Context`.

Отдельный модуль без импортов платформы: `core.models.context_models`
тянет его раньше `core.models` barrel — цикл запрещён слоями.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class CustomerRef(BaseModel):
    """Лёгкая ссылка на покупателя в `Context` — без загрузки строки."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    customer_id: str
    phone_e164: str
    scope_company_id: str
    # Витрины, где покупатель реально проходил верификацию; пусто →
    # трактуется как одиночный `scope_company_id` (токены старого формата).
    scope_company_ids: tuple[str, ...] = ()
