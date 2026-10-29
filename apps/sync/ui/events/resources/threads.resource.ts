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
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { SyncThreadsSlice } from '../sync.types.js';


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
    extraReducer: (state: SyncThreadsSlice, event, events) => {
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
                const payload = event.payload;
                const rawItem = event.type === events.CREATED
                    ? (isPlainRecord(payload) ? payload.item : null)
                    : payload;
                if (!isPlainRecord(rawItem) || typeof rawItem.thread_id !== 'string') return state;
                const threadId = rawItem.thread_id;
                const hasItem = state.items.some((row) => row.thread_id === threadId);
                const next: SyncThreadsSlice = {
                    ...state,
                    items: hasItem ? state.items : Object.freeze([...state.items, rawItem]),
                    selectedThreadId: threadId,
                    byChannelId: state.byChannelId,
                };
                const channelId = rawItem.channel_id;
                if (typeof channelId === 'string') {
                    const existing = state.byChannelId[channelId];
                    if (existing !== undefined && !Array.isArray(existing)) {
                        throw new Error('sync/threads: channel threads must be an array');
                    }
                    const cur = Array.isArray(existing) ? existing : [];
                    const hasInChannel = cur.some((row) => row.thread_id === threadId);
                    next.byChannelId = Object.freeze({
                        ...state.byChannelId,
                        [channelId]: hasInChannel ? cur : Object.freeze([...cur, rawItem]),
                    });
                }
                return next;
            }
            case 'sync/threads/open_requested': {
                const p = event.payload;
                if (!isPlainRecord(p) || typeof p.threadId !== 'string') return state;
                return { ...state, selectedThreadId: p.threadId };
            }
            case 'sync/threads/drawer_closed':
                return { ...state, selectedThreadId: null };
            default:
                return state;
        }
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'sync/threads': typeof threadsResource;
    }
}
