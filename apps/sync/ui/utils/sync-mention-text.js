/**
 * Упоминания в text/plain: UUID или platform user_id (например user_…, test_user_…).
 */

const UUID =
    '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const PLATFORM_USER = 'user_[a-zA-Z0-9]+';
const TEST_USER = 'test_user_[a-zA-Z0-9_]+';

/** Группа захвата: полный id после «@». */
export const SYNC_MENTION_ID_CAPTURE = `(?:${UUID}|${PLATFORM_USER}|${TEST_USER})`;

export const SYNC_MENTION_IN_TEXT_RE = new RegExp(`@(${SYNC_MENTION_ID_CAPTURE})`, 'gi');

/**
 * @param {string} t
 * @returns {string[]}
 */
export function extractMentionedUserIdsFromPlainText(t) {
    if (typeof t !== 'string' || t === '') return [];
    const seen = new Set();
    const out = [];
    const re = new RegExp(SYNC_MENTION_IN_TEXT_RE.source, SYNC_MENTION_IN_TEXT_RE.flags);
    let m;
    while ((m = re.exec(t)) !== null) {
        const id = m[1];
        if (!seen.has(id)) {
            seen.add(id);
            out.push(id);
        }
    }
    return out;
}

/**
 * @param {string} userId
 * @param {Array<{ user_id?: string, name?: string }> | undefined} membersList
 * @returns {string}
 */
export function mentionDisplayLabel(userId, membersList) {
    if (typeof userId !== 'string' || userId === '') return '?';
    const list = Array.isArray(membersList) ? membersList : [];
    const cm = list.find(c => c.user_id === userId);
    if (typeof cm?.name === 'string' && cm.name.trim() !== '') return cm.name.trim();
    return userId.length > 24 ? `${userId.slice(0, 22)}…` : userId;
}

/**
 * Текст для превью ответа: подставляет отображаемые имена вместо сырого id.
 * @param {string} body
 * @param {Array<{ user_id?: string, name?: string }> | undefined} membersList
 * @param {number} maxLen
 * @returns {string}
 */
export function plainTextSnippetWithMentionLabels(body, membersList, maxLen) {
    if (typeof body !== 'string' || body === '') return '';
    const re = new RegExp(SYNC_MENTION_IN_TEXT_RE.source, SYNC_MENTION_IN_TEXT_RE.flags);
    let out = '';
    let last = 0;
    let m;
    while ((m = re.exec(body)) !== null) {
        if (m.index > last) {
            out += body.slice(last, m.index);
        }
        const id = m[1];
        const label = mentionDisplayLabel(id, membersList);
        out += `@${label}`;
        last = m.index + m[0].length;
    }
    if (last < body.length) {
        out += body.slice(last);
    }
    const cap = typeof maxLen === 'number' && maxLen > 0 ? maxLen : 160;
    return out.length > cap ? `${out.slice(0, cap)}…` : out;
}
