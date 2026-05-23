"""
Снимок данных одного срабатывания триггера в ExecutionState.

Ключ в state.triggers — trigger_id (строка, уникальна в рамках flow).
Сырой вход и нормализованный context не смешиваются с state.variables.
"""

from __future__ import annotations

from pydantic import Field

from core.models import FlexibleBaseModel


class TriggerRuntimeSnapshot(FlexibleBaseModel):
    """
    payload — полный объект входа (Telegram Update, тело webhook, …).
    context — поля, явно вынесенные в output_mapping (левая часть: context.*).
    """

    payload: dict[str, object] = Field(
        ...,
        description="Сырой payload события триггера",
    )
    context: dict[str, object] = Field(
        default_factory=dict,
        description="Нормализованные поля из output_mapping (chat_id, user_id, …)",
    )


__all__ = ["TriggerRuntimeSnapshot"]
