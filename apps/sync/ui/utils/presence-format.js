/**
 * Подписи онлайн / last seen для Sync (локаль из i18n).
 */
import { i18n, t } from '@platform/services/i18n/i18n.service.js';

/**
 * @param {boolean} isOnline
 * @param {string | null | undefined} lastSeenIso
 * @returns {string}
 */
export function formatPeerPresenceLine(isOnline, lastSeenIso) {
    if (isOnline) {
        return t('presence.online', {});
    }
    if (typeof lastSeenIso === 'string' && lastSeenIso !== '') {
        const d = new Date(lastSeenIso);
        if (Number.isNaN(d.getTime())) {
            throw new Error(t('presence.err_invalid_iso', {}));
        }
        const loc = i18n.getCurrentLocale() === 'ru' ? 'ru-RU' : 'en-US';
        const timeStr = d.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' });
        const startOfDay = (x) => {
            const t0 = new Date(x);
            return new Date(t0.getFullYear(), t0.getMonth(), t0.getDate()).getTime();
        };
        const today = new Date();
        const d0 = startOfDay(d);
        if (d0 === startOfDay(today)) {
            return t('presence.last_seen_today', { time: timeStr });
        }
        const y = new Date(today);
        y.setDate(y.getDate() - 1);
        if (d0 === startOfDay(y)) {
            return t('presence.last_seen_yesterday', { time: timeStr });
        }
        const dateStr = d.toLocaleDateString(loc, { day: 'numeric', month: 'short' });
        return t('presence.last_seen_date', { date: dateStr, time: timeStr });
    }
    return t('presence.offline', {});
}
