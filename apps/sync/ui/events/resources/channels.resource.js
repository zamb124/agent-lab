/**
 * Sync Channels — каналы (direct/group/topic).
 *
 * Базовая фабрика — CRUD через WS. Дополнительные операции (mark_read,
 * typing, addMember, notifications, members list) — отдельные `createAsyncOp`
 * с restMirror на соответствующие REST-эндпоинты `apps/sync/api/channels.py`.
 *
 * Push-события: 'sync/channel/created', 'sync/channel/typing',
 * 'sync/channel/read_updated', 'sync/channel/member_added',
 * 'sync/channel/pins_changed' — обрабатываются в extraReducer.
 */

import { createAsyncOp, createResourceCollection } from '@platform/lib/events/index.js';

const EMPTY_TYPING = Object.freeze({});

function _normalizeChannel(channel) {
    if (!channel || typeof channel !== 'object') return channel;
    const unread = typeof channel.unread_count === 'number' ? channel.unread_count : 0;
    const mention = typeof channel.mention_unread_count === 'number' ? channel.mention_unread_count : 0;
    const preview = typeof channel.last_message_preview === 'string' ? channel.last_message_preview : '';
    return Object.freeze({
        ...channel,
        unread_count: unread,
        mention_unread_count: mention,
        last_message_preview: preview,
    });
}

export const channelsResource = createResourceCollection({
    name: 'sync/channels',
    baseUrl: '/sync/api/v1/channels',
    idField: 'id',
    operations: ['list', 'create', 'update'],
    transport: 'ws',
    wsTimeoutMs: 5_000,
    // restMirror.update указывает на реальный path FastAPI
    // (`@router.patch("/{channel_id}")` в `apps/sync/api/channels.py`).
    // Auto-derived `/{id}` не подошёл бы: idField фабрики локально называется
    // `id`, а FastAPI-параметр — `channel_id`.
    restMirror: {
        update: { method: 'PATCH', path: '/sync/api/v1/channels/:channel_id' },
    },
    toastKeys: {
        create: 'sync:channels.toast_created',
        create_error: 'sync:channels.err_create',
        update: 'sync:channels.toast_updated',
        update_error: 'sync:channels.err_update',
    },
    mapItem: _normalizeChannel,
    extraInitial: {
        selectedChannelId: null,
        peerReadAtByChannel: Object.freeze({}),
        typingByChannel: Object.freeze({}),
        membersByChannel: Object.freeze({}),
    },
    extraEvents: {
        SELECTED: 'channel_selected',
        OWN_READ_SET: 'own_read_set',
    },
    actions: {
        selectChannel: 'channel_selected',
        setOwnRead: 'own_read_set',
    },
    extraReducer: (state, event) => {
        switch (event.type) {
            case 'sync/channels/channel_selected': {
                const p = event.payload;
                const channelId = p && typeof p.channelId === 'string' ? p.channelId : null;
                return { ...state, selectedChannelId: channelId };
            }
            case 'sync/channel/created': {
                const raw = event.payload;
                if (!raw || typeof raw !== 'object' || typeof raw.id !== 'string') return state;
                if (state.items.some((x) => x.id === raw.id)) return state;
                const item = _normalizeChannel(raw);
                return { ...state, items: Object.freeze([...state.items, item]) };
            }
            case 'sync/channel/read_updated': {
                const p = event.payload;
                if (!p || typeof p.channel_id !== 'string') return state;
                if (typeof p.read_at !== 'string') return state;
                return {
                    ...state,
                    peerReadAtByChannel: Object.freeze({
                        ...state.peerReadAtByChannel,
                        [p.channel_id]: p.read_at,
                    }),
                };
            }
            case 'sync/channel/typing': {
                const p = event.payload;
                if (!p || typeof p.channel_id !== 'string') return state;
                const existing = state.typingByChannel[p.channel_id];
                const cur = (existing && typeof existing === 'object') ? existing : EMPTY_TYPING;
                const userId = p.user && p.user.user_id;
                if (typeof userId !== 'string') return state;
                const next = { ...cur };
                if (p.typing) {
                    const threadId = typeof p.thread_id === 'string' ? p.thread_id : null;
                    next[userId] = { thread_id: threadId, ts: Date.now() };
                } else {
                    delete next[userId];
                }
                return {
                    ...state,
                    typingByChannel: Object.freeze({
                        ...state.typingByChannel,
                        [p.channel_id]: Object.freeze(next),
                    }),
                };
            }
            case 'sync/channel/member_added': {
                const p = event.payload;
                if (!p || typeof p.channel_id !== 'string') return state;
                const cur = state.membersByChannel[p.channel_id];
                if (!Array.isArray(cur)) return state;
                if (cur.some((m) => m.user_id === p.added_user_id)) return state;
                return {
                    ...state,
                    membersByChannel: Object.freeze({
                        ...state.membersByChannel,
                        [p.channel_id]: Object.freeze([...cur, { user_id: p.added_user_id }]),
                    }),
                };
            }
            case 'sync/channel/pins_changed': {
                const p = event.payload;
                if (!p || typeof p.id !== 'string') return state;
                const idx = state.items.findIndex((x) => x.id === p.id);
                if (idx === -1) return state;
                const items = state.items.map((x, i) => (i === idx ? _normalizeChannel({ ...x, ...p }) : x));
                return { ...state, items: Object.freeze(items) };
            }
            case 'sync/message/created': {
                const m = event.payload;
                if (!m || typeof m.channel_id !== 'string') return state;
                const idx = state.items.findIndex((x) => x.id === m.channel_id);
                if (idx === -1) return state;
                const channel = state.items[idx];
                const isSelected = state.selectedChannelId === m.channel_id;
                const preview = typeof m.preview === 'string' ? m.preview
                    : (typeof m.last_message_preview === 'string' ? m.last_message_preview : channel.last_message_preview);
                const lastAt = typeof m.sent_at === 'string' ? m.sent_at : channel.last_message_at;
                const next = {
                    ...channel,
                    last_message_preview: preview,
                    last_message_at: lastAt,
                };
                if (!isSelected && typeof m.local_id !== 'string') {
                    next.unread_count = channel.unread_count + 1;
                    if (Array.isArray(m.mentioned_user_ids) && m.mentioned_user_ids.length > 0) {
                        next.mention_unread_count = channel.mention_unread_count + 1;
                    }
                }
                const items = state.items.map((x, i) => (i === idx ? _normalizeChannel(next) : x));
                return { ...state, items: Object.freeze(items) };
            }
            case 'sync/channels/own_read_set': {
                const p = event.payload;
                if (!p || typeof p.channelId !== 'string' || p.channelId === '') return state;
                const idx = state.items.findIndex((x) => x.id === p.channelId);
                if (idx === -1) return state;
                const channel = state.items[idx];
                if (channel.unread_count === 0 && channel.mention_unread_count === 0) return state;
                const items = state.items.map((x, i) => (i === idx
                    ? _normalizeChannel({ ...x, unread_count: 0, mention_unread_count: 0 })
                    : x));
                return { ...state, items: Object.freeze(items) };
            }
            default:
                return state;
        }
    },
});

