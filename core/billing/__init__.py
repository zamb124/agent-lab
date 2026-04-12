"""
Сервисы биллинга и учета использования ресурсов.
"""

from typing import Optional

from .exceptions import BillingBalanceBlockedError
from .service import (
    BALANCE_BLOCK_OPERATION_EMBEDDING,
    BALANCE_BLOCK_OPERATION_LIVEKIT_EGRESS,
    BALANCE_BLOCK_OPERATION_LIVEKIT_ROOM,
    BALANCE_BLOCK_OPERATION_LLM,
    BALANCE_BLOCK_OPERATION_VISION,
    BillingService,
)

_billing_service: Optional[BillingService] = None


def set_billing_service(service: BillingService) -> None:
    """
    Устанавливает глобальный BillingService.
    Вызывается при старте сервиса из контейнера.
    """
    global _billing_service
    _billing_service = service


def get_billing_service() -> BillingService:
    """
    Получает глобальный BillingService.
    
    Returns:
        BillingService
        
    Raises:
        RuntimeError: если сервис не инициализирован
    """
    if _billing_service is None:
        raise RuntimeError(
            "BillingService не инициализирован. "
            "Вызовите set_billing_service() при старте сервиса."
        )
    return _billing_service


__all__ = [
    "BALANCE_BLOCK_OPERATION_EMBEDDING",
    "BALANCE_BLOCK_OPERATION_LIVEKIT_EGRESS",
    "BALANCE_BLOCK_OPERATION_LIVEKIT_ROOM",
    "BALANCE_BLOCK_OPERATION_LLM",
    "BALANCE_BLOCK_OPERATION_VISION",
    "BillingBalanceBlockedError",
    "BillingService",
    "get_billing_service",
    "set_billing_service",
]

