"""Ошибки домена биллинга."""


class BillingBalanceBlockedError(Exception):
    """Старт тарифицируемой операции запрещён: у компании неположительный баланс."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
