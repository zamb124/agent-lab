/**
 * Эффект storage.
 *
 * Реагирует на STORAGE_PERSIST_REQUESTED и STORAGE_LOAD_REQUESTED, работает с
 * localStorage. Эмитит STORAGE_LOADED при успешной загрузке.
 *
 * Используется для feature-флагов и пользовательских настроек, которые не входят
 * в auth/theme/i18n (у тех собственные effects).
 */

import { CoreEvents } from '../contract.js';

export function createStorageEffect() {
    return async function storageEffect(event, ctx) {
        switch (event.type) {
            case CoreEvents.STORAGE_LOAD_REQUESTED: {
                const key = event.payload && event.payload.key;
                if (typeof key !== 'string' || key.length === 0) {
                    throw new Error('storage.effect: payload.key required');
                }
                const raw = localStorage.getItem(key);
                let value = null;
                if (raw !== null) {
                    try {
                        value = JSON.parse(raw);
                    } catch {
                        value = raw;
                    }
                }
                ctx.dispatch(CoreEvents.STORAGE_LOADED, { key, value }, { causation_id: event.id, source: 'storage' });
                return;
            }
            case CoreEvents.STORAGE_PERSIST_REQUESTED: {
                const key = event.payload && event.payload.key;
                if (typeof key !== 'string' || key.length === 0) {
                    throw new Error('storage.effect: payload.key required');
                }
                const value = event.payload.value;
                if (value === null || value === undefined) {
                    localStorage.removeItem(key);
                } else {
                    const serialized = typeof value === 'string' ? value : JSON.stringify(value);
                    localStorage.setItem(key, serialized);
                }
                return;
            }
            default:
                return;
        }
    };
}
