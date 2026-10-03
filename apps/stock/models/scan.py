"""Скан-движок ТСД — чистая машина состояний потоков склада (без IO).

Это «мозг» терминала сбора данных: каждый скан штрихкода продвигает
контекст по явным состояниям, а в конце выдаёт список исполненных
строк для одной атомарной проводки (``scan_service.commit`` в полосе).

Потоки (``ScanFlow``):

* ``receive`` — приёмка: товар → (ячейка) → количество, строки идут в
  приходную накладную;
* ``move`` — внутреннее перемещение: ячейка-источник → товар →
  ячейка-приёмник → количество;
* ``putaway`` — размещение после приёмки: то же, что ``move``, но
  приёмник по умолчанию берётся из подсказки ``placement_service.suggest``;
* ``pick`` — отбор по заказу: ячейка → товар/партия → количество;
* ``pack`` — упаковка: товар → контейнер-тара (короб на паллету);
* ``ship`` — отгрузка: подтверждение уезда собранных строк к партнёру;
* ``container_move`` — перевозка тары целиком: контейнер → приёмник;
* ``count`` — инвентаризация: ячейка → товар → фактическое количество;
* ``inquiry`` — справка «что за штрихкод» без движения запаса.

Разрешение штрихкода (``ScanResolution``) приходит извне — из
``BarcodeService.resolve``/GS1: продукт, фасовка, партия, серия,
ячейка, контейнер. Машина оперирует только распознанными сущностями
и набранными шагами, поэтому тестируется без БД.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum


class ScanFlow(StrEnum):
    RECEIVE = "receive"
    MOVE = "move"
    PUTAWAY = "putaway"
    PICK = "pick"
    PACK = "pack"
    SHIP = "ship"
    CONTAINER_MOVE = "container_move"
    COUNT = "count"
    INQUIRY = "inquiry"


class ScanStep(StrEnum):
    """Ожидаемый ввод на текущем шаге — «что сканировать дальше»."""

    START = "start"
    LOCATION = "location"
    PRODUCT = "product"
    LOT = "lot"
    QUANTITY = "quantity"
    DEST = "dest"
    CONTAINER = "container"
    REVIEW = "review"
    DONE = "done"


class ScanEntityKind(StrEnum):
    """Какая сущность распознана в штрихкоде."""

    PRODUCT = "product"
    PACKAGING = "packaging"
    LOT = "lot"
    SERIAL = "serial"
    LOCATION = "location"
    CONTAINER = "container"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ScanResolution:
    """Результат распознавания одного штрихкода.

    ``entity_id`` — id сущности (product/location/...), ``entity_kind`` —
    её тип; GS1-поля (`lot_id`, `quantity`, `packaging_id`) подмешиваются,
    когда штрихкод нёс их в себе (SSCC-паллета, GTIN+партия+вес).
    """

    entity_kind: ScanEntityKind
    entity_id: str | None = None
    barcode: str = ""
    product_id: str | None = None
    lot_id: str | None = None
    serial: str | None = None
    quantity: Decimal | None = None
    packaging_id: str | None = None
    packaging_qty: Decimal | None = None


@dataclass(frozen=True)
class ScanLineDraft:
    """Набранная оператором строка исполнения — будущая move_line-правка.

    ``quantity`` — фактическое количество, подтверждённое сканом.
    """

    location_id: str | None
    location_dest_id: str | None
    product_id: str
    quantity: Decimal
    lot_id: str | None = None
    serial: str | None = None
    container_id: str | None = None
    packaging_id: str | None = None


class ScanError(StrEnum):
    """Стабильные коды отказа машины — мапятся в `platform:errors`."""

    UNEXPECTED_STEP = "scan_unexpected_step"
    ENTITY_MISMATCH = "scan_entity_mismatch"
    LOCATION_REQUIRED = "scan_location_required"
    QUANTITY_REQUIRED = "scan_quantity_required"
    SERIAL_REQUIRED = "scan_serial_required"
    NOTHING_TO_COMMIT = "scan_nothing_to_commit"
    NOT_FOUND = "scan_barcode_not_found"


@dataclass(frozen=True)
class ScanStepResult:
    """Исход одного шага машины: новый контекст или отказ."""

    context: ScanContext
    error: ScanError | None = None
    hint: str = ""


@dataclass(frozen=True)
class ScanContext:
    """Состояние скан-сессии оператора — иммутабельно.

    Поля — «заполненные слоты» текущего потока: источник, товар,
    приёмник, количество, тара. ``lines`` — уже набранные строки
    исполнения (многостроковые потоки: приняли паллету из трёх SKU).
    ``step`` — что машина ждёт следующим сканом.
    """

    flow: ScanFlow
    step: ScanStep = ScanStep.START
    source_id: str | None = None
    product_id: str | None = None
    lot_id: str | None = None
    serial: str | None = None
    quantity: Decimal | None = None
    packaging_id: str | None = None
    dest_id: str | None = None
    container_id: str | None = None
    lines: tuple[ScanLineDraft, ...] = ()

    def expected(self) -> ScanStep:
        return self.step


# --- машина состояний --------------------------------------------------------

_FLOW_SEQUENCE: dict[ScanFlow, tuple[ScanStep, ...]] = {
    ScanFlow.RECEIVE: (
        ScanStep.PRODUCT, ScanStep.DEST, ScanStep.QUANTITY, ScanStep.REVIEW,
    ),
    ScanFlow.MOVE: (
        ScanStep.LOCATION, ScanStep.PRODUCT, ScanStep.DEST,
        ScanStep.QUANTITY, ScanStep.REVIEW,
    ),
    ScanFlow.PUTAWAY: (
        ScanStep.PRODUCT, ScanStep.LOCATION, ScanStep.DEST,
        ScanStep.QUANTITY, ScanStep.REVIEW,
    ),
    ScanFlow.PICK: (
        ScanStep.LOCATION, ScanStep.PRODUCT, ScanStep.QUANTITY,
        ScanStep.REVIEW,
    ),
    ScanFlow.PACK: (
        ScanStep.PRODUCT, ScanStep.CONTAINER, ScanStep.QUANTITY,
        ScanStep.REVIEW,
    ),
    ScanFlow.SHIP: (
        ScanStep.LOCATION, ScanStep.REVIEW,
    ),
    ScanFlow.CONTAINER_MOVE: (
        ScanStep.CONTAINER, ScanStep.DEST, ScanStep.REVIEW,
    ),
    ScanFlow.COUNT: (
        ScanStep.LOCATION, ScanStep.PRODUCT, ScanStep.QUANTITY,
        ScanStep.REVIEW,
    ),
    ScanFlow.INQUIRY: (ScanStep.DONE,),
}

_STEP_ENTITIES: dict[ScanStep, frozenset[ScanEntityKind]] = {
    ScanStep.LOCATION: frozenset(
        {ScanEntityKind.LOCATION, ScanEntityKind.CONTAINER}
    ),
    ScanStep.PRODUCT: frozenset(
        {ScanEntityKind.PRODUCT, ScanEntityKind.PACKAGING,
         ScanEntityKind.LOT, ScanEntityKind.SERIAL}
    ),
    ScanStep.DEST: frozenset(
        {ScanEntityKind.LOCATION, ScanEntityKind.CONTAINER}
    ),
    ScanStep.CONTAINER: frozenset({ScanEntityKind.CONTAINER}),
    ScanStep.LOT: frozenset({ScanEntityKind.LOT, ScanEntityKind.SERIAL}),
}
"""Какие типы сущностей принимает каждый шаг ввода."""


def _advance(step: ScanStep, seq: tuple[ScanStep, ...]) -> ScanStep:
    """Следующий ожидаемый шаг в последовательности потока."""
    if step == ScanStep.START:
        return seq[0]
    try:
        idx = seq.index(step)
    except ValueError:
        return step
    return seq[min(idx + 1, len(seq) - 1)]


def _apply_resolution(
    ctx: ScanContext, res: ScanResolution
) -> ScanContext:
    """Положить распознанную сущность в слот текущего шага."""
    match ctx.step:
        case ScanStep.LOCATION:
            return replace(ctx, source_id=res.entity_id)
        case ScanStep.PRODUCT:
            # Партия/серия из GS1 доезжают вместе с товаром; скан
            # партии/серии отдельным кодом тоже наполняет слоты.
            product_id = res.product_id or (
                res.entity_id
                if res.entity_kind == ScanEntityKind.PRODUCT
                else ctx.product_id
            )
            lot_id = res.lot_id or (
                res.entity_id
                if res.entity_kind == ScanEntityKind.LOT
                else None
            )
            serial = res.serial or (
                res.entity_id
                if res.entity_kind == ScanEntityKind.SERIAL
                else None
            )
            return replace(
                ctx,
                product_id=product_id,
                lot_id=lot_id or ctx.lot_id,
                serial=serial or ctx.serial,
                quantity=(
                    res.quantity
                    if res.quantity is not None
                    else (
                        res.packaging_qty
                        if res.packaging_qty is not None
                        else ctx.quantity
                    )
                ),
                packaging_id=res.packaging_id or ctx.packaging_id,
            )
        case ScanStep.DEST:
            return replace(ctx, dest_id=res.entity_id)
        case ScanStep.CONTAINER:
            return replace(ctx, container_id=res.entity_id)
        case ScanStep.LOT:
            return replace(
                ctx,
                lot_id=res.lot_id or res.entity_id,
                serial=res.serial or ctx.serial,
            )
        case _:
            return ctx


def _emit_line(ctx: ScanContext) -> ScanContext:
    """Снять набранные слоты в строку исполнения и очистить их.

    Многостроковые потоки: после ``REVIEW`` оператор может сканировать
    следующий товар — слоты продукта/количества сбрасываются, источник и
    приёмник остаются (переборка внутри одной зоны не переспрашивает
    ячейки).
    """
    # Контейнер — это локация: для pack приёмником строки становится
    # сама тара (товар уезжает «внутрь короба»). Поле container_id в
    # строке не заполняем — на коммите оно означает «перевезти тару
    # целиком», а не «упаковать в неё».
    dest = ctx.dest_id
    if ctx.flow == ScanFlow.PACK and ctx.container_id is not None:
        dest = ctx.container_id
    # _validate_ready выше гарантирует заполненные слоты для всех
    # потоков, которые снимают строку: пустых значений здесь не бывает.
    assert ctx.product_id is not None and ctx.quantity is not None
    line = ScanLineDraft(
        location_id=ctx.source_id,
        location_dest_id=dest,
        product_id=ctx.product_id,
        quantity=ctx.quantity,
        lot_id=ctx.lot_id,
        serial=ctx.serial,
        container_id=None,
        packaging_id=ctx.packaging_id,
    )
    return replace(
        ctx,
        lines=(*ctx.lines, line),
        product_id=None,
        lot_id=None,
        serial=None,
        quantity=None,
        packaging_id=None,
        step=ScanStep.REVIEW,
    )


def _validate_ready(ctx: ScanContext) -> ScanError | None:
    """Проверка «строку можно снять в исполнение» на шаге REVIEW."""
    match ctx.flow:
        case ScanFlow.RECEIVE | ScanFlow.MOVE | ScanFlow.PUTAWAY | ScanFlow.PICK:
            if ctx.product_id is None:
                return ScanError.ENTITY_MISMATCH
            if ctx.dest_id is None and ctx.flow != ScanFlow.PICK:
                return ScanError.LOCATION_REQUIRED
        case ScanFlow.PACK:
            if ctx.product_id is None or ctx.container_id is None:
                return ScanError.ENTITY_MISMATCH
        case ScanFlow.CONTAINER_MOVE:
            if ctx.container_id is None or ctx.dest_id is None:
                return ScanError.LOCATION_REQUIRED
        case ScanFlow.COUNT:
            if ctx.source_id is None or ctx.product_id is None:
                return ScanError.ENTITY_MISMATCH
        case _:
            return None
    if ctx.flow in {
        ScanFlow.RECEIVE, ScanFlow.MOVE, ScanFlow.PUTAWAY,
        ScanFlow.PICK, ScanFlow.PACK, ScanFlow.COUNT,
    } and (ctx.quantity is None or ctx.quantity <= 0):
        return ScanError.QUANTITY_REQUIRED
    return None


def scan_step(ctx: ScanContext, res: ScanResolution) -> ScanStepResult:
    """Один скан: распознанное значение → новый контекст.

    Чистая функция: не трогает БД и не проводит запас — только
    двигает машину. Неожиданный тип сущности для текущего шага
    возвращает ``ScanError.UNEXPECTED_STEP``/``ENTITY_MISMATCH``,
    контекст при этом не меняется (оператор может пересканировать).
    """
    if res.entity_kind == ScanEntityKind.UNKNOWN:
        return ScanStepResult(ctx, ScanError.NOT_FOUND, res.barcode)
    seq = _FLOW_SEQUENCE[ctx.flow]
    if ctx.flow == ScanFlow.INQUIRY:
        # Справочный поток: любой распознанный код — ответ без записи.
        return ScanStepResult(replace(ctx, step=ScanStep.DONE))
    if ctx.step == ScanStep.DONE:
        return ScanStepResult(ctx, ScanError.UNEXPECTED_STEP, "flow_done")
    if ctx.step == ScanStep.START:
        ctx = replace(ctx, step=seq[0])
    if ctx.step == ScanStep.REVIEW:
        # В review принимаем скан следующего товара (новая строка)
        # либо явный commit снаружи (не через scan_step).
        if res.entity_kind in _STEP_ENTITIES[ScanStep.PRODUCT]:
            ctx2 = _apply_resolution(
                replace(ctx, step=ScanStep.PRODUCT), res
            )
            return ScanStepResult(
                replace(ctx2, step=_advance(ScanStep.PRODUCT, seq))
            )
        return ScanStepResult(ctx, ScanError.UNEXPECTED_STEP, "expect_commit")
    allowed = _STEP_ENTITIES.get(ctx.step)
    if allowed is not None and res.entity_kind not in allowed:
        return ScanStepResult(ctx, ScanError.UNEXPECTED_STEP, ctx.step.value)
    if ctx.step == ScanStep.QUANTITY:
        # Количество приходит числом через scan_quantity — скан-шаг
        # в QUANTITY не принимает сущности.
        return ScanStepResult(ctx, ScanError.UNEXPECTED_STEP, "quantity")
    ctx2 = _apply_resolution(ctx, res)
    ctx2 = replace(ctx2, step=_advance(ctx.step, seq))
    if ctx2.step == ScanStep.REVIEW:
        err = _validate_ready(ctx2)
        if err is not None:
            return ScanStepResult(ctx2, err)
        # ship коммитит строки документа, container_move — слоты тары:
        # синтетическая строка не нужна ни там, ни там.
        if ctx.flow not in {ScanFlow.SHIP, ScanFlow.CONTAINER_MOVE}:
            ctx2 = _emit_line(ctx2)
    return ScanStepResult(ctx2)


def scan_quantity(ctx: ScanContext, quantity: Decimal) -> ScanStepResult:
    """Числовой ввод количества (клавиатура ТСД или вес с GS1)."""
    if ctx.step == ScanStep.START:
        ctx = replace(ctx, step=_FLOW_SEQUENCE[ctx.flow][0])
    if ctx.step != ScanStep.QUANTITY:
        return ScanStepResult(ctx, ScanError.UNEXPECTED_STEP, ctx.step.value)
    if quantity <= 0:
        return ScanStepResult(ctx, ScanError.QUANTITY_REQUIRED)
    seq = _FLOW_SEQUENCE[ctx.flow]
    ctx2 = replace(ctx, quantity=quantity, step=_advance(ctx.step, seq))
    if ctx2.step == ScanStep.REVIEW:
        err = _validate_ready(ctx2)
        if err is not None:
            return ScanStepResult(ctx2, err)
        if ctx.flow != ScanFlow.SHIP:
            ctx2 = _emit_line(ctx2)
    return ScanStepResult(ctx2)


def scan_commit_ready(ctx: ScanContext) -> ScanError | None:
    """Можно ли коммитить набранное в одну атомарную проводку.

    ``ship`` коммитит уже собранные строки документа — своих строк
    у него нет. ``container_move`` держит тарe/приёмник в слотах —
    строка строится на коммите. Остальные потоки требуют хотя бы
    одну набранную строку исполнения.
    """
    if ctx.flow == ScanFlow.SHIP:
        return None
    if ctx.flow == ScanFlow.CONTAINER_MOVE:
        if ctx.container_id is None or ctx.dest_id is None:
            return ScanError.NOTHING_TO_COMMIT
        return None
    if not ctx.lines:
        return ScanError.NOTHING_TO_COMMIT
    return None
