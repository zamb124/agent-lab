/**
 * Sync persist effect — связка локального state с core storage-effect.
 *
 * Подписывается на UI-actions фабрик (selectChannel, sidebarSectionOpen) и
 * диспатчит `STORAGE_PERSIST_REQUESTED`. На bootstrap диспатчит
 * `STORAGE_LOAD_REQUESTED` для каждого ключа и реагирует на `STORAGE_LOADED`
 * соответствующим action для гидратации slice.
 *
 * «Активное пространство Sync» теперь = платформенный namespace
 * (state.ui.namespace.selectionByCompany), который persist'ит сам core
 * ui.effect (`crm:last-namespace-by-company`). В этом эффекте больше нет
 * собственных ключей `selectedSpaceId` / `sidebarSpaceFilterIds` — выбор
 * глобально согласован с CRM/RAG/Office через `setPlatformNamespaceSelection`.
 *
 * Ключи в localStorage:
 *   sync.chat.selectedChannelId       — string | null
 *   sync.ui.sidebarSectionOpen        — { spaces: bool, channels: bool, direct: bool }
 *
 * Не содержит fallback: если ключа нет, action не диспатчится (slice
 * остаётся в initial state).
 */

import { CoreEvents } from '@platform/lib/events/index.js';

const KEYS = Object.freeze({
    selectedChannelId:      'sync.chat.selectedChannelId',
    sidebarSectionOpen:     'sync.ui.sidebarSectionOpen',
});

const HYDRATION_ACTIONS = Object.freeze({
    [KEYS.selectedChannelId]:      (value) => ({ type: 'sync/channels/channel_selected', payload: { channelId: value } }),
    [KEYS.sidebarSectionOpen]:     (value) => {
        if (!value || typeof value !== 'object') return null;
        return { type: 'sync/chat_ui/section_hydrated', payload: { sections: value } };
    },
});

function _extractStringField(event, fieldName) {
    if (!event.payload || typeof event.payload !== 'object') return null;
    const value = event.payload[fieldName];
    return typeof value === 'string' && value !== '' ? value : null;
}

const PERSIST_TRIGGERS = Object.freeze({
    'sync/channels/channel_selected': (event) => ({ key: KEYS.selectedChannelId,  value: _extractStringField(event, 'channelId') }),
    'sync/chat_ui/section_toggled':   (event, getState) => {
        const slice = getState().syncChatUi;
        if (!slice || !slice.sidebarSectionOpen || typeof slice.sidebarSectionOpen !== 'object') {
            return { key: KEYS.sidebarSectionOpen, value: {} };
        }
        return { key: KEYS.sidebarSectionOpen, value: { ...slice.sidebarSectionOpen } };
    },
});

export function createSyncPersistEffect() {
    let bootstrapDispatched = false;

    function dispatchBootstrap(ctx) {
        if (bootstrapDispatched) return;
        bootstrapDispatched = true;
        for (const key of Object.values(KEYS)) {
            ctx.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key }, { source: 'system' });
        }
    }

    return async function syncPersistEffect(event, ctx) {
        if (event.type === CoreEvents.AUTH_USER_LOADED || event.type === CoreEvents.AUTH_LOGIN_SUCCEEDED) {
            dispatchBootstrap(ctx);
            return;
        }

        if (event.type === CoreEvents.AUTH_COMPANY_SWITCHED) {
            ctx.dispatch(
                CoreEvents.STORAGE_PERSIST_REQUESTED,
                { key: KEYS.selectedChannelId, value: null },
                { source: 'system', causation_id: event.id },
            );
            return;
        }

        if (event.type === CoreEvents.STORAGE_LOADED) {
            if (!event.payload || typeof event.payload !== 'object') return;
            const { key, value } = event.payload;
            if (value === null || value === undefined) return;
            const factory = HYDRATION_ACTIONS[key];
            if (typeof factory !== 'function') return;
            const action = factory(value);
            if (action && typeof action.type === 'string') {
                ctx.dispatch(action.type, action.payload, { source: 'storage' });
            }
            return;
        }

        const persistFn = PERSIST_TRIGGERS[event.type];
        if (persistFn) {
            const { key, value } = persistFn(event, ctx.getState);
            ctx.dispatch(CoreEvents.STORAGE_PERSIST_REQUESTED, { key, value }, { source: 'system' });
        }
    };
}
