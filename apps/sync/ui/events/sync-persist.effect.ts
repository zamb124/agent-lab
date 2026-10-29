/**
 * Эффект persist Sync — связка локального state с core storage-effect.
 *
 * Подписывается на UI-actions фабрик (selectChannel, sidebarSectionOpen) и
 * диспатчит `STORAGE_PERSIST_REQUESTED`. На bootstrap диспатчит
 * `STORAGE_LOAD_REQUESTED` для каждого ключа и реагирует на `STORAGE_LOADED`
 * соответствующим action для гидратации slice.
 *
 * Sync не персистит и не читает платформенный namespace selection
 * (`crm:last-namespace-by-company` / `state.ui.namespace`) — список чатов
 * без switcher, CRM/Office владеют shared selection сами.
 *
 * Ключи в localStorage:
 *   sync.chat.selectedChannelId       — string | null
 *   sync.ui.sidebarSectionOpen        — { spaces: bool, channels: bool, direct: bool }
 *
 * Не содержит fallback: если ключа нет, action не диспатчится (slice
 * остаётся в initial state).
 */

import { CoreEvents } from '@platform/lib/events/index.js';
import type { EffectCtx, PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

function hasOwnKey<T extends object>(catalog: T, key: string): key is Extract<keyof T, string> {
    return Object.prototype.hasOwnProperty.call(catalog, key);
}

const KEYS = Object.freeze({
    selectedChannelId:      platformStorageKey('sync', 'chat.selected_channel_id'),
    sidebarSectionOpen:     platformStorageKey('sync', 'ui.sidebar_section_open'),
});

const HYDRATION_ACTIONS = Object.freeze({
    [KEYS.selectedChannelId]:      (value: unknown) => ({ type: 'sync/channels/channel_selected', payload: { channelId: value } }),
    [KEYS.sidebarSectionOpen]:     (value: unknown) => {
        if (!value || typeof value !== 'object') return null;
        return { type: 'sync/chat_ui/section_hydrated', payload: { sections: value } };
    },
});

function _extractStringField(event: PlatformEvent, fieldName: string) {
    if (!isPlainRecord(event.payload)) return null;
    const value = event.payload[fieldName];
    return typeof value === 'string' && value !== '' ? value : null;
}

const PERSIST_TRIGGERS = Object.freeze({
    'sync/channels/channel_selected': (event: PlatformEvent, _getState: () => unknown) => ({
        key: KEYS.selectedChannelId,
        value: _extractStringField(event, 'channelId'),
    }),
    'sync/chat_ui/section_toggled': (_event: PlatformEvent, getState: () => unknown) => {
        const state = getState();
        const slice = isPlainRecord(state) ? state.syncChatUi : null;
        const sections = isPlainRecord(slice) ? slice.sidebarSectionOpen : null;
        if (!isPlainRecord(sections)) {
            return { key: KEYS.sidebarSectionOpen, value: {} };
        }
        return { key: KEYS.sidebarSectionOpen, value: { ...sections } };
    },
});

export function createSyncPersistEffect() {
    let bootstrapDispatched = false;

    function dispatchBootstrap(ctx: EffectCtx) {
        if (bootstrapDispatched) return;
        bootstrapDispatched = true;
        for (const key of Object.values(KEYS)) {
            ctx.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key }, { source: 'system' });
        }
    }

    return async function syncPersistEffect(event: PlatformEvent, ctx: EffectCtx) {
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
            if (!isPlainRecord(event.payload)) return;
            const key = event.payload.key;
            const value = event.payload.value;
            if (value === null || value === undefined) return;
            if (typeof key !== 'string' || !hasOwnKey(HYDRATION_ACTIONS, key)) return;
            const factory = HYDRATION_ACTIONS[key];
            if (factory === undefined) return;
            const action = factory(value);
            if (action && typeof action.type === 'string') {
                ctx.dispatch(action.type, action.payload, { source: 'storage' });
            }
            return;
        }

        if (!hasOwnKey(PERSIST_TRIGGERS, event.type)) return;
        const { key, value } = PERSIST_TRIGGERS[event.type](event, ctx.getState);
        ctx.dispatch(CoreEvents.STORAGE_PERSIST_REQUESTED, { key, value }, { source: 'system' });
    };
}
