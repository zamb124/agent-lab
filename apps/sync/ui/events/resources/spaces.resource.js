/**
 * Sync Spaces — пространства Sync.
 *
 * `transport: 'ws'` — все мутации идут через single platform WS
 * (`/sync/api/ws/notifications`) с автоматическим request-reply ack.
 * REST-зеркало живёт в `apps/sync/api/spaces.py` для CLI/SDK/гостей.
 *
 * Slice расширен UI-state: `selectedSpaceId` (текущий выбор) и
 * `sidebarSpaceFilterIds` (multi-select фильтр в sidebar; пустой массив =
 * все topic-каналы). Persist через core storage-effect (см. PR3).
 */

import { createResourceCollection } from '@platform/lib/events/index.js';
import { resolveSpaceId } from '../../_helpers/sync-id-resolvers.js';

export const spacesResource = createResourceCollection({
    name: 'sync/spaces',
    baseUrl: '/sync/api/v1/spaces',
    idField: 'space_id',
    operations: ['list', 'create', 'update'],
    transport: 'ws',
    wsTimeoutMs: 5_000,
    toastKeys: {
        create: 'sync:spaces.toast_created',
        create_error: 'sync:spaces.err_create',
        update: 'sync:spaces.toast_updated',
        update_error: 'sync:spaces.err_update',
    },
    extraInitial: {
        selectedSpaceId: null,
        sidebarSpaceFilterIds: Object.freeze([]),
    },
    extraEvents: {
        SELECTED: 'space_selected',
        FILTER_TOGGLED: 'filter_toggled',
        FILTER_RESET: 'filter_reset',
    },
    actions: {
        selectSpace: 'space_selected',
        toggleFilter: 'filter_toggled',
        resetFilter: 'filter_reset',
    },
    extraReducer: (state, event) => {
        if (event.type === 'sync/space/created') {
            const item = event.payload;
            if (!item || typeof item !== 'object') return state;
            const id = resolveSpaceId(item);
            if (id === '') return state;
            const existing = state.items.findIndex((x) => resolveSpaceId(x) === id);
            const items = existing === -1 ? [...state.items, item] : state.items;
            return { ...state, items: Object.freeze(items) };
        }
        if (event.type === 'sync/spaces/space_selected') {
            const p = event.payload;
            const spaceId = p && typeof p.spaceId === 'string' ? p.spaceId : null;
            return { ...state, selectedSpaceId: spaceId };
        }
        if (event.type === 'sync/spaces/filter_toggled') {
            const p = event.payload;
            if (!p || typeof p.spaceId !== 'string') return state;
            const cur = state.sidebarSpaceFilterIds;
            const next = cur.includes(p.spaceId)
                ? cur.filter((x) => x !== p.spaceId)
                : [...cur, p.spaceId];
            return { ...state, sidebarSpaceFilterIds: Object.freeze(next) };
        }
        if (event.type === 'sync/spaces/filter_reset') {
            return { ...state, sidebarSpaceFilterIds: Object.freeze([]) };
        }
        return state;
    },
});
