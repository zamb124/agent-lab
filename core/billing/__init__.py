"""
Сервисы биллинга и учета использования ресурсов.
"""

from .service import BillingService
from core.context import get_context


def get_billing_service() -> BillingService:
    """
    Получает BillingService из контекста.
    
    Returns:
        BillingService из context.container
        
    Raises:
        RuntimeError: если контекст или контейнер недоступны
    """
    context = get_context()
    if not context:
        raise RuntimeError("Контекст недоступен для получения BillingService")
    if not context.container:
        raise RuntimeError("Контейнер недоступен в контексте")
    if not hasattr(context.container, 'billing_service'):
        raise RuntimeError("BillingService не найден в контейнере")
    return context.container.billing_service


__all__ = ["BillingService", "get_billing_service"]

