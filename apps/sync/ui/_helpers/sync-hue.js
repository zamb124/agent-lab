/**
 * Hash-стабильный hue (0..359) для аватар-инициалов.
 * Чистая функция, идентичный seed → идентичный цвет между сессиями.
 */

export function hueFromString(seed) {
    if (typeof seed !== 'string' || seed === '') return 0;
    let h = 0;
    for (let i = 0; i < seed.length; i += 1) {
        h = (h * 31 + seed.charCodeAt(i)) >>> 0;
    }
    return h % 360;
}

export function initialsFromName(name) {
    if (typeof name !== 'string' || name === '') return '?';
    const parts = name.trim().split(/\s+/);
    if (parts.length === 0) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
}

/** CSS custom property для пастельного аватара (читает токены с :root). */
export function syncAvatarHueVar(seed) {
    return `--sync-avatar-h: ${hueFromString(typeof seed === 'string' ? seed : '')}`;
}
