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
 * Скоупы соответствуют backend whitelist VALID_SCOPES в
 * apps/frontend/api/api_keys.py.
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

export const apiKeysResource = createResourceCollection({
    name: 'frontend/api_keys',
    baseUrl: '/frontend/api/api-keys',
    idField: 'key_id',
    operations: ['list', 'create', 'update', 'remove'],
    toastKeys: {
        create: 'frontend:api_key_modal.toast_created',
        create_error: 'frontend:api_key_modal.err_create_failed',
        update: 'frontend:api_keys_page.toast_renamed',
        remove: 'frontend:api_keys_page.toast_revoked',
    },
    mapItem: (raw) => ({
        key_id: raw.key_id,
        name: raw.name,
        scopes: raw.scopes || [],
        key_prefix: raw.key_prefix || (raw.secret ? raw.secret.slice(0, 12) : ''),
        created_at: raw.created_at || new Date().toISOString(),
        last_used: raw.last_used || null,
    }),
    extraInitial: { lastSecret: null },
    actions: { dismissSecret: 'secret_dismissed' },
    extraReducer: (state, event, events) => {
        if (event.type === events.CREATED) {
            const item = event.payload && event.payload.item;
            if (item && item.secret) {
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
