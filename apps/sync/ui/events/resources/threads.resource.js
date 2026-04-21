/**
 * Sync Threads — треды канала.
 *
 * REST-зеркало: `apps/sync/api/threads.py`. WS-команда `sync/threads/create_requested`
 * → handler `threads.create`.
 *
 * Slice добавляет UI-state `selectedThreadId` (открытый thread-drawer) и
 * `byChannelId` (сводка тредов по каналу).
 *
 * UI-actions: openThread(threadId), closeThread().
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

export const threadsResource = createResourceCollection({
    name: 'sync/threads',
    baseUrl: '/sync/api/v1/threads',
    idField: 'thread_id',
    operations: ['list', 'get', 'create'],
    transport: 'ws',
    wsTimeoutMs: 5_000,
    toastKeys: {
        create: 'sync:threads.toast_created',
        create_error: 'sync:threads.err_create',
    },
    listQuery: ({ channel_id }) => ({ channel_id }),
    extraInitial: {
        selectedThreadId: null,
        byChannelId: Object.freeze({}),
    },
    extraEvents: {
        OPEN_REQUESTED: 'open_requested',
        CLOSED: 'drawer_closed',
    },
    actions: {
        openThread: 'open_requested',
        closeThread: 'drawer_closed',
    },
    extraReducer: (state, event) => {
        switch (event.type) {
            case 'sync/context/company_cleared': {
                return {
                    ...state,
                    items: Object.freeze([]),
                    byId: Object.freeze({}),
                    loading: false,
                    error: null,
                    busyIds: Object.freeze({}),
                    lastError: Object.freeze({}),
                    selectedThreadId: null,
                    byChannelId: Object.freeze({}),
                };
            }
            case 'sync/thread/created': {
                const item = event.payload;
                if (!item || typeof item.thread_id !== 'string') return state;
                if (state.items.some((x) => x.thread_id === item.thread_id)) return state;
                const next = { ...state, items: Object.freeze([...state.items, item]) };
                if (typeof item.channel_id === 'string') {
                    const existing = state.byChannelId[item.channel_id];
                    const cur = Array.isArray(existing) ? existing : [];
                    next.byChannelId = Object.freeze({
                        ...state.byChannelId,
                        [item.channel_id]: Object.freeze([...cur, item]),
                    });
                }
                return next;
            }
            case 'sync/threads/open_requested': {
                const p = event.payload;
                if (!p || typeof p.threadId !== 'string') return state;
                return { ...state, selectedThreadId: p.threadId };
            }
            case 'sync/threads/drawer_closed':
                return { ...state, selectedThreadId: null };
            default:
                return state;
        }
    },
});
