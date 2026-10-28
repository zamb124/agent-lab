/**
 * Presence Sync — typing-индикатор.
 *
 * Чистый `createSlice` без HTTP/WS: состояние derived из push
 * `sync/channel/typing` (через `extraReducer`).
 *
 * Online/last_seen — поля `CompanyMemberRead` фабрики `sync/company_members`.
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
    },
    extraEvents: {
        TYPING_PRUNE: 'typing_prune',
    },
    actions: {
        pruneTyping: 'typing_prune',
    },
    extraReducer: (state, event) => {
        if (event.type === 'sync/channel/typing') {
            const p = event.payload as Record<string, any> | null;
            if (!p || typeof p.channel_id !== 'string') return state;
            const typingByChannel = state.typingByChannel as Record<string, Record<string, { ts?: number; thread_id?: unknown }>>;
            const existing = typingByChannel[p.channel_id];
            const cur: Record<string, unknown> = (existing && typeof existing === 'object') ? existing : EMPTY_TYPING;
            const userId = p.user && p.user.user_id;
            if (typeof userId !== 'string') return state;
            const next: Record<string, unknown> = { ...cur };
            if (p.typing) {
                const threadId = typeof p.thread_id === 'string' ? p.thread_id : null;
                next[userId] = { thread_id: threadId, ts: Date.now() };
            } else {
                delete next[userId];
            }
            return {
                ...state,
                typingByChannel: Object.freeze({
                    ...typingByChannel,
                    [p.channel_id]: Object.freeze(next),
                }),
            };
        }
        if (event.type === 'sync/presence/typing_prune') {
            const now = Date.now();
            const next: Record<string, unknown> = {};
            let changed = false;
            const pruneChannel = state.typingByChannel as Record<string, Record<string, { ts?: number }>>;
            for (const [chId, peers] of Object.entries(pruneChannel)) {
                const filtered: Record<string, unknown> = {};
                for (const [uid, entry] of Object.entries(peers)) {
                    if (entry && typeof entry.ts === 'number' && now - entry.ts < TYPING_TTL_MS) {
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'sync/presence': typeof presenceResource;
    }
}
