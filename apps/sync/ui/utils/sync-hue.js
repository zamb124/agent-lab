/**
 * Стабильный оттенок для инициалов аватаров по строке id.
 * @param {unknown} value
 * @returns {number}
 */
export function hueFromString(value) {
    const s = typeof value === 'string' ? value : String(value ?? '');
    let h = 0;
    for (let i = 0; i < s.length; i++) {
        h = (h * 31 + s.charCodeAt(i)) >>> 0;
    }
    return h % 360;
}
