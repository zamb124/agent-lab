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
import type { ResourceCollectionSlice } from '@platform/lib/events/factories/resource-collection.js';

interface SyncThreadsSlice extends ResourceCollectionSlice {
    selectedThreadId: string | null;
    byChannelId: Readonly<Record<string, readonly Record<string, any>[]>>;
}

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
        const s = state as SyncThreadsSlice;
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
                const payload = event.payload as Record<string, any> | null;
                const item = event.type === events.CREATED
                    ? (payload && payload.item)
                    : payload;
                if (!item || typeof item.thread_id !== 'string') return state;
                const hasItem = s.items.some((x) => x.thread_id === item.thread_id);
                const next: SyncThreadsSlice = {
                    ...s,
                    items: hasItem ? s.items : Object.freeze([...s.items, item]),
                    selectedThreadId: item.thread_id,
                    byChannelId: s.byChannelId,
                };
                if (typeof item.channel_id === 'string') {
                    const existing = s.byChannelId[item.channel_id];
                    const cur = Array.isArray(existing) ? existing : [];
                    const hasInChannel = cur.some((x) => x.thread_id === item.thread_id);
                    next.byChannelId = Object.freeze({
                        ...s.byChannelId,
                        [item.channel_id]: hasInChannel ? cur : Object.freeze([...cur, item]),
                    });
                }
                return next;
            }
            case 'sync/threads/open_requested': {
                const p = event.payload as Record<string, unknown> | null;
                if (!p || typeof p.threadId !== 'string') return state;
                return { ...s, selectedThreadId: p.threadId };
            }
            case 'sync/threads/drawer_closed':
                return { ...s, selectedThreadId: null };
            default:
                return state;
        }
    },
});
