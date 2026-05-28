/**
 * Общая цветовая палитра для типов сущностей, календарных событий и нод графа.
 *
 * У каждой записи есть семантический `key` и hex-значение `dot`.
 * Типы бэкенда сущностей хранят `color` как одно из этих hex-значений.
 * UI-компоненты берут цвета нод/chip-ов из этой палитры.
 */

export const COLOR_PALETTE = [
    { key: 'default', dot: '#a2affb' },
    { key: 'mint', dot: '#34c38f' },
    { key: 'sky', dot: '#4ea8ff' },
    { key: 'violet', dot: '#8f7bff' },
    { key: 'amber', dot: '#f5b14c' },
    { key: 'rose', dot: '#ef6f98' },
    { key: 'gray', dot: '#8f96a3' },
    { key: 'slate', dot: '#607D8B' },
    { key: 'orange', dot: '#FF9800' },
    { key: 'red', dot: '#D32F2F' },
    { key: 'blue', dot: '#1976D2' },
    { key: 'purple', dot: '#7E57C2' },
    { key: 'teal', dot: '#00897B' },
    { key: 'deeporange', dot: '#EF6C00' },
];

export function isKnownPaletteColor(hexOrKey) {
    if (!hexOrKey || typeof hexOrKey !== 'string') {
        return false;
    }
    const normalized = hexOrKey.trim().toLowerCase();
    return COLOR_PALETTE.some(
        (entry) => entry.key === normalized || entry.dot.toLowerCase() === normalized,
    );
}

export function resolvePaletteColor(hexOrKey) {
    if (!hexOrKey || typeof hexOrKey !== 'string') {
        throw new Error('Color value is required');
    }
    const normalized = hexOrKey.trim().toLowerCase();
    const byKey = COLOR_PALETTE.find((entry) => entry.key === normalized);
    if (byKey) {
        return byKey.dot;
    }
    const byDot = COLOR_PALETTE.find((entry) => entry.dot.toLowerCase() === normalized);
    if (byDot) {
        return byDot.dot;
    }
    if (/^#[0-9a-f]{6}$/i.test(hexOrKey.trim())) {
        return hexOrKey.trim();
    }
    throw new Error(`Unknown palette color: ${hexOrKey}`);
}
