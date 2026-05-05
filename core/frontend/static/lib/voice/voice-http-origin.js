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