export const channelMarkReadOp = createAsyncOp({
    name: 'sync/channel_mark_read',
    transport: 'ws',
    wsTimeoutMs: 3_000,
    silent: true,
    commandType: 'sync/channels/mark_read_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/read' },
    onSuccess: (ctx, _result, event) => {
        const p = event && event.payload;
        if (!p || typeof p.channel_id !== 'string' || p.channel_id === '') return;
        ctx.dispatch('sync/channels/own_read_set', { channelId: p.channel_id }, { source: 'local' });
    },
});

export const channelTypingOp = createAsyncOp({
    name: 'sync/channel_typing',
    transport: 'ws',
    wsTimeoutMs: 2_000,
    silent: true,
    commandType: 'sync/channels/typing_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/typing' },
});

export const channelAddMemberOp = createAsyncOp({
    name: 'sync/channel_add_member',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    successToastKey: 'sync:channels.toast_member_added',
    errorToastKey: 'sync:channels.err_member_add',
    commandType: 'sync/channels/add_member_requested',
    restMirror: { method: 'POST', path: '/sync/api/v1/channels/:channel_id/members' },
});

export const channelMembersListOp = createAsyncOp({
    name: 'sync/channel_members_list',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/channels/list_members_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/channels/:channel_id/members' },
});

export const channelNotificationsUpdateOp = createAsyncOp({
    name: 'sync/channel_notifications_update',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    successToastKey: 'sync:channels.toast_notifications_updated',
    errorToastKey: 'sync:channels.err_notifications',
    commandType: 'sync/channels/notification_settings_update_requested',
    restMirror: { method: 'PATCH', path: '/sync/api/v1/channels/:channel_id/notification-settings' },
});
