/**
 * Sync Messages — двунаправленная курсорная пагинация (before/after) делает
 * `createCursorList` неподходящим. Используем `createAsyncOp` с
 * `extraInitial.byChannelId` slice'ом и `extraReducer` для push-событий.
 *
 * Все мутации — `transport: 'ws'` + REST-зеркало (`apps/sync/api/messages.py`).
 *
 * Slice (zero-fallback canon, см. `frontend.mdc`):
 *   {
 *     byChannelId: { [channelId]: ChannelData },
 *     replyToMessageId: string | null,
 *     editMessageId: string | null,
 *     contextMenuTarget: { messageId, x, y } | null,
 *   }
 *
 * `ChannelData` — гарантированная форма (через `_emptyChannelData()` +
 * `_normalizeMessage()`):
 *   {
 *     items: Message[],
 *     pendingByLocalId: { [localId]: Message },
 *     loading: false,
 *     error: null,
 *     pagination: { hasOlder: false, oldestCursor: null, hasNewer: false, newestCursor: null },
 *   }
 *
 * `Message` после `_normalizeMessage`:
 *   contents: array (всегда), reactions: array (всегда), остальные поля как от сервера.
 *
 * Push-события (server -> client): 'sync/message/created',
 * 'sync/message/updated', 'sync/message/deleted',
 * 'sync/message/reaction_changed', 'sync/message/status_changed' —
 * обрабатываются в extraReducer, мутируют byChannelId.
 *
 * UI-события (client only):
 *   'sync/messages/reply_mode_set', 'sync/messages/edit_mode_set',
 *   'sync/messages/context_menu_requested', 'sync/messages/context_menu_dismissed',
 *   'sync/messages/optimistic_added', 'sync/messages/optimistic_failed'.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

const EMPTY_CHANNEL_DATA = Object.freeze({
    items: Object.freeze([]),
    pendingByLocalId: Object.freeze({}),
    loading: false,
    loadingOlder: false,
    loadingNewer: false,
    error: null,
    pagination: Object.freeze({
        hasOlder: false,
        oldestCursor: null,
        hasNewer: false,
        newestCursor: null,
    }),
});

function _emptyChannelData() {
    return EMPTY_CHANNEL_DATA;
}

function _getChannelData(state, channelId) {
    if (typeof channelId !== 'string' || channelId === '') return EMPTY_CHANNEL_DATA;
    const data = state.byChannelId[channelId];
    if (data && typeof data === 'object') return data;
    return EMPTY_CHANNEL_DATA;
}

function _normalizeMessage(message) {
    if (!message || typeof message !== 'object') return message;
    return Object.freeze({
        ...message,
        contents: Array.isArray(message.contents) ? message.contents : [],
        reactions: Array.isArray(message.reactions) ? message.reactions : [],
    });
}

function _normalizeMessages(items) {
    if (!Array.isArray(items)) return [];
    return items.map(_normalizeMessage);
}

export const messagesResource = createAsyncOp({
    name: 'sync/messages',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    silent: true,
    commandType: 'sync/messages/list_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/channels/:channel_id/messages' },
    extraInitial: {
        byChannelId: Object.freeze({}),
        replyToMessageId: null,
        editMessageId: null,
        contextMenuTarget: null,
        flashMessageId: null,
        flashSeq: 0,
    },
    extraEvents: {
        SEND_REQUESTED: 'send_requested',
        SEND_SUCCEEDED: 'send_succeeded',
        SEND_FAILED: 'send_failed',
        EDIT_REQUESTED: 'edit_requested',
        EDIT_SUCCEEDED: 'edit_succeeded',
        DELETE_REQUESTED: 'delete_requested',
        DELETE_SUCCEEDED: 'delete_succeeded',
        REACT_REQUESTED: 'react_requested',
        REACT_SUCCEEDED: 'react_succeeded',
        PIN_REQUESTED: 'pin_requested',
        PIN_SUCCEEDED: 'pin_succeeded',
        FORWARD_REQUESTED: 'forward_requested',
        FORWARD_SUCCEEDED: 'forward_succeeded',
        TRANSCRIBE_AUDIO_REQUESTED: 'transcribe_audio_requested',
        TRANSCRIBE_VIDEO_REQUESTED: 'transcribe_video_requested',
        TRANSCRIBE_CALL_REQUESTED: 'transcribe_call_requested',
        MARK_READ_REQUESTED: 'mark_read_requested',
        REPLY_MODE_SET: 'reply_mode_set',
        EDIT_MODE_SET: 'edit_mode_set',
        CONTEXT_MENU_REQUESTED: 'context_menu_requested',
        CONTEXT_MENU_DISMISSED: 'context_menu_dismissed',
        OPTIMISTIC_ADDED: 'optimistic_added',
        OPTIMISTIC_FAILED: 'optimistic_failed',
        FLASH_REQUESTED: 'flash_requested',
        FLASH_CLEARED: 'flash_cleared',
        HISTORY_OLDER_STARTED: 'history_older_started',
        HISTORY_NEWER_STARTED: 'history_newer_started',
        HISTORY_OLDER_LOADED: 'history_older_loaded',
        HISTORY_NEWER_LOADED: 'history_newer_loaded',
    },
    actions: {
        send: 'send_requested',
        edit: 'edit_requested',
        remove: 'delete_requested',
        react: 'react_requested',
        pin: 'pin_requested',
        forward: 'forward_requested',
        transcribeAudio: 'transcribe_audio_requested',
        transcribeVideo: 'transcribe_video_requested',
        transcribeCall: 'transcribe_call_requested',
        markRead: 'mark_read_requested',
        setReplyMode: 'reply_mode_set',
        setEditMode: 'edit_mode_set',
        showContextMenu: 'context_menu_requested',
        dismissContextMenu: 'context_menu_dismissed',
        flash: 'flash_requested',
        clearFlash: 'flash_cleared',
    },
    extraReducer: (state, event) => {
        const updateChannel = (channelId, updater) => {
            const cur = _getChannelData(state, channelId);
            const next = updater(cur);
            return {
                ...state,
                byChannelId: Object.freeze({ ...state.byChannelId, [channelId]: Object.freeze(next) }),
            };
        };

        switch (event.type) {
            case 'sync/messages/succeeded': {
                if (!event.payload || !event.payload.result) return state;
                const result = event.payload.result;
                if (!Array.isArray(result.items)) return state;
                if (result.items.length === 0) return state;
                const firstItem = result.items[0];
                const channelId = firstItem && typeof firstItem.channel_id === 'string' ? firstItem.channel_id : '';
                if (channelId === '') return state;
                const items = _normalizeMessages(result.items);
                const hasOlder = typeof result.has_older === 'boolean' ? result.has_older : false;
                const hasNewer = typeof result.has_newer === 'boolean' ? result.has_newer : false;
                const oldestCursor = typeof result.oldest_cursor === 'string' ? result.oldest_cursor : null;
                const newestCursor = typeof result.newest_cursor === 'string' ? result.newest_cursor : null;
                return updateChannel(channelId, (cur) => ({
                    ...cur,
                    items: Object.freeze(items),
                    pagination: Object.freeze({
                        hasOlder,
                        oldestCursor,
                        hasNewer,
                        newestCursor,
                    }),
                }));
            }
            case 'sync/messages/history_older_loaded': {
                const p = event.payload;
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                if (!Array.isArray(p.items)) return state;
                const newItems = _normalizeMessages(p.items);
                return updateChannel(p.channelId, (cur) => {
                    const seen = new Set(cur.items.map((x) => x.message_id));
                    const merged = [...newItems.filter((x) => !seen.has(x.message_id)), ...cur.items];
                    return {
                        ...cur,
                        items: Object.freeze(merged),
                        loadingOlder: false,
                        pagination: Object.freeze({
                            ...cur.pagination,
                            hasOlder: typeof p.hasOlder === 'boolean' ? p.hasOlder : cur.pagination.hasOlder,
                            oldestCursor: typeof p.oldestCursor === 'string' ? p.oldestCursor : cur.pagination.oldestCursor,
                        }),
                    };
                });
            }
            case 'sync/messages/history_newer_loaded': {
                const p = event.payload;
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                if (!Array.isArray(p.items)) return state;
                const newItems = _normalizeMessages(p.items);
                return updateChannel(p.channelId, (cur) => {
                    const seen = new Set(cur.items.map((x) => x.message_id));
                    const merged = [...cur.items, ...newItems.filter((x) => !seen.has(x.message_id))];
                    return {
                        ...cur,
                        items: Object.freeze(merged),
                        loadingNewer: false,
                        pagination: Object.freeze({
                            ...cur.pagination,
                            hasNewer: typeof p.hasNewer === 'boolean' ? p.hasNewer : cur.pagination.hasNewer,
                            newestCursor: typeof p.newestCursor === 'string' ? p.newestCursor : cur.pagination.newestCursor,
                        }),
                    };
                });
            }
            case 'sync/messages/history_older_started': {
                const p = event.payload;
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                return updateChannel(p.channelId, (cur) => ({ ...cur, loadingOlder: true }));
            }
            case 'sync/messages/history_newer_started': {
                const p = event.payload;
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                return updateChannel(p.channelId, (cur) => ({ ...cur, loadingNewer: true }));
            }
            case 'sync/message/created': {
                const m = _normalizeMessage(event.payload);
                if (!m || typeof m.channel_id !== 'string' || typeof m.message_id !== 'string') return state;
                return updateChannel(m.channel_id, (cur) => {
                    if (cur.items.some((x) => x.message_id === m.message_id)) return cur;
                    let pending = cur.pendingByLocalId;
                    if (typeof m.local_id === 'string' && pending[m.local_id]) {
                        pending = { ...pending };
                        delete pending[m.local_id];
                    }
                    return {
                        ...cur,
                        items: Object.freeze([...cur.items, m]),
                        pendingByLocalId: Object.freeze(pending),
                    };
                });
            }
            case 'sync/message/updated': {
                const m = _normalizeMessage(event.payload);
                if (!m || typeof m.channel_id !== 'string' || typeof m.message_id !== 'string') return state;
                return updateChannel(m.channel_id, (cur) => {
                    const idx = cur.items.findIndex((x) => x.message_id === m.message_id);
                    if (idx === -1) return cur;
                    const items = cur.items.map((x, i) => (i === idx ? Object.freeze({ ...x, ...m }) : x));
                    return { ...cur, items: Object.freeze(items) };
                });
            }
            case 'sync/message/deleted': {
                const p = event.payload;
                if (!p || typeof p.channel_id !== 'string' || typeof p.message_id !== 'string') return state;
                return updateChannel(p.channel_id, (cur) => ({
                    ...cur,
                    items: Object.freeze(cur.items.filter((x) => x.message_id !== p.message_id)),
                }));
            }
            case 'sync/message/reaction_changed': {
                const p = event.payload;
                if (!p || typeof p.channel_id !== 'string' || typeof p.message_id !== 'string') return state;
                const reactions = Array.isArray(p.reactions) ? p.reactions : [];
                return updateChannel(p.channel_id, (cur) => {
                    const idx = cur.items.findIndex((x) => x.message_id === p.message_id);
                    if (idx === -1) return cur;
                    const items = cur.items.map((x, i) => (i === idx ? Object.freeze({ ...x, reactions }) : x));
                    return { ...cur, items: Object.freeze(items) };
                });
            }
            case 'sync/message/status_changed': {
                const p = event.payload;
                if (!p || typeof p.channel_id !== 'string' || typeof p.message_id !== 'string') return state;
                return updateChannel(p.channel_id, (cur) => {
                    const idx = cur.items.findIndex((x) => x.message_id === p.message_id);
                    if (idx === -1) return cur;
                    const items = cur.items.map((x, i) => (i === idx ? Object.freeze({ ...x, status: p.status }) : x));
                    return { ...cur, items: Object.freeze(items) };
                });
            }
            case 'sync/messages/reply_mode_set': {
                const messageId = event.payload && event.payload.messageId;
                return {
                    ...state,
                    replyToMessageId: typeof messageId === 'string' ? messageId : null,
                    editMessageId: null,
                };
            }
            case 'sync/messages/edit_mode_set': {
                const messageId = event.payload && event.payload.messageId;
                return {
                    ...state,
                    editMessageId: typeof messageId === 'string' ? messageId : null,
                    replyToMessageId: null,
                };
            }
            case 'sync/messages/context_menu_requested': {
                const p = event.payload;
                if (!p || typeof p.messageId !== 'string') return state;
                return {
                    ...state,
                    contextMenuTarget: Object.freeze({
                        messageId: p.messageId,
                        x: typeof p.x === 'number' ? p.x : 0,
                        y: typeof p.y === 'number' ? p.y : 0,
                    }),
                };
            }
            case 'sync/messages/context_menu_dismissed': {
                return { ...state, contextMenuTarget: null };
            }
            case 'sync/messages/optimistic_added': {
                const p = event.payload;
                if (!p || typeof p.channelId !== 'string' || !p.item) return state;
                const item = _normalizeMessage(p.item);
                if (!item || typeof item.local_id !== 'string') return state;
                return updateChannel(p.channelId, (cur) => ({
                    ...cur,
                    pendingByLocalId: Object.freeze({
                        ...cur.pendingByLocalId,
                        [item.local_id]: Object.freeze({ ...item, _pending: true }),
                    }),
                }));
            }
            case 'sync/messages/flash_requested': {
                const p = event.payload;
                if (!p || typeof p.messageId !== 'string' || p.messageId === '') return state;
                return { ...state, flashMessageId: p.messageId, flashSeq: state.flashSeq + 1 };
            }
            case 'sync/messages/flash_cleared':
                return { ...state, flashMessageId: null };
            case 'sync/messages/optimistic_failed': {
                const p = event.payload;
                if (!p || typeof p.channelId !== 'string' || typeof p.localId !== 'string') return state;
                return updateChannel(p.channelId, (cur) => {
                    if (!cur.pendingByLocalId[p.localId]) return cur;
                    const errorMessage = typeof p.message === 'string' && p.message !== '' ? p.message : 'failed';
                    return {
                        ...cur,
                        pendingByLocalId: Object.freeze({
                            ...cur.pendingByLocalId,
                            [p.localId]: Object.freeze({
                                ...cur.pendingByLocalId[p.localId],
                                _pending: false,
                                _error: errorMessage,
                            }),
                        }),
                    };
                });
            }
            default:
                return state;
        }
    },
});

/**
 * Двусторонняя пагинация: отдельные ops с уникальным `name` (и slice),
 * но с тем же canonical `commandType` (`sync/messages/list_requested`).
 *
 * Reducer `messagesResource` не читает их `succeeded` — компоненты после
 * успеха явно диспатчат `HISTORY_OLDER_LOADED` / `HISTORY_NEWER_LOADED`
 * с уже распакованным `result.items`.
 */
export const messagesLoadOlderOp = createAsyncOp({
    name: 'sync/messages_load_older',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    silent: true,
    commandType: 'sync/messages/list_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/channels/:channel_id/messages' },
});

export const messagesLoadNewerOp = createAsyncOp({
    name: 'sync/messages_load_newer',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    silent: true,
    commandType: 'sync/messages/list_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/channels/:channel_id/messages' },
});

export { _getChannelData, _emptyChannelData };
