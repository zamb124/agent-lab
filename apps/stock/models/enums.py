"""Enum'ы домена склада — leaf-модуль без зависимостей.

Импортируется и `domain.py` (поля моделей), и `valuation.py` (чистая
математика) — потому не должен тянуть модели, иначе цикл импорта.
"""

from __future__ import annotations

from enum import StrEnum


class StockLocationUsage(StrEnum):
    VIEW = "view"
    INTERNAL = "internal"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    INVENTORY = "inventory"
    PRODUCTION = "production"
    TRANSIT = "transit"


STOCK_VIRTUAL_LOCATION_KINDS: tuple[StockLocationUsage, ...] = (
    StockLocationUsage.SUPPLIER,
    StockLocationUsage.CUSTOMER,
    StockLocationUsage.INVENTORY,
    StockLocationUsage.PRODUCTION,
    StockLocationUsage.TRANSIT,
)


class StockMoveState(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PARTIALLY_AVAILABLE = "partially_available"
    ASSIGNED = "assigned"
    WAITING = "waiting"
    DONE = "done"
    CANCEL = "cancel"


class StockTransferState(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PARTIALLY_AVAILABLE = "partially_available"
    ASSIGNED = "assigned"
    DONE = "done"
    CANCEL = "cancel"


class StockTracking(StrEnum):
    NONE = "none"
    LOT = "lot"
    SERIAL = "serial"


class StockOperationCode(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    INTERNAL = "internal"


class ReservationPolicy(StrEnum):
    AT_CONFIRM = "at_confirm"
    MANUAL = "manual"
    BY_DATE = "by_date"


class BackorderPolicy(StrEnum):
    ALWAYS = "always"
    NEVER = "never"


class ReflexMode(StrEnum):
    RULE = "rule"
    INLINE = "inline"
    SHADOW = "shadow"


class ReflexPoint(StrEnum):
    PUTAWAY = "putaway"
    REMOVAL = "removal"
    QC_ROUTE = "qc_route"
    RECEIPT_LINES = "receipt_lines"


class StockDecisionStatus(StrEnum):
    SUGGESTED = "suggested"
    APPLIED = "applied"
    REJECTED = "rejected"


class ValuationMethod(StrEnum):
    STANDARD = "standard"
    AVERAGE = "average"
    FIFO = "fifo"
    UNVALUED = "unvalued"


class ValuationPriceSource(StrEnum):
    DOCUMENT = "document"
    STANDARD = "standard"
    AVERAGE = "average"
    MANUAL = "manual"


class ValueEntryKind(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL_OUT = "internal_out"
    INTERNAL_IN = "internal_in"
    INVENTORY_LOSS = "inventory_loss"
    INVENTORY_GAIN = "inventory_gain"
    RETURN = "return"
    REVALUATION = "revaluation"
    CORRECTION = "correction"


class StockBarcodeEntityType(StrEnum):
    PRODUCT = "product"
    LOCATION = "location"
    PACKAGE = "package"
    LOT = "lot"
    TRANSFER = "transfer"
