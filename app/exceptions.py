"""
Кастомные исключения для платформы
"""


class BillingError(Exception):
    """Ошибка биллинга (лимиты, бюджет)"""
    pass


class TariffError(Exception):
    """Ошибка тарифного плана (ресурс недоступен на тарифе)"""
    pass


__all__ = ['BillingError', 'TariffError']

