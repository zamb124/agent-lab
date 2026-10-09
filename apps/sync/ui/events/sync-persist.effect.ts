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
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

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
    if (!event.payload || typeof event.payload !== 'object') return null;
    const value = (event.payload as Record<string, unknown>)[fieldName];
    return typeof value === 'string' && value !== '' ? value : null;
}

const PERSIST_TRIGGERS = Object.freeze({
    'sync/channels/channel_selected': (event: PlatformEvent) => ({ key: KEYS.selectedChannelId,  value: _extractStringField(event, 'channelId') }),
    'sync/chat_ui/section_toggled':   (event: PlatformEvent, getState: () => Record<string, any>) => {
        const slice = getState().syncChatUi;
        if (!slice || !slice.sidebarSectionOpen || typeof slice.sidebarSectionOpen !== 'object') {
            return { key: KEYS.sidebarSectionOpen, value: {} };
        }
        return { key: KEYS.sidebarSectionOpen, value: { ...slice.sidebarSectionOpen } };
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
            if (!event.payload || typeof event.payload !== 'object') return;
            const { key, value } = event.payload as { key?: unknown; value?: unknown };
            if (value === null || value === undefined) return;
            const factory = typeof key === 'string' ? (HYDRATION_ACTIONS as Record<string, (v: unknown) => { type: string; payload: unknown } | null>)[key] : undefined;
            if (typeof factory !== 'function') return;
            const action = factory(value);
            if (action && typeof action.type === 'string') {
                ctx.dispatch(action.type, action.payload, { source: 'storage' });
            }
            return;
        }

        const persistFn = (PERSIST_TRIGGERS as Record<string, (e: PlatformEvent, gs: () => Record<string, any>) => { key: string; value: unknown }>)[event.type];
        if (persistFn) {
            const { key, value } = persistFn(event, ctx.getState as () => Record<string, any>);
            ctx.dispatch(CoreEvents.STORAGE_PERSIST_REQUESTED, { key, value }, { source: 'system' });
        }
    };
}
