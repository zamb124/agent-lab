/** Форматирование чисел для экранов терминала. */

/**
 * Количество на экране оператора — без нулей Decimal-шкалы
 * («5.000000» → «5», «12.500000» → «12.5», «0.125» → «0.125»).
 */
export function tsdFormatQty(qty: number | string | null | undefined): string {
    const s = String(qty ?? '0');
    return s.includes('.') ? s.replace(/\.?0+$/, '') : s;
}

/**
 * i18n-ключ виртуальной локации компании (концы движения за границей
 * склада: partner/transit/adjustment). У таких локаций `warehouse_id`
 * пуст — показываем роль, а не служебное имя вида «Partners/customer».
 * `null` — локация физическая, берём её имя как обычно.
 */
export function tsdVirtualLocationKey(
    usage: string | null | undefined,
    partnerRole: string | null | undefined,
): string | null {
    if (usage === 'partner') {
        return partnerRole === 'vendor' ? 'location.partner_vendor' : 'location.partner_customer';
    }
    if (usage === 'transit') return 'location.transit';
    if (usage === 'adjustment') return 'location.adjustment';
    return null;
}

// --- Имена сущностей по коллекциям `stock/locations`/`stock/products` ---
// Общие для home/run экранов lookup'ы: сырой UUID на терминале
// недопустим — не найденное показывается id как есть (честный
// фолбек до подгрузки справочника), виртуальная локация — своей ролью.

import type { StockLocation, StockProductView } from '@platform/lib/events/wire/stock.gen.js';
import { buildPlatformFileDownloadUrl } from '@platform/lib/utils/platform-files-url.js';

type Translate = (key: string) => string;

function _locationLabel(
    location: StockLocation,
    t: Translate,
    short: boolean,
): string {
    const virtual = tsdVirtualLocationKey(location.usage, location.partner_role);
    if (virtual !== null) return t(virtual);
    if (short) return location.name;
    return location.complete_name ?? location.name;
}

/** Полное имя ячейки («Склад/Зона/А-01»); виртуальные — ролью. */
export function tsdLocationName(
    items: readonly StockLocation[],
    locationId: string,
    t: Translate,
): string {
    const location = items.find((row) => row.location_id === locationId);
    return location === undefined ? locationId : _locationLabel(location, t, false);
}

/** Короткое имя («А-01») для маршрута «источник → приёмник». */
export function tsdLocationShortName(
    items: readonly StockLocation[],
    locationId: string,
    t: Translate,
): string {
    const location = items.find((row) => row.location_id === locationId);
    return location === undefined ? locationId : _locationLabel(location, t, true);
}

export function tsdProductName(
    items: readonly StockProductView[],
    productId: string,
): string {
    const product = items.find((row) => row.product_id === productId);
    return product === undefined ? productId : product.name;
}

export function tsdProductImageUrl(
    items: readonly StockProductView[],
    productId: string,
): string | null {
    const product = items.find((row) => row.product_id === productId);
    const fileId = product?.image_file_ids?.[0];
    return typeof fileId === 'string' && fileId !== ''
        ? buildPlatformFileDownloadUrl(fileId)
        : null;
}
