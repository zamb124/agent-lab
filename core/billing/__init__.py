"""
Сервисы биллинга и учета использования ресурсов.
"""

from .cbr_rate_provider import (
    get_current_rate as get_cbr_usd_to_rub_rate,
)
from .cbr_rate_provider import (
    refresh_loop_coro as cbr_rate_refresh_loop_coro,
)
from .cbr_rate_provider import (
    refresh_rate_once as refresh_cbr_rate,
)
from .exceptions import BillingBalanceBlockedError
from .service import (
    BALANCE_BLOCK_OPERATION_EMBEDDING,
    BALANCE_BLOCK_OPERATION_GUEST_RUNTIME,
    BALANCE_BLOCK_OPERATION_IMAGE,
    BALANCE_BLOCK_OPERATION_LIVEKIT_EGRESS,
    BALANCE_BLOCK_OPERATION_LIVEKIT_ROOM,
    BALANCE_BLOCK_OPERATION_LLM,
    BALANCE_BLOCK_OPERATION_SEARCH,
    BALANCE_BLOCK_OPERATION_SPEECH,
    BALANCE_BLOCK_OPERATION_VISION,
    BillingService,
)

_billing_service: BillingService | None = None


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

    Возвращает:
        BillingService

    Исключения:
        RuntimeError: если сервис не инициализирован
    """
    if _billing_service is None:
        raise RuntimeError(
            'BillingService is not initialized. Call set_billing_service() at service startup.'
        )
    return _billing_service


__all__ = [
    "BALANCE_BLOCK_OPERATION_EMBEDDING",
    "BALANCE_BLOCK_OPERATION_GUEST_RUNTIME",
    "BALANCE_BLOCK_OPERATION_IMAGE",
    "BALANCE_BLOCK_OPERATION_LIVEKIT_EGRESS",
    "BALANCE_BLOCK_OPERATION_LIVEKIT_ROOM",
    "BALANCE_BLOCK_OPERATION_LLM",
    "BALANCE_BLOCK_OPERATION_SEARCH",
    "BALANCE_BLOCK_OPERATION_SPEECH",
    "BALANCE_BLOCK_OPERATION_VISION",
    "BillingBalanceBlockedError",
    "BillingService",
    "cbr_rate_refresh_loop_coro",
    "get_billing_service",
    "get_cbr_usd_to_rub_rate",
    "refresh_cbr_rate",
    "set_billing_service",
]
