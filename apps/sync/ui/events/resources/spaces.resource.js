/**
 * Sync Spaces — пространства Sync.
 *
 * Каждый Sync Space жёстко 1:1 связан с платформенным namespace
 * (shared KV `namespaces`). UI-выбор «активного пространства» хранится в
 * общем срезе `state.ui.namespace.selectionByCompany` (см. CRM-sidebar +
 * `setPlatformNamespaceSelection`); локального `selectedSpaceId` или
 * фильтра-чипов в этом slice больше нет.
 *
 * `transport: 'ws'` — все мутации идут через single platform WS
 * (`/sync/api/ws/notifications`) с автоматическим request-reply ack.
 * REST-зеркало живёт в `apps/sync/api/spaces.py` для CLI/SDK/гостей.
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

function _normalizeSpace(item) {
    if (!item || typeof item !== 'object') return item;
    const namespace = typeof item.namespace === 'string' ? item.namespace : '';
    const description = typeof item.description === 'string' ? item.description : null;
    const avatarUrl = typeof item.avatar_url === 'string' ? item.avatar_url : null;
    return Object.freeze({
        ...item,
        namespace,
        description,
        avatar_url: avatarUrl,
        transcribe_voice_messages: item.transcribe_voice_messages === true,
        speech_to_chat_enabled: item.speech_to_chat_enabled === true,
    });
}

export const spacesResource = createResourceCollection({
    name: 'sync/spaces',
    baseUrl: '/sync/api/v1/spaces',
    idField: 'id',
    operations: ['list', 'create', 'update'],
    transport: 'ws',
    wsTimeoutMs: 5_000,
    // restMirror.update — реальный path FastAPI
    // (`@router.patch("/{space_id}")` в `apps/sync/api/spaces.py`).
    restMirror: {
        update: { method: 'PATCH', path: '/sync/api/v1/spaces/:space_id' },
    },
    toastKeys: {
        create: 'sync:spaces.toast_created',
        create_error: 'sync:spaces.err_create',
        update: 'sync:spaces.toast_updated',
        update_error: 'sync:spaces.err_update',
    },
    mapItem: _normalizeSpace,
    extraReducer: (state, event) => {
        if (event.type === 'sync/space/created') {
            const raw = event.payload;
            if (!raw || typeof raw !== 'object' || typeof raw.id !== 'string') return state;
            if (state.items.some((x) => x.id === raw.id)) return state;
            const item = _normalizeSpace(raw);
            return { ...state, items: Object.freeze([...state.items, item]) };
        }
        return state;
    },
});
