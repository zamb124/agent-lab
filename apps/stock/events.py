"""
События склада на шине `platform:events`.

Регистрация типов в каталоге платформы (импортируется `apps/stock/main.py`
side-effect'ом). Payload-модели и сборка событий — `apps/stock/models/events.py`:
события складываются в `LaneCommit.events` внутри транзакции команды и
публикуются после commit (`publish_lane_run` быстрый путь, `relay_lane_commits`
— догоняющий). Это нотификация для UI и durable-потребителей, не транспорт
записи леджера.
"""

from __future__ import annotations

from apps.stock.models.events import (
    STOCK_CONTAINER_MOVED,
    STOCK_MOVE_DONE,
    STOCK_MOVE_LINE_ASSIGNED,
    STOCK_MOVE_LINE_EXCEPTION,
    STOCK_QUANT_CHANGED,
    STOCK_TRANSFER_DONE,
    STOCK_VALUATION_CHANGED,
    STOCK_WAVE_RELEASED,
    StockContainerMovedPayload,
    StockMoveDonePayload,
    StockMoveLineAssignedPayload,
    StockMoveLineExceptionPayload,
    StockQuantChangedPayload,
    StockTransferDonePayload,
    StockValuationChangedPayload,
    StockWaveReleasedPayload,
    company_event,
)
from core.events import register_platform_event

register_platform_event(
    STOCK_MOVE_DONE,
    StockMoveDonePayload,
    description="Движение склада завершено (done): quant и слои оценки записаны.",
)
register_platform_event(
    STOCK_TRANSFER_DONE,
    StockTransferDonePayload,
    description="Перевод склада проведён; возможный backorder указан отдельно.",
)
register_platform_event(
    STOCK_QUANT_CHANGED,
    StockQuantChangedPayload,
    description="Проекция остатка изменена (done движения / инвентаризация).",
)
register_platform_event(
    STOCK_CONTAINER_MOVED,
    StockContainerMovedPayload,
    description="Контейнер-локация перемещена под нового родителя.",
)
register_platform_event(
    STOCK_VALUATION_CHANGED,
    StockValuationChangedPayload,
    description="Стоимость продукта изменена корректирующим слоем.",
)
register_platform_event(
    STOCK_MOVE_LINE_ASSIGNED,
    StockMoveLineAssignedPayload,
    description="Складское задание закреплено за оператором/ресурсом.",
)
register_platform_event(
    STOCK_MOVE_LINE_EXCEPTION,
    StockMoveLineExceptionPayload,
    description="Исключение по заданию: недостача/бой, поставлен пересчёт.",
)
register_platform_event(
    STOCK_WAVE_RELEASED,
    StockWaveReleasedPayload,
    description="Волна сборки выпущена в работу.",
)

__all__ = [
    "STOCK_CONTAINER_MOVED",
    "STOCK_MOVE_DONE",
    "STOCK_QUANT_CHANGED",
    "STOCK_TRANSFER_DONE",
    "STOCK_VALUATION_CHANGED",
    "StockContainerMovedPayload",
    "StockMoveDonePayload",
    "StockQuantChangedPayload",
    "StockTransferDonePayload",
    "StockValuationChangedPayload",
    "company_event",
]
