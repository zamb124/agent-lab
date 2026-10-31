/**
 * Сообщения Sync — фабрики команд + единый slice истории чатов.
 *
 * Канон `ui_factories.mdc`: одна `createAsyncOp` = одна WS-команда. Поэтому
 * на каждую mutating-операцию (send/edit/delete/forward/react/pin/transcribe*)
 * заведена отдельная фабрика с собственным `commandType` и REST-зеркалом.
 * Загрузка ленты — `messagesResource` (двунаправленный курсор `before/after`,
 * один и тот же `commandType: 'sync/messages/list_requested'`); подгрузка
 * страниц — `messagesLoadOlderOp` / `messagesLoadNewerOp`.
 *
 * Доменное состояние ленты (byChannelId, optimistic-pending, reply/edit
 * режимы, контекстное меню, flash) живёт в slice-only фабрике
 * `messagesStoreSlice` (`createSlice('sync/messages_store')`). Реагирует на:
 *   - push-события сервера: `sync/message/created`, `sync/message/updated`,
 *     `sync/message/deleted`, `sync/message/reaction_changed`,
 *     `sync/message/status_changed`;
 *   - локальные UI-события: `sync/messages_store/reply_mode_set`,
 *     `sync/messages_store/edit_mode_set`,
 *     `sync/messages_store/context_menu_requested`,
 *     `sync/messages_store/context_menu_dismissed`,
 *     `sync/messages_store/optimistic_added`,
 *     `sync/messages_store/optimistic_failed`,
 *     `sync/messages_store/flash_requested`,
 *     `sync/messages_store/flash_cleared`,
 *     `sync/messages_store/history_older_started`,
 *     `sync/messages_store/history_newer_started`,
 *     `sync/messages_store/history_older_loaded`,
 *     `sync/messages_store/history_newer_loaded`;
 *   - success загрузок: `sync/messages/succeeded` (первичная страница).
 *
 * Slice (канон zero-fallback, `frontend.mdc`):
 *   {
 *     byChannelId: { [channelId]: ChannelData },
 *     replyToMessageId: string | null,
 *     editMessageId: string | null,
 *     contextMenuTarget: { messageId, channelId, x, y } | null,
 *     flashMessageId: string | null,
 *     flashSeq: number,
 *   }
 *
 * `ChannelData` (через `_emptyChannelData()` + `_normalizeMessage()`):
 *   {
 *     items: Message[],
 *     pendingByLocalId: { [localId]: Message },
 *     loading: false,
 *     loadingOlder: false,
 *     loadingNewer: false,
 *     error: null,
 *     pagination: { hasOlder: false, oldestCursor: null, hasNewer: false, newestCursor: null },
 *   }
 *
 * `Message` после `_normalizeMessage`: `contents: array`, `reactions: array`.
 */

import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';
import type { SyncChannelMessagesData, SyncMessagesStoreSlice } from '../sync.types.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { isPlatformEventType, isPlainRecord } from '@platform/lib/events/payload.js';
import { opSucceededResult } from '@platform/lib/events/factories/merge.js';

function createEmptyChannelData(): SyncChannelMessagesData {
    const items: Record<string, unknown>[] = [];
    Object.freeze(items);
    const pendingByLocalId: Record<string, Record<string, unknown>> = {};
    Object.freeze(pendingByLocalId);
    const pagination = {
        hasOlder: false,
        oldestCursor: null,
        hasNewer: false,
        newestCursor: null,
    };
    Object.freeze(pagination);
    const data: SyncChannelMessagesData = {
        items,
        pendingByLocalId,
        loading: false,
        loadingOlder: false,
        loadingNewer: false,
        error: null,
        pagination,
    };
    Object.freeze(data);
    return data;
}

const EMPTY_CHANNEL_DATA = createEmptyChannelData();

function _emptyChannelData(): SyncChannelMessagesData {
    return EMPTY_CHANNEL_DATA;
}

