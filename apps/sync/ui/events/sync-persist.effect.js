/**
 * Sync persist effect — связка локального state с core storage-effect.
 *
 * Подписывается на UI-actions фабрик (selectSpace/selectChannel/toggleFilter)
 * и диспатчит `STORAGE_PERSIST_REQUESTED`. На bootstrap диспатчит
 * `STORAGE_LOAD_REQUESTED` для каждого ключа и реагирует на `STORAGE_LOADED`
 * соответствующим action для гидратации slice.
 *
 * Ключи в localStorage:
 *   sync.chat.selectedSpaceId         — string | null
 *   sync.chat.selectedChannelId       — string | null
 *   sync.ui.sidebarSpaceFilterIds     — string[]
 *
 * Не содержит fallback: если ключа нет, action не диспатчится (slice
 * остаётся в initial state).
 */

import { CoreEvents } from '@platform/lib/events/index.js';

const KEYS = Object.freeze({
    selectedSpaceId:        'sync.chat.selectedSpaceId',
    selectedChannelId:      'sync.chat.selectedChannelId',
    sidebarSpaceFilterIds:  'sync.ui.sidebarSpaceFilterIds',
});

const HYDRATION_ACTIONS = Object.freeze({
    [KEYS.selectedSpaceId]:        (value) => ({ type: 'sync/spaces/space_selected',   payload: { spaceId: value } }),
    [KEYS.selectedChannelId]:      (value) => ({ type: 'sync/channels/channel_selected', payload: { channelId: value } }),
    [KEYS.sidebarSpaceFilterIds]:  (value) => null,
});

function _extractStringField(event, fieldName) {
    if (!event.payload || typeof event.payload !== 'object') return null;
    const value = event.payload[fieldName];
    return typeof value === 'string' && value !== '' ? value : null;
}

const PERSIST_TRIGGERS = Object.freeze({
    'sync/spaces/space_selected':     (event) => ({ key: KEYS.selectedSpaceId,    value: _extractStringField(event, 'spaceId') }),
    'sync/channels/channel_selected': (event) => ({ key: KEYS.selectedChannelId,  value: _extractStringField(event, 'channelId') }),
    'sync/spaces/filter_toggled':     (event, getState) => {
        const slice = getState().syncSpaces;
        const ids = (slice && Array.isArray(slice.sidebarSpaceFilterIds)) ? slice.sidebarSpaceFilterIds : [];
        return { key: KEYS.sidebarSpaceFilterIds, value: Array.from(ids) };
    },
    'sync/spaces/filter_reset':       () => ({ key: KEYS.sidebarSpaceFilterIds,   value: [] }),
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

    function hydrateSidebarFilter(value, ctx) {
        if (!Array.isArray(value)) return;
        for (const spaceId of value) {
            if (typeof spaceId === 'string' && spaceId !== '') {
                ctx.dispatch('sync/spaces/filter_toggled', { spaceId }, { source: 'storage' });
            }
        }
    }

    return async function syncPersistEffect(event, ctx) {
        if (event.type === CoreEvents.AUTH_USER_LOADED || event.type === CoreEvents.AUTH_LOGIN_SUCCEEDED) {
            dispatchBootstrap(ctx);
            return;
        }

        if (event.type === CoreEvents.STORAGE_LOADED) {
            if (!event.payload || typeof event.payload !== 'object') return;
            const { key, value } = event.payload;
            if (value === null || value === undefined) return;
            if (key === KEYS.sidebarSpaceFilterIds) {
                hydrateSidebarFilter(value, ctx);
                return;
            }
            const factory = HYDRATION_ACTIONS[key];
            if (typeof factory !== 'function') return;
            const action = factory(value);
            if (action) {
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
