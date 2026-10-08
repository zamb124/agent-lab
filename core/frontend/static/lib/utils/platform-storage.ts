/**
 * Каноничный синхронный доступ к localStorage платформы.
 *
 * Аргумент — полный ключ из `platformStorageKey(scope, key)` (`platform:<svc>:<key>`).
 * Прямые `localStorage.getItem/setItem/removeItem` вне этого модуля запрещены
 * (rule `localstorage_raw`, `check_ui_kit_canon.py`).
 *
 * Для bus-медиированных фича-флагов существует `storage.effect.js`
 * (`CoreEvents.STORAGE_*`) — эта утилита для синхронных чтений/записей
 * пользовательских предпочтений (layout, view-mode, dismissed).
 */

const _CANON_PREFIX = 'platform:';

function _assertKey(key: string): void {
    if (typeof key !== 'string' || !key.startsWith(_CANON_PREFIX)) {
        throw new Error(
            `platform-storage: key must come from platformStorageKey() (platform:<svc>:<key>); got ${JSON.stringify(key)}`,
        );
    }
}

/** Прочитать строковое значение; null если ключа нет. */
export function storageGet(key: string): string | null {
    _assertKey(key);
    return globalThis.localStorage.getItem(key);
}

/** Записать строковое значение. */
export function storageSet(key: string, value: string): void {
    _assertKey(key);
    globalThis.localStorage.setItem(key, value);
}

/** Удалить ключ. */
export function storageRemove(key: string): void {
    _assertKey(key);
    globalThis.localStorage.removeItem(key);
}

/** Прочитать JSON-значение; null при отсутствии, ошибка при битом JSON. */
export function storageGetJson<T>(key: string): T | null {
    const raw = storageGet(key);
    if (raw === null) {
        return null;
    }
    try {
        return JSON.parse(raw) as T;
    } catch (err) {
        throw new Error(
            `storageGetJson: broken JSON at ${key}: ${(err as Error).message}`,
        );
    }
}

/** Записать JSON-значение. */
export function storageSetJson(key: string, value: unknown): void {
    storageSet(key, JSON.stringify(value));
}