function _getChannelData(state: SyncMessagesStoreSlice, channelId: unknown): SyncChannelMessagesData {
    if (typeof channelId !== 'string' || channelId === '') return EMPTY_CHANNEL_DATA;
    const data = state.byChannelId[channelId];
    if (data !== undefined) return data;
    return EMPTY_CHANNEL_DATA;
}

function payloadRecord(event: { payload: unknown }): Record<string, unknown> | null {
    return isPlainRecord(event.payload) ? event.payload : null;
}

function _normalizeMessage(message: unknown): Record<string, unknown> | null {
    if (!isPlainRecord(message)) return null;
    const messageId = typeof message.message_id === 'string' && message.message_id !== ''
        ? message.message_id
        : null;
    return Object.freeze({
        ...message,
        message_id: messageId,
        contents: Array.isArray(message.contents) ? message.contents : [],
        reactions: Array.isArray(message.reactions) ? message.reactions : [],
    });
}

function _normalizeMessages(items: unknown): Record<string, unknown>[] {
    if (!Array.isArray(items)) return [];
    const messages: Record<string, unknown>[] = [];
    for (const item of items) {
        const message = _normalizeMessage(item);
        if (message === null) {
            throw new Error('sync/messages: message must be an object');
        }
        messages.push(message);
    }
    return messages;
}

export const messagesResource = createAsyncOp({
    name: 'sync/messages',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    silent: true,
    commandType: 'sync/messages/list_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/channels/:channel_id/messages' },
});

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

export const messagesSendOp = createAsyncOp({
    name: 'sync/messages_send',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    silent: true,
    commandType: 'sync/messages/send_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/messages' },
    onSuccess: (ctx, result, event) => {
        const payload = payloadRecord(event);
        const body = payload !== null && isPlainRecord(payload.body) ? payload.body : null;
        const localId = body && typeof body.local_id === 'string' && body.local_id !== ''
            ? body.local_id
            : null;
        ctx.dispatch(
            'sync/messages_store/send_confirmed',
            { message: result, localId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const messagesEditOp = createAsyncOp({
    name: 'sync/messages_edit',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    silent: true,
    commandType: 'sync/messages/edit_requested',
    restMirror: { method: 'PATCH', path: '/sync/api/v1/channels/:channel_id/messages/:message_id' },
});

export const messagesDeleteOp = createAsyncOp({
    name: 'sync/messages_delete',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    silent: true,
    commandType: 'sync/messages/delete_requested',
    restMirror: { method: 'DELETE', path: '/sync/api/v1/channels/:channel_id/messages/:message_id' },
});

export const messagesForwardOp = createAsyncOp({
    name: 'sync/messages_forward',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    silent: true,
    commandType: 'sync/messages/forward_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/messages/:message_id/forward' },
});

export const messagesReactOp = createAsyncOp({
    name: 'sync/messages_react',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/messages/react_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/messages/:message_id/react' },
});

export const messagesPinOp = createAsyncOp({
    name: 'sync/messages_pin',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/messages/pin_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/pins' },
    onFailure: (ctx, err: unknown, event) => {
        const msg = err instanceof Error ? err.message : '';
        if (msg === '') return;
        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            { type: 'error', message: msg },
            { causation_id: event.id },
        );
    },
});

export const messagesMarkReadOp = createAsyncOp({
    name: 'sync/messages_mark_read',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/messages/mark_read_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/messages/:message_id/read' },
});

export const messagesTranscribeAudioOp = createAsyncOp({
    name: 'sync/messages_transcribe_audio',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    silent: true,
    commandType: 'sync/messages/transcribe_audio_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/messages/:message_id/transcribe' },
});

export const messagesTranscribeVideoOp = createAsyncOp({
    name: 'sync/messages_transcribe_video',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    silent: true,
    commandType: 'sync/messages/transcribe_video_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/messages/:message_id/transcribe-video' },
});

