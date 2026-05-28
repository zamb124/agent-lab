/**
 * Треды Sync — треды канала.
 *
 * REST-зеркало: `apps/sync/api/threads.py`. WS-команда `sync/threads/create_requested`
 * → handler `threads.create`.
 *
 * Slice добавляет UI-состояние `selectedThreadId` (открытый thread-drawer) и
 * `byChannelId` (сводка тредов по каналу).
 *
 * UI-действия: openThread(threadId), closeThread().
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
    extraReducer: (state, event, events) => {
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
            case events.CREATED:
            case 'sync/thread/created': {
                const item = event.type === events.CREATED
                    ? (event.payload && event.payload.item)
                    : event.payload;
                if (!item || typeof item.thread_id !== 'string') return state;
                const hasItem = state.items.some((x) => x.thread_id === item.thread_id);
                const next = {
                    ...state,
                    items: hasItem ? state.items : Object.freeze([...state.items, item]),
                    selectedThreadId: item.thread_id,
                };
                if (typeof item.channel_id === 'string') {
                    const existing = state.byChannelId[item.channel_id];
                    const cur = Array.isArray(existing) ? existing : [];
                    const hasInChannel = cur.some((x) => x.thread_id === item.thread_id);
                    next.byChannelId = Object.freeze({
                        ...state.byChannelId,
                        [item.channel_id]: hasInChannel ? cur : Object.freeze([...cur, item]),
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
