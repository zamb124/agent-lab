/**
 * Журнал оценки: метаданные видов операций и форматирование Decimal-полей.
 *
 * Wire-типы несут Decimal как `number | string` — здесь единственное место,
 * где строка превращается в число и форматируется под локаль.
 */

import { formatPlatformCurrencyRub, formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';
import { formatPlatformDate, formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { StockValueLayer, ValueEntryKind } from '@platform/lib/events/wire/stock.gen.js';

export const VALUE_ENTRY_KINDS: readonly ValueEntryKind[] = [
    'inbound',
    'outbound',
    'internal_out',
    'internal_in',
    'inventory_loss',
    'inventory_gain',
    'return',
    'revaluation',
    'correction',
];

const KIND_ICONS: Record<ValueEntryKind, string> = {
    inbound: 'inbox',
    outbound: 'send',
    internal_out: 'swap-horiz',
    internal_in: 'swap',
    inventory_loss: 'minus',
    inventory_gain: 'plus',
    return: 'undo',
    revaluation: 'adjustment',
    correction: 'edit',
};

export function valueEntryKindIcon(kind: ValueEntryKind): string {
    const icon = KIND_ICONS[kind];
    if (typeof icon !== 'string' || icon.length === 0) {
        throw new Error(`valuation: unknown entry kind ${String(kind)}`);
    }
    return icon;
}

/** Направление записи: приход / расход / ручная поправка — для цвета бейджа и суммы. */
export function valueEntryKindTone(kind: ValueEntryKind): 'in' | 'out' | 'adj' {
    switch (kind) {
        case 'inbound':
        case 'internal_in':
        case 'inventory_gain':
        case 'return':
            return 'in';
        case 'outbound':
        case 'internal_out':
        case 'inventory_loss':
            return 'out';
        case 'revaluation':
        case 'correction':
            return 'adj';
    }
}

/** Wire-тип Decimal (`number | string`) → number. Любая другая форма — нарушение контракта транспорта. */
export function parseDecimal(value: unknown): number {
    if (typeof value !== 'number' && typeof value !== 'string') {
        throw new Error(`valuation: invalid decimal ${String(value)}`);
    }
    const parsed = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(parsed)) {
        throw new Error(`valuation: invalid decimal ${String(value)}`);
    }
    return parsed;
}

export function formatQty(value: unknown, locale: string): string {
    return formatPlatformNumber(parseDecimal(value), locale, { maximumFractionDigits: 3 });
}

export function formatMoney(value: unknown, locale: string): string {
    return formatPlatformCurrencyRub(parseDecimal(value), locale);
}

export function formatUnitCost(value: unknown, locale: string): string {
    return formatPlatformCurrencyRub(parseDecimal(value), locale, { maximumFractionDigits: 4 });
}

/** Сумма со знаком для журнала: +1 234,56 ₽ / −1 234,56 ₽. */
export function formatSignedMoney(value: unknown, locale: string): string {
    const amount = parseDecimal(value);
    const formatted = formatPlatformCurrencyRub(Math.abs(amount), locale);
    if (amount > 0) return `+${formatted}`;
    if (amount < 0) return `−${formatted}`;
    return formatted;
}

export function formatSignedQty(value: unknown, locale: string): string {
    const qty = parseDecimal(value);
    const formatted = formatPlatformNumber(Math.abs(qty), locale, { maximumFractionDigits: 3 });
    if (qty > 0) return `+${formatted}`;
    if (qty < 0) return `−${formatted}`;
    return formatted;
}

export function formatLayerDate(value: unknown, locale: string): string {
    return formatPlatformDate(value, locale);
}

export function formatLayerDateTime(value: unknown, locale: string): string {
    return formatPlatformDateTime(value, locale);
}

export interface ValuationLayersResult {
    items: StockValueLayer[];
    total: number;
    product_names: Record<string, string>;
    product_skus: Record<string, string>;
    transfer_names: Record<string, string>;
    warehouse_names: Record<string, string>;
}

const EMPTY_LAYERS_PAGE: ValuationLayersResult = {
    items: [],
    total: 0,
    product_names: {},
    product_skus: {},
    transfer_names: {},
    warehouse_names: {},
};

function _nameMap(value: unknown, field: string): Record<string, string> {
    if (value === undefined) return {};
    if (!isPlainRecord(value)) {
        throw new Error(`valuation: malformed ${field} in layers page`);
    }
    return value as Record<string, string>;
}

/** lastResult op'а списка слоёв → типизированная страница с sidecar-картами имён. Пустой `lastResult` — «ещё не грузили»; кривая форма — `throw`. */
export function readLayersPage(result: unknown): ValuationLayersResult {
    if (result === undefined || result === null) return EMPTY_LAYERS_PAGE;
    if (!isPlainRecord(result) || !Array.isArray(result.items)) {
        throw new Error('valuation: malformed layers page payload');
    }
    const items = result.items.map((item) => {
        if (!isPlainRecord(item)) {
            throw new Error('valuation: malformed layer row in page');
        }
        return item as StockValueLayer;
    });
    if (typeof result.total !== 'number') {
        throw new Error('valuation: malformed total in layers page');
    }
    return {
        items,
        total: result.total,
        product_names: _nameMap(result.product_names, 'product_names'),
        product_skus: _nameMap(result.product_skus, 'product_skus'),
        transfer_names: _nameMap(result.transfer_names, 'transfer_names'),
        warehouse_names: _nameMap(result.warehouse_names, 'warehouse_names'),
    };
}
