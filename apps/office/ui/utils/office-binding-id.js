/**
 * Ид привязки в сегменте URL после /documents/edit/ — один логический токен без слэшей.
 * Относительные переходы (например от iframe OnlyOffice) иначе дают путь вида .../edit/common/index.html
 * и ломают маршрутизацию и fetch (в пути %2F часто превращается в /).
 */

/**
 * @param {string} raw
 * @returns {boolean}
 */
export function isPlausibleOfficeBindingId(raw) {
    if (typeof raw !== 'string') {
        return false;
    }
    const s = raw.trim();
    if (!s || s.length > 200) {
        return false;
    }
    if (s.includes('/') || s.includes('\\') || s.includes('..')) {
        return false;
    }
    if (/\.html?$/i.test(s)) {
        return false;
    }
    return true;
}
