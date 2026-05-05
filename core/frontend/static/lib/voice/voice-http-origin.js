/**
 * HTTP-база голосового шлюза из базы flows A2A (`…/flows` → `…/voice`).
 * Используется во embed: страница виджета и origin API часто различаются.
 * @param {string} flowsBaseUrl - например https://host/flows
 * @returns {string}
 */
export function resolveVoiceHttpOriginFromFlowsBaseUrl(flowsBaseUrl) {
    if (typeof flowsBaseUrl !== 'string') {
        throw new TypeError('resolveVoiceHttpOriginFromFlowsBaseUrl: string required');
    }
    const root = flowsBaseUrl.trim().replace(/\/$/, '');
    if (root === '') {
        throw new Error('resolveVoiceHttpOriginFromFlowsBaseUrl: flowsBaseUrl is empty');
    }
    if (root.toLowerCase().endsWith('/flows')) {
        return `${root.slice(0, -'/flows'.length)}/voice`;
    }
    let parsed;
    try {
        parsed = new URL(root);
    } catch {
        throw new Error('resolveVoiceHttpOriginFromFlowsBaseUrl: invalid flowsBaseUrl');
    }
    return `${parsed.origin}/voice`;
}

/**
 * HTTP-оригин голосового шлюза (тот же host, путь `/voice`).
 * Переопределение: meta `platform-voice-origin`.
 * @returns {string}
 */
export function resolveVoiceHttpOrigin() {
    if (typeof document !== 'undefined') {
        const el = document.querySelector('meta[name="platform-voice-origin"]');
        if (el) {
            const raw = el.getAttribute('content');
            if (typeof raw === 'string') {
                const trimmed = raw.trim();
                if (trimmed !== '') {
                    return trimmed.replace(/\/$/, '');
                }
            }
        }
    }
    if (typeof window !== 'undefined' && window.location) {
        return `${window.location.protocol}//${window.location.host}/voice`;
    }
    return '';
}
