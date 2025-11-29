"""
Кастомные исключения для платформы
"""


class AgentInterrupt(Exception):
    """Исключение для запроса ввода от пользователя"""
    def __init__(self, message: str):
        self.message = message
        self.value = message
        super().__init__(message)


class BillingError(Exception):
    """Ошибка биллинга (лимиты, бюджет)"""
    pass


class TariffError(Exception):
    """Ошибка тарифного плана (ресурс недоступен на тарифе)"""
    pass


__all__ = ['AgentInterrupt', 'BillingError', 'TariffError']

