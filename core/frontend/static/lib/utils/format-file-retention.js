/**
 * Оставшееся время жизни файла по expires_at (FileRecord).
 *
 * @param {string | null | undefined} expiresAtIso — ISO datetime; null/undefined/'' = permanent.
 * @param {string} locale — BCP 47, из state.i18n.locale.
 * @param {number} [nowMs] — для тестов.
 * @returns {'permanent' | 'expired' | string}
 */
export function formatFileRetentionRemaining(expiresAtIso, locale, nowMs = Date.now()) {
    if (expiresAtIso === null || expiresAtIso === undefined || expiresAtIso === '') {
        return 'permanent';
    }
    if (typeof locale !== 'string' || locale.length === 0) {
        throw new Error('formatFileRetentionRemaining: locale required');
    }
    const expiresMs = Date.parse(expiresAtIso);
    if (!Number.isFinite(expiresMs)) {
        throw new Error('formatFileRetentionRemaining: invalid expiresAtIso');
    }
    const remainingSec = Math.floor((expiresMs - nowMs) / 1000);
    if (remainingSec <= 0) {
        return 'expired';
    }
    const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'always', style: 'short' });
    if (remainingSec >= 86400) {
        return rtf.format(Math.ceil(remainingSec / 86400), 'day');
    }
    if (remainingSec >= 3600) {
        return rtf.format(Math.ceil(remainingSec / 3600), 'hour');
    }
    return rtf.format(Math.max(1, Math.ceil(remainingSec / 60)), 'minute');
}
