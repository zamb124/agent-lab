/**
 * Sync Presence — typing-индикатор и user.presence (online/last_seen).
 *
 * Чистый `createSlice` без HTTP/WS: состояние derived из push-событий
 * `sync/channel/typing` и `sync/presence/changed` (через `extraReducer`).
 *
 * Локальный action `pruneTyping` используется TTL-таймером, чтобы убрать
 * устаревшие typing-записи (>= TYPING_TTL_MS).
 *
 * `notifyTyping`-команда (отправка факта набора в backend) — отдельная
 * `sync/channel_typing` фабрика в `channels.resource.js` с
 * `transport: 'ws'` + `commandType: 'sync/channels/typing_requested'`.
 */

import { createSlice } from '@platform/lib/events/index.js';

const TYPING_TTL_MS = 6_000;
const EMPTY_TYPING = Object.freeze({});

export const presenceResource = createSlice({
    name: 'sync/presence',
    extraInitial: {
        typingByChannel: Object.freeze({}),
        presenceByUserId: Object.freeze({}),
    },
    extraEvents: {
        TYPING_PRUNE: 'typing_prune',
    },
    actions: {
        pruneTyping: 'typing_prune',
    },
    extraReducer: (state, event) => {
        if (event.type === 'sync/channel/typing') {
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
        if (event.type === 'sync/presence/changed') {
            const p = event.payload;
            if (!p || typeof p.user_id !== 'string') return state;
            const lastSeenAt = (typeof p.last_seen_at === 'string' && p.last_seen_at !== '') ? p.last_seen_at : null;
            return {
                ...state,
                presenceByUserId: Object.freeze({
                    ...state.presenceByUserId,
                    [p.user_id]: {
                        online: Boolean(p.online),
                        last_seen_at: lastSeenAt,
                    },
                }),
            };
        }
        if (event.type === 'sync/presence/typing_prune') {
            const now = Date.now();
            const next = {};
            let changed = false;
            for (const [chId, peers] of Object.entries(state.typingByChannel)) {
                const filtered = {};
                for (const [uid, entry] of Object.entries(peers)) {
                    if (entry && now - entry.ts < TYPING_TTL_MS) {
                        filtered[uid] = entry;
                    } else {
                        changed = true;
                    }
                }
                if (Object.keys(filtered).length > 0) {
                    next[chId] = Object.freeze(filtered);
                } else if (Object.keys(peers).length > 0) {
                    changed = true;
                }
            }
            if (!changed) return state;
            return { ...state, typingByChannel: Object.freeze(next) };
        }
        return state;
    },
});

export const TYPING_PRUNE_INTERVAL_MS = TYPING_TTL_MS;
