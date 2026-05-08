/**
 * Безопасное экранирование HTML-спецсимволов.
 * Один канон для всех сервисов: используется при ручном построении innerHTML
 * (markdown rendering, log line splitter, search highlight и т.п.).
 *
 * Не использовать как замену Lit-биндингов: внутри `html\`${value}\`` Lit сам экранирует.
 */

/**
 * @param {unknown} value — приводится к строке.
 * @returns {string}
 */
export function escapeHtml(value) {
    if (value === null || value === undefined) {
        return '';
    }
    const str = typeof value === 'string' ? value : String(value);
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
