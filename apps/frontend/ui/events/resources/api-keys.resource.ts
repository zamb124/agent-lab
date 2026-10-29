/**
 * Ресурс api_keys — единственное определение домена API-ключей.
 *
 * Здесь живут события, slice, эффект и селекторы для управления ключами.
 * Никаких ручных reducer-case или httpRequest в effect-файлах: вся логика
 * декларативна.
 *
 * Особенность: при создании ключа BE возвращает одноразовый `secret`. Он не
 * хранится в обычном items[], а кладётся в `lastSecret` через extraReducer,
 * чтобы страница смогла показать баннер до явного `secret_dismissed`.
 *
 * Команды `frontend/api_keys/{list,create,update,remove}_requested`
 * (REST-зеркало `apps/frontend/api/api_keys.py`); скоупы — backend whitelist VALID_SCOPES.
 */

import { createResourceCollection } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

export const apiKeysResource = createResourceCollection({
    name: 'frontend/api_keys',
    baseUrl: '/frontend/api/api-keys',
    idField: 'key_id',
    operations: ['list', 'create', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({ limit: 200, offset: 0 }),
    toastKeys: {
        create: 'frontend:api_key_modal.toast_created',
        create_error: 'frontend:api_key_modal.err_create_failed',
        update: 'frontend:api_keys_page.toast_renamed',
        remove: 'frontend:api_keys_page.toast_revoked',
    },
    mapItem: (raw) => {
        if (typeof raw.key_id !== 'string') {
            throw new Error('frontend/api_keys.mapItem: key_id required');
        }
        return {
            key_id: raw.key_id,
            name: typeof raw.name === 'string' ? raw.name : '',
            scopes: Array.isArray(raw.scopes) ? raw.scopes : [],
            key_prefix: typeof raw.key_prefix === 'string' && raw.key_prefix.length > 0
                ? raw.key_prefix
                : (typeof raw.secret === 'string' ? raw.secret.slice(0, 12) : ''),
            created_at: typeof raw.created_at === 'string' ? raw.created_at : new Date().toISOString(),
            last_used: typeof raw.last_used === 'string' ? raw.last_used : null,
        };
    },
    extraInitial: { lastSecret: null },
    actions: { dismissSecret: 'secret_dismissed' },
    extraReducer: (state, event, events) => {
        if (event.type === events.CREATED) {
            const payload = event.payload;
            const item = isPlainRecord(payload) ? payload.item : null;
            if (isPlainRecord(item) && item.secret) {
                return { ...state, lastSecret: { key_id: item.key_id, secret: item.secret } };
            }
            return state;
        }
        if (event.type === events.SECRET_DISMISSED) {
            return { ...state, lastSecret: null };
        }
        return state;
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'frontend/api_keys': typeof apiKeysResource;
    }
}
