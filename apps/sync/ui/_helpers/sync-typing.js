/**
 * Sync typing helpers — построение строки typing-индикатора.
 *
 * Вход: typingByChannel (slice presence), channelId, threadId,
 * myUserId (исключаем себя), members (для отображения имён), t.
 *
 * Возвращает строку или ''.
 */

import { resolveDisplayName } from './sync-id-resolvers.js';

const TYPING_TTL_MS = 6_000;

export function getTypingIndicatorLine({
    typingByChannel,
    channelId,
    threadId,
    myUserId,
    members,
    t,
}) {
    if (!typingByChannel || typeof typingByChannel !== 'object') return '';
    if (typeof channelId !== 'string' || channelId === '') return '';
    const peers = typingByChannel[channelId];
    if (!peers || typeof peers !== 'object') return '';
    const myId = typeof myUserId === 'string' ? myUserId : '';
    const wantThreadId = typeof threadId === 'string' && threadId !== '' ? threadId : null;
    const now = Date.now();
    const names = [];
    for (const [uid, entry] of Object.entries(peers)) {
        if (uid === myId) continue;
        if (!entry || typeof entry !== 'object') continue;
        if (typeof entry.ts !== 'number' || now - entry.ts >= TYPING_TTL_MS) continue;
        const peerThreadId = typeof entry.thread_id === 'string' && entry.thread_id !== '' ? entry.thread_id : null;
        if (wantThreadId !== peerThreadId) continue;
        const member = Array.isArray(members) ? members.find((m) => m && m.user_id === uid) : null;
        const name = resolveDisplayName(member && typeof member === 'object' ? member : { user_id: uid });
        if (name === '') continue;
        names.push(name);
    }
    if (names.length === 0) return '';
    if (names.length === 1) return t('sync_store.typing_one', { name: names[0] });
    if (names.length === 2) return t('sync_store.typing_two', { name1: names[0], name2: names[1] });
    return t('sync_store.typing_many', { name1: names[0], name2: names[1], n: names.length - 2 });
}

export { TYPING_TTL_MS };