export const messagesTranscribeCallOp = createAsyncOp({
    name: 'sync/messages_transcribe_call',
    transport: 'ws',
    wsTimeoutMs: 10_000,
    successToastKey: 'sync:bubble.toast_transcribe_call_queued',
    errorToastKey: 'sync:bubble.toast_transcribe_call_failed',
    commandType: 'sync/messages/transcribe_call_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/calls/:call_id/transcribe' },
});

export const messagesStoreSlice = createSlice({
    name: 'sync/messages_store',
    extraInitial: {
        byChannelId: Object.freeze({}),
        replyToMessageId: null,
        editMessageId: null,
        contextMenuTarget: null,
        flashMessageId: null,
        flashSeq: 0,
    },
    extraEvents: {
        REPLY_MODE_SET: 'reply_mode_set',
        EDIT_MODE_SET: 'edit_mode_set',
        CONTEXT_MENU_REQUESTED: 'context_menu_requested',
        CONTEXT_MENU_DISMISSED: 'context_menu_dismissed',
        OPTIMISTIC_ADDED: 'optimistic_added',
        OPTIMISTIC_FAILED: 'optimistic_failed',
        OPTIMISTIC_RESEND_REQUESTED: 'optimistic_resend_requested',
        SEND_CONFIRMED: 'send_confirmed',
        FLASH_REQUESTED: 'flash_requested',
        FLASH_CLEARED: 'flash_cleared',
        INITIAL_LOAD_STARTED: 'initial_load_started',
        INITIAL_LOAD_LOADED: 'initial_load_loaded',
        INITIAL_LOAD_FAILED: 'initial_load_failed',
        HISTORY_OLDER_STARTED: 'history_older_started',
        HISTORY_NEWER_STARTED: 'history_newer_started',
        HISTORY_OLDER_LOADED: 'history_older_loaded',
        HISTORY_NEWER_LOADED: 'history_newer_loaded',
    },
    actions: {
        setReplyMode: 'reply_mode_set',
        setEditMode: 'edit_mode_set',
        showContextMenu: 'context_menu_requested',
        dismissContextMenu: 'context_menu_dismissed',
        addOptimistic: 'optimistic_added',
        failOptimistic: 'optimistic_failed',
        resendOptimistic: 'optimistic_resend_requested',
        flash: 'flash_requested',
        clearFlash: 'flash_cleared',
        startInitial: 'initial_load_started',
        loadedInitial: 'initial_load_loaded',
        failInitial: 'initial_load_failed',
        startOlder: 'history_older_started',
        startNewer: 'history_newer_started',
        loadedOlder: 'history_older_loaded',
        loadedNewer: 'history_newer_loaded',
    },
    extraReducer: (state: SyncMessagesStoreSlice, event) => {
        const s = state;
        const updateChannel = (channelId: string, updater: (cur: SyncChannelMessagesData) => SyncChannelMessagesData) => {
            const cur = _getChannelData(s, channelId);
            const next = updater(cur);
            return {
                ...s,
                byChannelId: Object.freeze({ ...s.byChannelId, [channelId]: Object.freeze(next) }),
            };
        };

        switch (event.type) {
            case 'sync/context/company_cleared': {
                return {
                    byChannelId: Object.freeze({}),
                    replyToMessageId: null,
                    editMessageId: null,
                    contextMenuTarget: null,
                    flashMessageId: null,
                    flashSeq: 0,
                };
            }
            case 'sync/messages/succeeded': {
                const result = opSucceededResult(event, messagesResource);
                if (result === null || !Array.isArray(result.items) || result.items.length === 0) return state;
                const firstItem = result.items[0];
                const channelId = firstItem && typeof firstItem.channel_id === 'string' ? firstItem.channel_id : '';
                if (channelId === '') return state;
                const items = _normalizeMessages(result.items);
                const hasOlder = typeof result.has_older === 'boolean'
                    ? result.has_older
                    : (typeof result.prev_cursor === 'string' && result.prev_cursor !== '');
                const hasNewer = typeof result.has_newer === 'boolean'
                    ? result.has_newer
                    : (typeof result.next_cursor === 'string' && result.next_cursor !== '');
                const oldestCursor = typeof result.oldest_cursor === 'string'
                    ? result.oldest_cursor
                    : (typeof result.prev_cursor === 'string' ? result.prev_cursor : null);
                const newestCursor = typeof result.newest_cursor === 'string'
                    ? result.newest_cursor
                    : (typeof result.next_cursor === 'string' ? result.next_cursor : null);
                return updateChannel(channelId, (cur) => ({
                    ...cur,
                    items: Object.freeze(items),
                    pagination: Object.freeze({
                        hasOlder,
                        oldestCursor,
                        hasNewer,
                        newestCursor,
                    }),
                    loading: false,
                    error: null,
                }));
            }
            case 'sync/messages_store/initial_load_started': {
                const p = payloadRecord(event);
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                return updateChannel(p.channelId, (cur) => ({ ...cur, loading: true, error: null }));
            }
            case 'sync/messages_store/initial_load_loaded': {
                const p = payloadRecord(event);
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                const result = isPlainRecord(p.result) ? p.result : null;
                const items = result && Array.isArray(result.items) ? _normalizeMessages(result.items) : [];
                const hasOlder = result !== null && typeof result.has_older === 'boolean'
                    ? result.has_older
                    : result !== null && typeof result.prev_cursor === 'string' && result.prev_cursor !== '';
                const hasNewer = result !== null && typeof result.has_newer === 'boolean'
                    ? result.has_newer
                    : result !== null && typeof result.next_cursor === 'string' && result.next_cursor !== '';
                const oldestCursor = result !== null && typeof result.oldest_cursor === 'string'
                    ? result.oldest_cursor
                    : result !== null && typeof result.prev_cursor === 'string'
                        ? result.prev_cursor
                        : null;
                const newestCursor = result !== null && typeof result.newest_cursor === 'string'
                    ? result.newest_cursor
                    : result !== null && typeof result.next_cursor === 'string'
                        ? result.next_cursor
                        : null;
                return updateChannel(p.channelId, (cur) => ({
                    ...cur,
                    items: Object.freeze(items),
                    loading: false,
                    error: null,
                    pagination: Object.freeze({
                        hasOlder,
                        oldestCursor,
                        hasNewer,
                        newestCursor,
                    }),
                }));
            }
            case 'sync/messages_store/initial_load_failed': {
                const p = payloadRecord(event);
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                const message = typeof p.message === 'string' && p.message !== '' ? p.message : 'failed';
                return updateChannel(p.channelId, (cur) => ({ ...cur, loading: false, error: message }));
            }
            case 'sync/messages_store/history_older_loaded': {
                const p = payloadRecord(event);
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                if (!Array.isArray(p.items)) return state;
                const newItems = _normalizeMessages(p.items);
                return updateChannel(p.channelId, (cur) => {
                    const seen = new Set(cur.items.map((x: Record<string, unknown>) => x.message_id));
                    const merged = [...newItems.filter((x: Record<string, unknown>) => !seen.has(x.message_id)), ...cur.items];
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
            case 'sync/messages_store/history_newer_loaded': {
                const p = payloadRecord(event);
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                if (!Array.isArray(p.items)) return state;
                const newItems = _normalizeMessages(p.items);
                return updateChannel(p.channelId, (cur) => {
                    const seen = new Set(cur.items.map((x: Record<string, unknown>) => x.message_id));
                    const merged = [...cur.items, ...newItems.filter((x: Record<string, unknown>) => !seen.has(x.message_id))];
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
            case 'sync/messages_store/history_older_started': {
                const p = payloadRecord(event);
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                return updateChannel(p.channelId, (cur) => ({ ...cur, loadingOlder: true }));
            }
            case 'sync/messages_store/history_newer_started': {
                const p = payloadRecord(event);
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                return updateChannel(p.channelId, (cur) => ({ ...cur, loadingNewer: true }));
            }
            case 'sync/message/created':
            case 'sync/messages_store/send_confirmed': {
                const payload = payloadRecord(event);
                const raw = isPlatformEventType(event, 'sync/message/created')
                    ? event.payload
                    : (payload !== null ? payload.message : undefined);
                const m = _normalizeMessage(raw);
                if (!m || typeof m.channel_id !== 'string' || typeof m.message_id !== 'string') return state;
                const localIdFromConfirm = event.type === 'sync/messages_store/send_confirmed'
                    && payload !== null
                    && typeof payload.localId === 'string'
                    && payload.localId !== ''
                    ? payload.localId
                    : null;
                const localId = localIdFromConfirm
                    || (typeof m.local_id === 'string' && m.local_id !== '' ? m.local_id : null);
                return updateChannel(m.channel_id, (cur) => {
                    let pending: Record<string, Record<string, unknown>> = { ...cur.pendingByLocalId };
                    if (localId !== null && pending[localId]) {
                        delete pending[localId];
                    }
                    if (cur.items.some((x) => x.message_id === m.message_id)) {
                        return {
                            ...cur,
                            pendingByLocalId: Object.freeze(pending),
                        };
                    }
                    return {
                        ...cur,
                        items: Object.freeze([...cur.items, m]),
                        pendingByLocalId: Object.freeze(pending),
                    };
                });
            }
            case 'sync/message/updated': {
                const m = isPlatformEventType(event, 'sync/message/updated')
                    ? _normalizeMessage(event.payload)
                    : null;
                if (!m || typeof m.channel_id !== 'string' || typeof m.message_id !== 'string') return state;
                return updateChannel(m.channel_id, (cur) => {
                    const idx = cur.items.findIndex((x) => x.message_id === m.message_id);
                    if (idx === -1) return cur;
                    const items = cur.items.map((x, i) => (i === idx ? Object.freeze({ ...x, ...m }) : x));
                    return { ...cur, items: Object.freeze(items) };
                });
            }
            case 'sync/message/deleted': {
                if (!isPlatformEventType(event, 'sync/message/deleted')) return state;
                const p = event.payload;
                return updateChannel(p.channel_id, (cur) => ({
                    ...cur,
                    items: Object.freeze(cur.items.filter((x) => x.message_id !== p.message_id)),
                }));
            }
            case 'sync/message/reaction_changed': {
                if (!isPlatformEventType(event, 'sync/message/reaction_changed')) return state;
                const p = event.payload;
                const reactions = Array.isArray(p.reactions) ? p.reactions : [];
                return updateChannel(p.channel_id, (cur) => {
                    const idx = cur.items.findIndex((x) => x.message_id === p.message_id);
                    if (idx === -1) return cur;
                    const items = cur.items.map((x, i) => (i === idx ? Object.freeze({ ...x, reactions }) : x));
                    return { ...cur, items: Object.freeze(items) };
                });
            }
            case 'sync/message/status_changed': {
                if (!isPlatformEventType(event, 'sync/message/status_changed')) return state;
                const p = event.payload;
                const channelId = p.channel_id;
                if (typeof channelId !== 'string' || channelId === '') return state;
                return updateChannel(channelId, (cur) => {
                    const idx = cur.items.findIndex((x) => x.message_id === p.message_id);
                    if (idx === -1) return cur;
                    const items = cur.items.map((x, i) => (i === idx ? Object.freeze({ ...x, status: p.status }) : x));
                    return { ...cur, items: Object.freeze(items) };
                });
            }
            case 'sync/messages_store/reply_mode_set': {
                const messageId = (payloadRecord(event))?.messageId;
                return {
                    ...s,
                    replyToMessageId: typeof messageId === 'string' ? messageId : null,
                    editMessageId: null,
                };
            }
            case 'sync/messages_store/edit_mode_set': {
                const messageId = (payloadRecord(event))?.messageId;
                return {
                    ...s,
                    editMessageId: typeof messageId === 'string' ? messageId : null,
                    replyToMessageId: null,
                };
            }
            case 'sync/messages_store/context_menu_requested': {
                const p = payloadRecord(event);
                if (!p || typeof p.messageId !== 'string') return state;
                if (typeof p.channelId !== 'string' || p.channelId === '') return state;
                return {
                    ...s,
                    contextMenuTarget: Object.freeze({
                        messageId: p.messageId,
                        channelId: p.channelId,
                        x: typeof p.x === 'number' ? p.x : 0,
                        y: typeof p.y === 'number' ? p.y : 0,
                    }),
                };
            }
            case 'sync/messages_store/context_menu_dismissed': {
                return { ...s, contextMenuTarget: null };
            }
            case 'sync/messages_store/optimistic_added': {
                const p = payloadRecord(event);
                if (!p || typeof p.channelId !== 'string' || !p.item) return state;
                const item = _normalizeMessage(p.item);
                const localId = item !== null ? item.local_id : null;
                if (item === null || typeof localId !== 'string' || localId === '') return state;
                return updateChannel(p.channelId, (cur) => ({
                    ...cur,
                    pendingByLocalId: Object.freeze({
                        ...cur.pendingByLocalId,
                        [localId]: Object.freeze({ ...item, _pending: true }),
                    }),
                }));
            }
            case 'sync/messages_store/flash_requested': {
                const p = payloadRecord(event);
                if (!p || typeof p.messageId !== 'string' || p.messageId === '') return state;
                return { ...s, flashMessageId: p.messageId, flashSeq: s.flashSeq + 1 };
            }
            case 'sync/messages_store/flash_cleared':
                return { ...s, flashMessageId: null };
            case 'sync/messages_store/optimistic_failed': {
                const p = payloadRecord(event);
                if (p === null) return state;
                const localId = p.localId;
                if (typeof p.channelId !== 'string' || typeof localId !== 'string') return state;
                return updateChannel(p.channelId, (cur) => {
                    if (!cur.pendingByLocalId[localId]) return cur;
                    const errorMessage = typeof p.message === 'string' && p.message !== '' ? p.message : 'failed';
                    return {
                        ...cur,
                        pendingByLocalId: Object.freeze({
                            ...cur.pendingByLocalId,
                            [localId]: Object.freeze({
                                ...cur.pendingByLocalId[localId],
                                _pending: false,
                                _error: errorMessage,
                            }),
                        }),
                    };
                });
            }
            case 'sync/messages_store/optimistic_resend_requested': {
                const p = payloadRecord(event);
                if (p === null) return state;
                const localId = p.localId;
                if (typeof p.channelId !== 'string' || typeof localId !== 'string') return state;
                return updateChannel(p.channelId, (cur) => {
                    if (!cur.pendingByLocalId[localId]) return cur;
                    return {
                        ...cur,
                        pendingByLocalId: Object.freeze({
                            ...cur.pendingByLocalId,
                            [localId]: Object.freeze({
                                ...cur.pendingByLocalId[localId],
                                _pending: true,
                                _error: null,
                                status: 'sending',
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

export { _getChannelData, _emptyChannelData };

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'sync/messages': typeof messagesResource;
        'sync/messages_load_older': typeof messagesLoadOlderOp;
        'sync/messages_load_newer': typeof messagesLoadNewerOp;
        'sync/messages_send': typeof messagesSendOp;
        'sync/messages_edit': typeof messagesEditOp;
        'sync/messages_delete': typeof messagesDeleteOp;
        'sync/messages_forward': typeof messagesForwardOp;
        'sync/messages_react': typeof messagesReactOp;
        'sync/messages_pin': typeof messagesPinOp;
        'sync/messages_mark_read': typeof messagesMarkReadOp;
        'sync/messages_transcribe_audio': typeof messagesTranscribeAudioOp;
        'sync/messages_transcribe_video': typeof messagesTranscribeVideoOp;
        'sync/messages_transcribe_call': typeof messagesTranscribeCallOp;
        'sync/messages_store': typeof messagesStoreSlice;
    }
}
