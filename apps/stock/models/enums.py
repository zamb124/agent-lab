"""Enum'ы домена склада — leaf-модуль без зависимостей.

Импортируется модулями таблиц и `valuation.py` (чистая
математика) — потому не должен тянуть модели, иначе цикл импорта.
"""

from __future__ import annotations

from enum import StrEnum


class StockLocationUsage(StrEnum):
    """Таксономия локаций целевой топологии.

    `view` — склад/зона/ряд/стеллаж (остаток не хранит); `bin` — ячейка;
    `container` — паллета/короб/пакет/тоут/тележка (хранит и перемещается);
    `partner` — поставщик/клиент (`partner_role` уточняет); `transit` —
    собственный товар в пути (оценивается); `adjustment` —
    инвентаризация и списание.
    """

    VIEW = "view"
    BIN = "bin"
    CONTAINER = "container"
    PARTNER = "partner"
    TRANSIT = "transit"
    ADJUSTMENT = "adjustment"


class StockPartnerRole(StrEnum):
    """Роль partner-локации: поставщик или клиент."""

    VENDOR = "vendor"
    CUSTOMER = "customer"


STOCK_VIRTUAL_LOCATION_KINDS: tuple[
    tuple[StockLocationUsage, StockPartnerRole | None], ...
] = (
    (StockLocationUsage.PARTNER, StockPartnerRole.VENDOR),
    (StockLocationUsage.PARTNER, StockPartnerRole.CUSTOMER),
    (StockLocationUsage.ADJUSTMENT, None),
    (StockLocationUsage.TRANSIT, None),
)

STOCK_QUANT_USAGES: frozenset[StockLocationUsage] = frozenset(
    {
        StockLocationUsage.BIN,
        StockLocationUsage.CONTAINER,
        StockLocationUsage.TRANSIT,
    }
)
"""Usage, на которых живёт `StockQuant` (оцениваемые при `owner IS NULL`)."""

STOCK_EXTERNAL_USAGES: frozenset[StockLocationUsage] = frozenset(
    {
        StockLocationUsage.PARTNER,
        StockLocationUsage.ADJUSTMENT,
    }
)
"""Внешние концы движения: товар появляется/исчезает без quant-проводки.

`partner` — поставщик/клиент, `adjustment` — инвентаризационный сурплюс.
`view` сюда не входит: зона — это корень поддерева ячеек, движение
из/в view резолвится в конкретные quant-локации поддерева."""


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


class StockMoveLineKind(StrEnum):
    """Вид складского задания (WT): количество, контейнер целиком, пересчёт."""

    QUANTITY = "quantity"
    CONTAINER = "container"
    COUNT = "count"


class StockMoveLineState(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class StockWaveState(StrEnum):
    """Жизненный цикл волны сборки — сменного задания бригады."""

    DRAFT = "draft"
    RELEASED = "released"
    DONE = "done"
    CANCELLED = "cancelled"


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


class BackorderPolicy(StrEnum):
    ALWAYS = "always"
    NEVER = "never"
    ASK = "ask"


class StockContainerKind(StrEnum):
    PALLET = "pallet"
    BOX = "box"
    BAG = "bag"
    TOTE = "tote"
    CART = "cart"
    OTHER = "other"


class StockContainerPolicy(StrEnum):
    """Политика типа хранения по упаковке содержимого."""

    LOOSE_ONLY = "loose_only"
    ANY = "any"
    CONTAINER_ONLY = "container_only"


class StockProductMixing(StrEnum):
    """Смешивание содержимого в ячейке типа хранения."""

    MIXED = "mixed"
    SAME_PRODUCT = "same_product"
    EMPTY_ONLY = "empty_only"


class StockRemovalStrategy(StrEnum):
    FIFO = "fifo"
    FEFO = "fefo"
    LIFO = "lifo"
    LEAST_CONTAINERS = "least_containers"
    CLOSEST = "closest"


class StockPutawayStrategy(StrEnum):
    """Шаг цепочки стратегий размещения типа хранения (SAP-стиль).

    ``manual`` — «оператор выбирает сам»: подсказки нет, но цепочка
    явно объявлена (тип хранения всегда знает свою стратегию).
    """

    EXISTING_STOCK = "existing_stock"
    EMPTY_BIN = "empty_bin"
    NEAREST = "nearest"
    MANUAL = "manual"


class StockLayoutPreset(StrEnum):
    """Пресет топологии склада: даркстор → стандартный → РЦ."""

    SIMPLE = "simple"
    STANDARD = "standard"
    DISTRIBUTION_CENTER = "distribution_center"


class ReflexMode(StrEnum):
    RULE = "rule"
    INLINE = "inline"
    SHADOW = "shadow"


class ReflexPoint(StrEnum):
    """Точка, где движок спрашивает внешнее решение (reflex).

    Пока одна — ``putaway``: «куда положить принятое». Новые точки
    добавляются только вместе с исполнителем, который их вызывает.
    """

    PUTAWAY = "putaway"


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
    PACKAGING = "packaging"
    LOCATION = "location"
    CONTAINER = "container"
    LOT = "lot"
    TRANSFER = "transfer"
    RESOURCE = "resource"
