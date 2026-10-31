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
import { isPlatformEventType, isPlainRecord } from '@platform/lib/events/payload.js';

const TYPING_TTL_MS = 6_000;

function typingMap(value: unknown): Record<string, unknown> {
    if (!isPlainRecord(value)) {
        throw new Error('sync/presence: typingByChannel must be an object');
    }
    const row: Record<string, unknown> = {};
    for (const [key, field] of Object.entries(value)) row[key] = field;
    return row;
}

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
        if (isPlatformEventType(event, 'sync/channel/typing')) {
            const p = event.payload;
            const channelId = p.channel_id;
            const typingByChannel = typingMap(state.typingByChannel);
            const existing = typingByChannel[channelId];
            if (existing != null && !isPlainRecord(existing)) {
                throw new Error('sync/presence: channel typing must be an object');
            }
            const cur = isPlainRecord(existing) ? existing : {};
            const userId = p.user.user_id;
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
                    [channelId]: Object.freeze(next),
                }),
            };
        }
        if (event.type === 'sync/presence/typing_prune') {
            const now = Date.now();
            const next: Record<string, unknown> = {};
            let changed = false;
            const pruneChannel = typingMap(state.typingByChannel);
            for (const [chId, peersValue] of Object.entries(pruneChannel)) {
                if (!isPlainRecord(peersValue)) {
                    throw new Error('sync/presence: channel typing must be an object');
                }
                const filtered: Record<string, unknown> = {};
                for (const [uid, entry] of Object.entries(peersValue)) {
                    if (isPlainRecord(entry) && typeof entry.ts === 'number' && now - entry.ts < TYPING_TTL_MS) {
                        filtered[uid] = entry;
                    } else {
                        changed = true;
                    }
                }
                if (Object.keys(filtered).length > 0) {
                    next[chId] = Object.freeze(filtered);
                } else if (Object.keys(peersValue).length > 0) {
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
