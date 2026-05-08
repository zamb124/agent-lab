/**
 * Форматирование длительности в `MM:SS` / `H:MM:SS`.
 * Канон для всех сервисов (sync, calls, voice, и т.д.).
 */

function _pad2(n) {
    return n < 10 ? `0${n}` : String(n);
}

/**
 * @param {number} seconds — целое неотрицательное; nullable/NaN/<0 — `'00:00'`.
 * @param {{ withHours?: 'auto' | 'always' }} [options]
 * @returns {string}
 */
export function formatDurationSeconds(seconds, options = {}) {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) {
        return '00:00';
    }
    const total = Math.floor(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;

    const withHours = options.withHours === 'always' || (options.withHours !== 'always' && h > 0);
    if (withHours) {
        return `${h}:${_pad2(m)}:${_pad2(s)}`;
    }
    return `${_pad2(m)}:${_pad2(s)}`;
}

/**
 * @param {number} ms
 * @param {{ withHours?: 'auto' | 'always' }} [options]
 * @returns {string}
 */
export function formatDurationMs(ms, options = {}) {
    if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) {
        return '00:00';
    }
    return formatDurationSeconds(Math.floor(ms / 1000), options);
}
