/**
 * Форматирование размера файла в человекочитаемой форме.
 * Один канон для всех сервисов (sync/crm/flows/...).
 *
 * Поведение: B / KB / MB / GB / TB; <1 KB — без дроби; ≥1 KB — 1 десятичный знак.
 */

const UNITS = Object.freeze(['B', 'KB', 'MB', 'GB', 'TB', 'PB']);

/**
 * @param {number} bytes — целое неотрицательное; nullable/NaN — `'—'`.
 * @param {{ precision?: number }} [options]
 * @returns {string}
 */
export function formatFileSize(bytes, options = {}) {
    if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes < 0) {
        return '—';
    }
    if (bytes === 0) {
        return '0 B';
    }
    const precision = typeof options.precision === 'number' && options.precision >= 0
        ? options.precision
        : 1;
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < UNITS.length - 1) {
        size /= 1024;
        unitIndex += 1;
    }
    const formatted = unitIndex === 0
        ? String(Math.round(size))
        : size.toFixed(precision);
    return `${formatted} ${UNITS[unitIndex]}`;
}
