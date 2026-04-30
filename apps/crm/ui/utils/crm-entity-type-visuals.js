/**
 * Палитры по строкам справочника `crm/entity_types` (mapItem уже нормализован).
 *
 * @param {unknown} items
 * @returns {Map<string, string>}
 */
export function buildEntityTypeColorMapFromItems(items) {
    const colors = new Map();
    if (!Array.isArray(items)) {
        return colors;
    }
    for (const item of items) {
        if (!item || typeof item !== 'object') {
            continue;
        }
        const typeId = typeof item.type_id === 'string' ? item.type_id.trim() : '';
        if (typeId.length === 0) {
            continue;
        }
        const color = typeof item.color === 'string' ? item.color.trim() : '';
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
export function buildEntityTypeIconMapFromItems(items) {
    const icons = new Map();
    if (!Array.isArray(items)) {
        return icons;
    }
    for (const item of items) {
        if (!item || typeof item !== 'object') {
            continue;
        }
        const typeId = typeof item.type_id === 'string' ? item.type_id.trim() : '';
        if (typeId.length === 0) {
            continue;
        }
        const icon = typeof item.icon === 'string' ? item.icon.trim() : '';
        if (icon.length > 0) {
            icons.set(typeId, icon);
        }
    }
    return icons;
}
