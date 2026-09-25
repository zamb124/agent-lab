"""Наследники ``inherited_base`` в модуле, который не импортирует ``Ledger`` — как ``apps/flows/di.py``."""

import dataclasses
from collections.abc import AsyncIterator

from core.di import recipe
from tests.core.di.inherited_base import AuditBase, LedgerDi


@dataclasses.dataclass(frozen=True, kw_only=True)
class Audit(AuditBase):
    retries: int = 3


class AuditDi(LedgerDi):
    audit: Audit


@recipe
async def watch_ledger(di: AuditDi) -> AsyncIterator[None]:
    _ = di
    yield
