/**
 * Форматирование JSON для UI (pretty-print, copy buffers, modals).
 * Один канон для всех сервисов.
 */

/**
 * @param {unknown} value
 * @returns {string}
 */
export function formatJsonPretty(value) {
    return JSON.stringify(value, null, 2);
}
