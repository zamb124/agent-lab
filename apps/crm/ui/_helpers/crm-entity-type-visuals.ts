/**
 * Палитры по строкам справочника `crm/entity_types` (mapItem уже нормализован).
 *
 * @param {unknown} items
 * @returns {Map<string, string>}
 */
export function buildEntityTypeColorMapFromItems(items: unknown): Map<string, string> {
    const colors = new Map<string, string>();
    if (!Array.isArray(items)) {
        return colors;
    }
    for (const item of items) {
        if (!item || typeof item !== 'object') {
            continue;
        }
        const it = item as Record<string, unknown>;
        const typeId = typeof it.type_id === 'string' ? it.type_id.trim() : '';
        if (typeId.length === 0) {
            continue;
        }
        const color = typeof it.color === 'string' ? it.color.trim() : '';
        if (color.length > 0) {
            colors.set(typeId, color);
        }
    }
    return colors;
}

/**
 * @param {unknown} items
 * @returns {Map<string, string>}
 */
export function buildEntityTypeIconMapFromItems(items: unknown): Map<string, string> {
    const icons = new Map<string, string>();
    if (!Array.isArray(items)) {
        return icons;
    }
    for (const item of items) {
        if (!item || typeof item !== 'object') {
            continue;
        }
        const it = item as Record<string, unknown>;
        const typeId = typeof it.type_id === 'string' ? it.type_id.trim() : '';
        if (typeId.length === 0) {
            continue;
        }
        const icon = typeof it.icon === 'string' ? it.icon.trim() : '';
        if (icon.length > 0) {
            icons.set(typeId, icon);
        }
    }
    return icons;
}
