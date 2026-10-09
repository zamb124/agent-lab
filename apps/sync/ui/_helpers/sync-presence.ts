/**
 * Хелперы presence Sync — отображение online/last_seen из CompanyMemberRead.
 *
 * Чистые функции. `t` (translator) передаётся аргументом, чтобы helpers
 * оставались UI-нейтральными и тестируемыми.
 */

export function findCompanyMember(members: unknown, userId: unknown) {
    if (typeof userId !== 'string' || userId === '') return null;
    if (!Array.isArray(members)) return null;
    for (const member of members) {
        if (member && typeof member === 'object' && member.user_id === userId) {
            return member;
        }
    }
    return null;
}

export function isOnline(member: Record<string, unknown> | null | undefined) {
    return Boolean(member && member.is_online === true);
}

function _formatTime(date: Date) {
    const hh = String(date.getHours()).padStart(2, '0');
    const mm = String(date.getMinutes()).padStart(2, '0');
    return `${hh}:${mm}`;
}

function _formatDate(date: Date) {
    const d = String(date.getDate()).padStart(2, '0');
    const m = String(date.getMonth() + 1).padStart(2, '0');
    return `${d}.${m}`;
}

/**
 * Человеко-читаемый last_seen: "Был(а) сегодня в HH:mm" / "вчера в HH:mm" / "DD.MM в HH:mm".
 */
export function formatLastSeen(iso: unknown, t: (key: string, vars?: Record<string, string | number> | null) => string) {
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
export function getPeerPresenceSubtitle(member: Record<string, unknown> | null | undefined, t: (key: string, vars?: Record<string, string | number> | null) => string) {
    if (!member || typeof member !== 'object') return '';
    if (member.is_online === true) return t('presence.online');
    if (typeof member.last_seen_at === 'string' && member.last_seen_at !== '') {
        return formatLastSeen(member.last_seen_at, t);
    }
    return t('presence.offline');
}
