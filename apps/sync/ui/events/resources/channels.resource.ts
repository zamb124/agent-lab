/**
 * Каналы Sync — каналы (direct/group/topic).
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
import type { ResourceItem } from '@platform/lib/events/factories/resource-collection.js';
import type { SyncChannelsSlice } from '../sync.types.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function eventRecord(payload: unknown): Record<string, unknown> | null {
    return isPlainRecord(payload) ? payload : null;
}

const EMPTY_TYPING = Object.freeze({});

function _mergeChannelReadIntoItems(state: SyncChannelsSlice, result: Record<string, any> | null | undefined) {
    if (!result || typeof result !== 'object' || typeof result.channel_id !== 'string' || result.channel_id === '') {
        return state;
    }
    const idx = state.items.findIndex((x) => x.channel_id === result.channel_id);
    if (idx === -1) return state;
    const merged = _normalizeChannel({ ...state.items[idx], ...result });
    const items = state.items.map((x, i) => (i === idx ? merged : x));
    return { ...state, items: Object.freeze(items) };
}

function _normalizeChannel(channel: ResourceItem): ResourceItem {
    if (!channel || typeof channel !== 'object') return channel;
    const unread = typeof channel.unread_count === 'number' ? channel.unread_count : 0;
    const mention = typeof channel.mention_unread_count === 'number' ? channel.mention_unread_count : 0;
    const preview = typeof channel.last_message_preview === 'string' ? channel.last_message_preview : '';
    const pinnedIds = Array.isArray(channel.pinned_message_ids) ? channel.pinned_message_ids : [];
    return Object.freeze({
        ...channel,
        unread_count: unread,
        mention_unread_count: mention,
        last_message_preview: preview,
        pinned_message_ids: Object.freeze(pinnedIds.slice()),
    });
}

export const channelsResource = createResourceCollection({
    name: 'sync/channels',
    baseUrl: '/sync/api/v1/channels',
    idField: 'channel_id',
    operations: ['list', 'create'],
    transport: 'ws',
    wsTimeoutMs: 5_000,
    toastKeys: {
        create: 'sync:channels.toast_created',
        create_error: 'sync:channels.err_create',
    },
    mapItem: _normalizeChannel,
    extraInitial: {
        selectedChannelId: null,
        readByChannelUser: Object.freeze({}),
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
    extraReducer: (state: SyncChannelsSlice, event, events) => {
        const s = state;
        switch (event.type) {
            case 'sync/context/company_cleared': {
                return {
                    ...s,
                    items: Object.freeze([]),
                    byId: Object.freeze({}),
                    loading: false,
                    error: null,
                    busyIds: Object.freeze({}),
                    lastError: Object.freeze({}),
                    selectedChannelId: null,
                    readByChannelUser: Object.freeze({}),
                    typingByChannel: Object.freeze({}),
                    membersByChannel: Object.freeze({}),
                };
            }
            case 'sync/channels/channel_selected': {
                const p = eventRecord(event.payload);
                const channelId = p !== null && typeof p.channelId === 'string' ? p.channelId : null;
                return { ...s, selectedChannelId: channelId };
            }
            case 'sync/channel/created': {
                const raw = eventRecord(event.payload);
                if (raw === null || typeof raw.channel_id !== 'string') return state;
                if (s.items.some((x) => x.channel_id === raw.channel_id)) return state;
                const item = _normalizeChannel(raw);
                return { ...s, items: Object.freeze([...s.items, item]) };
            }
            case 'sync/channel/read_updated': {
                const p = eventRecord(event.payload);
                if (p === null || typeof p.channel_id !== 'string') return state;
                if (typeof p.read_at !== 'string') return state;
                if (typeof p.reader_user_id !== 'string' || p.reader_user_id === '') return state;
                const cur = s.readByChannelUser[p.channel_id];
                const channelMap = (cur && typeof cur === 'object') ? { ...cur } : {};
                channelMap[p.reader_user_id] = p.read_at;
                return {
                    ...s,
                    readByChannelUser: Object.freeze({
                        ...s.readByChannelUser,
                        [p.channel_id]: Object.freeze(channelMap),
                    }),
                };
            }
            case 'sync/channel/typing': {
                const p = eventRecord(event.payload);
                if (p === null || typeof p.channel_id !== 'string') return state;
                const existing = s.typingByChannel[p.channel_id];
                const cur = existing === undefined ? EMPTY_TYPING : existing;
                const user = isPlainRecord(p.user) ? p.user : null;
                const userId = user !== null ? user.user_id : undefined;
                if (typeof userId !== 'string') return state;
                const next: Record<string, { thread_id: string | null; ts: number }> = { ...cur };
                if (p.typing) {
                    const threadId = typeof p.thread_id === 'string' ? p.thread_id : null;
                    next[userId] = { thread_id: threadId, ts: Date.now() };
                } else {
                    delete next[userId];
                }
                return {
                    ...s,
                    typingByChannel: Object.freeze({
                        ...s.typingByChannel,
                        [p.channel_id]: Object.freeze(next),
                    }),
                };
            }
            case 'sync/channel/member_added': {
                const p = eventRecord(event.payload);
                if (p === null || typeof p.channel_id !== 'string') return state;
                const cur = s.membersByChannel[p.channel_id];
                if (!Array.isArray(cur)) return state;
                if (cur.some((m) => m.user_id === p.added_user_id)) return state;
                return {
                    ...s,
                    membersByChannel: Object.freeze({
                        ...s.membersByChannel,
                        [p.channel_id]: Object.freeze([...cur, { user_id: p.added_user_id }]),
                    }),
                };
            }
            case 'sync/channel/pins_changed': {
                const p = eventRecord(event.payload);
                if (p === null || typeof p.channel_id !== 'string') return state;
                const idx = s.items.findIndex((x) => x.channel_id === p.channel_id);
                if (idx === -1) return state;
                const items = s.items.map((x, i) => (i === idx ? _normalizeChannel({ ...x, ...p }) : x));
                return { ...s, items: Object.freeze(items) };
            }
            case 'sync/channel_update/succeeded':
            case 'sync/channel_notifications_update/succeeded':
            case 'sync/messages_pin/succeeded': {
                const payload = eventRecord(event.payload);
                const result = payload !== null && isPlainRecord(payload.result) ? payload.result : null;
                return _mergeChannelReadIntoItems(s, result);
            }
            case 'sync/message/created': {
                const m = eventRecord(event.payload);
                if (m === null || typeof m.channel_id !== 'string') return state;
                const idx = s.items.findIndex((x) => x.channel_id === m.channel_id);
                if (idx === -1) return state;
                const channel = s.items[idx];
                if (channel === undefined) return state;
                const isSelected = s.selectedChannelId === m.channel_id;
                const channelPreview = typeof channel.last_message_preview === 'string' ? channel.last_message_preview : '';
                const preview = typeof m.preview === 'string' ? m.preview
                    : (typeof m.last_message_preview === 'string' ? m.last_message_preview : channelPreview);
                const channelLastAt = typeof channel.last_message_at === 'string' ? channel.last_message_at : '';
                const lastAt = typeof m.sent_at === 'string' ? m.sent_at : channelLastAt;
                const unread = typeof channel.unread_count === 'number' ? channel.unread_count : 0;
                const mentionUnread = typeof channel.mention_unread_count === 'number' ? channel.mention_unread_count : 0;
                const next: Record<string, unknown> = {
                    ...channel,
                    last_message_preview: preview,
                    last_message_at: lastAt,
                };
                if (!isSelected && typeof m.local_id !== 'string') {
                    next.unread_count = unread + 1;
                    if (Array.isArray(m.mentioned_user_ids) && m.mentioned_user_ids.length > 0) {
                        next.mention_unread_count = mentionUnread + 1;
                    }
                }
                const items = s.items.map((x, i) => (i === idx ? _normalizeChannel(next) : x));
                return { ...s, items: Object.freeze(items) };
            }
            case 'sync/channels/own_read_set': {
                const p = eventRecord(event.payload);
                if (p === null || typeof p.channelId !== 'string' || p.channelId === '') return state;
                const idx = s.items.findIndex((x) => x.channel_id === p.channelId);
                if (idx === -1) return state;
                const channel = s.items[idx];
                if (channel === undefined) return state;
                if (channel.unread_count === 0 && channel.mention_unread_count === 0) return state;
                const items = s.items.map((x, i) => (i === idx
                    ? _normalizeChannel({ ...x, unread_count: 0, mention_unread_count: 0 })
                    : x));
                return { ...s, items: Object.freeze(items) };
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
        const p = eventRecord(event.payload);
        if (p === null || typeof p.channel_id !== 'string' || p.channel_id === '') return;
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

export const channelUpdateOp = createAsyncOp({
    name: 'sync/channel_update',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    successToastKey: 'sync:channels.toast_updated',
    errorToastKey: 'sync:channels.err_update',
    commandType: 'sync/channels/update_requested',
    restMirror: { method: 'PATCH', path: '/sync/api/v1/channels/:channel_id' },
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'sync/channels': typeof channelsResource;
        'sync/channel_mark_read': typeof channelMarkReadOp;
        'sync/channel_typing': typeof channelTypingOp;
        'sync/channel_update': typeof channelUpdateOp;
        'sync/channel_add_member': typeof channelAddMemberOp;
        'sync/channel_members_list': typeof channelMembersListOp;
        'sync/channel_notifications_update': typeof channelNotificationsUpdateOp;
    }
}
