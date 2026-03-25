/**
 * Подписи онлайн / last seen для Sync (локаль пользователя).
 * @param {boolean} isOnline
 * @param {string | null | undefined} lastSeenIso
 * @returns {string}
 */
export function formatPeerPresenceLine(isOnline, lastSeenIso) {
    if (isOnline) {
        return 'Онлайн';
    }
    if (typeof lastSeenIso === 'string' && lastSeenIso !== '') {
        const d = new Date(lastSeenIso);
        if (Number.isNaN(d.getTime())) {
            throw new Error('formatPeerPresenceLine: некорректный ISO last_seen_at.');
        }
        const timeStr = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
        const startOfDay = (x) => {
            const t = new Date(x);
            return new Date(t.getFullYear(), t.getMonth(), t.getDate()).getTime();
        };
        const today = new Date();
        const d0 = startOfDay(d);
        if (d0 === startOfDay(today)) {
            return `Был(а) в сети сегодня в ${timeStr}`;
        }
        const y = new Date(today);
        y.setDate(y.getDate() - 1);
        if (d0 === startOfDay(y)) {
            return `Был(а) в сети вчера в ${timeStr}`;
        }
        const dateStr = d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
        return `Был(а) в сети ${dateStr} в ${timeStr}`;
    }
    return 'Не в сети';
}
