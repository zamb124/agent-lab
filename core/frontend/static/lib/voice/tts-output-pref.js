/**
 * Глобальное предпочтение: воспроизводить ответ агента через TTS (голосовой WS и кнопка Play).
 * Хранение: localStorage (`platform:voice:tts_output_enabled`), при первом чтении миграция
 * с устаревшего ключа `platform_tts_output_enabled`. Синхронизация между вкладками — `storage`;
 * в той же вкладке — `platform-tts-output-changed`.
 */

import { platformStorageKey } from '../utils/storage-keys.js';

const LEGACY_STORAGE_KEY = 'platform_tts_output_enabled';
const STORAGE_KEY = platformStorageKey('voice', 'tts_output_enabled');

export const TTS_OUTPUT_STORAGE_KEY = STORAGE_KEY;

export const TTS_OUTPUT_CHANGED_EVENT = 'platform-tts-output-changed';

/**
 * @param {string|null} raw
 * @returns {boolean}
 */
function parseStoredTtsFlag(raw) {
    if (raw === null) {
        return true;
    }
    if (raw === '0' || raw === 'false') {
        return false;
    }
    if (raw === '1' || raw === 'true') {
        return true;
    }
    return true;
}

/**
 * @returns {boolean}
 */
export function readTtsOutputEnabled() {
    if (typeof window === 'undefined' || !window.localStorage) {
        return true;
    }
    let raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) {
        const legacy = window.localStorage.getItem(LEGACY_STORAGE_KEY);
        if (legacy !== null) {
            window.localStorage.setItem(STORAGE_KEY, legacy);
            window.localStorage.removeItem(LEGACY_STORAGE_KEY);
            raw = legacy;
        }
    }
    if (raw === null) {
        return true;
    }
    return parseStoredTtsFlag(raw);
}

/**
 * @param {boolean} enabled
 */
export function writeTtsOutputEnabled(enabled) {
    if (typeof window === 'undefined' || !window.localStorage) {
        return;
    }
    if (typeof enabled !== 'boolean') {
        throw new TypeError('writeTtsOutputEnabled: boolean required');
    }
    window.localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0');
    if (window.localStorage.getItem(LEGACY_STORAGE_KEY) !== null) {
        window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    }
    window.dispatchEvent(
        new CustomEvent(TTS_OUTPUT_CHANGED_EVENT, {
            detail: { enabled },
        }),
    );
}

/**
 * @returns {boolean} новое значение
 */
export function toggleTtsOutputEnabled() {
    const next = !readTtsOutputEnabled();
    writeTtsOutputEnabled(next);
    return next;
}
