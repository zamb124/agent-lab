/**
 * Хелперы mention Sync — рендер `@user_id` в тексте сообщения.
 *
 * Чистые функции без зависимостей. Заменяют любые `||`-фолбеки на явные
 * `typeof`-проверки.
 */

import { resolveDisplayName } from './sync-id-resolvers.js';

const SYNC_MENTION_IN_TEXT_RE = /@([a-zA-Z0-9_-]{6,})/g;

/**
 * Возвращает читабельную метку упоминания: имя участника, иначе сам user_id.
 */
export function mentionDisplayLabel(userId, members) {
    if (typeof userId !== 'string' || userId === '') return '';
    if (Array.isArray(members)) {
        for (const m of members) {
            if (m && typeof m === 'object' && m.user_id === userId) {
                return resolveDisplayName(m);
            }
        }
    }
    return userId;
}

/**
 * Превратить «сырое» @user_id в текстовый сниппет с подменой на имена.
 * Используется в превью каналов, поиске, last_message_preview.
 */
export function plainTextSnippetWithMentionLabels(text, members) {
    if (typeof text !== 'string') return '';
    if (text === '') return '';
    return text.replace(SYNC_MENTION_IN_TEXT_RE, (full, userId) => {
        const label = mentionDisplayLabel(userId, members);
        if (typeof label === 'string' && label !== '' && label !== userId) {
            return '@' + label;
        }
        return full;
    });
}

/**
 * Парсинг текста на массив сегментов: { kind: 'text'|'mention', value, userId? }.
 * Используется в bubble для рендера clickable @-чипов.
 */
export function parseMentionsToSegments(text, members) {
    if (typeof text !== 'string' || text === '') return [];
    const out = [];
    let lastIdx = 0;
    SYNC_MENTION_IN_TEXT_RE.lastIndex = 0;
    let match = SYNC_MENTION_IN_TEXT_RE.exec(text);
    while (match !== null) {
        const idx = match.index;
        if (idx > lastIdx) {
            out.push({ kind: 'text', value: text.slice(lastIdx, idx) });
        }
        const userId = match[1];
        out.push({
            kind: 'mention',
            value: '@' + mentionDisplayLabel(userId, members),
            userId,
        });
        lastIdx = idx + match[0].length;
        match = SYNC_MENTION_IN_TEXT_RE.exec(text);
    }
    if (lastIdx < text.length) {
        out.push({ kind: 'text', value: text.slice(lastIdx) });
    }
    return out;
}

/**
 * Извлечение списка user_id, упомянутых в тексте.
 */
export function extractMentionedUserIdsFromPlainText(text) {
    if (typeof text !== 'string' || text === '') return [];
    const out = new Set();
    SYNC_MENTION_IN_TEXT_RE.lastIndex = 0;
    let match = SYNC_MENTION_IN_TEXT_RE.exec(text);
    while (match !== null) {
        out.add(match[1]);
        match = SYNC_MENTION_IN_TEXT_RE.exec(text);
    }
    return Array.from(out);
}

export { SYNC_MENTION_IN_TEXT_RE };
