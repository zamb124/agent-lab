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
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { payloadFields, stringField } from '../payload.js';

/**
 * Строка пишется как есть, объект — JSON. На чтении JSON-литерал разбирается,
 * обычный текст остаётся строкой. Текст, похожий на JSON, но битый, — ошибка.
 */
function storageValue(raw: string): unknown {
    const trimmed = raw.trim();
    const jsonLiteral = trimmed === 'true'
        || trimmed === 'false'
        || trimmed === 'null'
        || trimmed.startsWith('{')
        || trimmed.startsWith('[')
        || trimmed.startsWith('"')
        || /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(trimmed);
    if (!jsonLiteral) {
        return raw;
    }
    return JSON.parse(raw);
}

export function createStorageEffect(): (event: PlatformEvent, ctx: EffectCtx) => Promise<void> {
    return async function storageEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        switch (event.type) {
            case CoreEvents.STORAGE_LOAD_REQUESTED: {
                const key = stringField(payloadFields(event).key);
                if (typeof key !== 'string' || key.length === 0) {
                    throw new Error('storage.effect: payload.key required');
                }
                const raw = localStorage.getItem(key);
                const value = raw === null ? null : storageValue(raw);
                ctx.dispatch(CoreEvents.STORAGE_LOADED, { key, value }, { causation_id: event.id, source: 'storage' });
                return;
            }
            case CoreEvents.STORAGE_PERSIST_REQUESTED: {
                const p = payloadFields(event);
                const key = p.key;
                if (typeof key !== 'string' || key.length === 0) {
                    throw new Error('storage.effect: payload.key required');
                }
                const value = p.value;
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
