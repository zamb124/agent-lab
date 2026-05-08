/**
 * Стабильное строковое хеширование (FNV-подобный множитель 31).
 *
 * Один источник правды для всех «деривативных» seed'ов: hue аватара,
 * выбор PNG из placeholder-коллекций, цветовой кэш и т.п.
 */

/**
 * @param {string} seed
 * @returns {number} unsigned 32-bit hash
 */
export function hashString31(seed) {
    if (typeof seed !== 'string' || seed.length === 0) {
        return 0;
    }
    let h = 0;
    for (let i = 0; i < seed.length; i += 1) {
        h = (h * 31 + seed.charCodeAt(i)) >>> 0;
    }
    return h;
}

/**
 * Стабильный hue 0..359 для аватара / акцента по seed (user_id, channel id и т.д.).
 * @param {string} seed
 * @returns {number}
 */
export function hueFromString(seed) {
    return hashString31(seed) % 360;
}

/**
 * Инициалы из имени: «Иван Петров» → «ИП», «Иван» → «ИВ», пустое → «?».
 * @param {string} name
 * @returns {string}
 */
export function initialsFromName(name) {
    if (typeof name !== 'string' || name.length === 0) {
        return '?';
    }
    const parts = name.trim().split(/\s+/);
    if (parts.length === 0 || parts[0].length === 0) {
        return '?';
    }
    if (parts.length === 1) {
        return parts[0].slice(0, 2).toUpperCase();
    }
    return (parts[0][0] + parts[1][0]).toUpperCase();
}

/**
 * Стабильный индекс 0..modulo-1 по seed (для PNG-коллекций аватаров).
 * @param {string} seed
 * @param {number} modulo  positive integer
 * @returns {number}
 */
export function indexFromSeed(seed, modulo) {
    if (!Number.isInteger(modulo) || modulo <= 0) {
        throw new Error('indexFromSeed: modulo must be positive integer');
    }
    return hashString31(seed) % modulo;
}
