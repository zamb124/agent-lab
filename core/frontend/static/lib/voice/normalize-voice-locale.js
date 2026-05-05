/**
 * Нормализует локаль UI для query `language=` voice WebSocket (ISO 639-1 / префикс BCP-47).
 * @param {string} locale
 * @returns {string}
 */
export function normalizeVoiceLocaleForWs(locale) {
    if (typeof locale !== 'string') {
        throw new Error('normalizeFlowVoiceSttLanguage: locale must be string');
    }
    const trimmed = locale.trim();
    if (trimmed === '') {
        throw new Error('normalizeFlowVoiceSttLanguage: locale required');
    }
    const lower = trimmed.toLowerCase();
    const dash = lower.indexOf('-');
    const under = lower.indexOf('_');
    let cut = lower.length;
    if (dash >= 0) {
        cut = Math.min(cut, dash);
    }
    if (under >= 0) {
        cut = Math.min(cut, under);
    }
    const base = lower.slice(0, cut);
    if (base.length < 2) {
        throw new Error('normalizeFlowVoiceSttLanguage: invalid locale');
    }
    return base;
}
