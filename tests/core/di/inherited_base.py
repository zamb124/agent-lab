"""Базы со строковыми аннотациями в отдельном модуле — как ``core.di.platform.PlatformDi``."""

from __future__ import annotations

import dataclasses

from core.di import ServiceDi


class Ledger:
    """Тип поля базы: модуль наследников его не импортирует."""


@dataclasses.dataclass(frozen=True, kw_only=True)
class AuditBase:
    ledger: Ledger


class LedgerDi(ServiceDi):
    ledger: Ledger
