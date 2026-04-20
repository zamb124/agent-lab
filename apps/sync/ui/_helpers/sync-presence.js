/**
 * Sync presence helpers — отображение online/last_seen.
 *
 * Чистые функции. `t` (translator) передаётся аргументом, чтобы helpers
 * оставались UI-нейтральными и тестируемыми.
 */

export function isOnline(presenceByUserId, userId) {
    if (typeof userId !== 'string' || userId === '') return false;
    if (!presenceByUserId || typeof presenceByUserId !== 'object') return false;
    const entry = presenceByUserId[userId];
    if (!entry || typeof entry !== 'object') return false;
    return entry.online === true;
}

function _formatTime(date) {
    const hh = String(date.getHours()).padStart(2, '0');
    const mm = String(date.getMinutes()).padStart(2, '0');
    return `${hh}:${mm}`;
}

function _formatDate(date) {
    const d = String(date.getDate()).padStart(2, '0');
    const m = String(date.getMonth() + 1).padStart(2, '0');
    return `${d}.${m}`;
}

/**
 * Человеко-читаемый last_seen: "Был(а) сегодня в HH:mm" / "вчера в HH:mm" / "DD.MM в HH:mm".
 */
export function formatLastSeen(iso, t) {
    if (typeof iso !== 'string' || iso === '') return '';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '';
    const now = new Date();
    const sameDay = date.toDateString() === now.toDateString();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday = date.toDateString() === yesterday.toDateString();
    const time = _formatTime(date);
    if (sameDay) return t('presence.last_seen_today', { time });
    if (isYesterday) return t('presence.last_seen_yesterday', { time });
    return t('presence.last_seen_date', { date: _formatDate(date), time });
}

/**
 * Подзаголовок для DM-собеседника: "онлайн" или человеко-читаемый last_seen.
 */
export function getPeerPresenceSubtitle(presenceByUserId, userId, t) {
    if (typeof userId !== 'string' || userId === '') return '';
    if (!presenceByUserId || typeof presenceByUserId !== 'object') return '';
    const entry = presenceByUserId[userId];
    if (!entry || typeof entry !== 'object') return '';
    if (entry.online === true) return t('presence.online');
    if (typeof entry.last_seen_at === 'string' && entry.last_seen_at !== '') {
        return formatLastSeen(entry.last_seen_at, t);
    }
    return t('presence.offline');
}
