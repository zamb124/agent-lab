/**
 * Глобальное предпочтение: воспроизводить ответ агента через TTS (голосовой WS и кнопка Play).
 * Хранение: localStorage, синхронизация между вкладками через событие.
 */

const STORAGE_KEY = 'platform_tts_output_enabled';

export const TTS_OUTPUT_STORAGE_KEY = STORAGE_KEY;

export const TTS_OUTPUT_CHANGED_EVENT = 'platform-tts-output-changed';

/**
 * @returns {boolean}
 */
export function readTtsOutputEnabled() {
    if (typeof window === 'undefined' || !window.localStorage) {
        return true;
    }
    const raw = window.localStorage.getItem(STORAGE_KEY);
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
