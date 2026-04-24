"""
Снимок данных одного срабатывания триггера в ExecutionState.

Ключ в state.triggers — trigger_id (строка, уникальна в рамках flow).
Сырой вход и нормализованный context не смешиваются с state.variables.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import Field

from core.models import FlexibleBaseModel


class TriggerRuntimeSnapshot(FlexibleBaseModel):
    """
    payload — полный объект входа (Telegram Update, тело webhook, …).
    context — поля, явно вынесенные в output_mapping (левая часть: context.*).
    """

    payload: Dict[str, Any] = Field(
        ...,
        description="Сырой payload события триггера",
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Нормализованные поля из output_mapping (chat_id, user_id, …)",
    )


__all__ = ["TriggerRuntimeSnapshot"]
