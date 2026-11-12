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
