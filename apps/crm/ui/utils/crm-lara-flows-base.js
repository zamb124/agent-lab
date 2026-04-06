/**
 * Единственная CRM-специфичная настройка встраиваемого чата: как достучаться до flows
 * и какие заголовки добавить к A2A (как если бы CRM был внешним сайтом).
 *
 * URL: meta name="humanitec-flows-base-url" или dev :8003 → :8001/flows, иначе origin + /flows.
 * Bearer (опционально): meta name="humanitec-flows-bearer-token" content="jwt..." — если flows на
 * другом домене и cookie сессии туда не доходит; иначе достаточно credentials при том же hostname
 * (в т.ч. разные порты: один site для SameSite=Lax, см. flowsEmbedShouldSendCredentials).
 */

/**
 * @returns {string} Базовый URL flows без завершающего слэша
 */
export function resolveCrmLaraFlowsBaseUrl() {
    const meta = document.querySelector('meta[name="humanitec-flows-base-url"]');
    const raw = meta?.getAttribute('content');
    if (raw != null && String(raw).trim() !== '') {
        return String(raw).trim().replace(/\/$/, '');
    }
    const { protocol, hostname, port } = window.location;
    if (port === '8003') {
        return `${protocol}//${hostname}:8001/flows`.replace(/\/$/, '');
    }
    return `${window.location.origin}/flows`.replace(/\/$/, '');
}

/**
 * Включать fetch credentials к flows: тот же origin или та же схема + hostname (другой порт).
 * Иначе при dev CRM :8003 и flows :8001 cookie auth_token не уходит и A2A даёт 401.
 *
 * @param {string} flowsBaseUrl
 * @returns {boolean}
 */
export function flowsEmbedShouldSendCredentials(flowsBaseUrl) {
    if (!flowsBaseUrl || typeof flowsBaseUrl !== 'string') {
        return false;
    }
    try {
        const u = new URL(flowsBaseUrl, window.location.href);
        if (u.origin === window.location.origin) {
            return true;
        }
        return u.protocol === window.location.protocol && u.hostname === window.location.hostname;
    } catch {
        return false;
    }
}

/**
 * Заголовки для fetch A2A (например Authorization). Пустой объект — только cookie при use-credentials.
 *
 * @returns {Promise<Record<string, string>>}
 */
export async function resolveFlowsEmbedAuthHeaders() {
    const meta = document.querySelector('meta[name="humanitec-flows-bearer-token"]');
    const raw = meta?.getAttribute('content');
    if (raw != null && String(raw).trim() !== '') {
        return { Authorization: `Bearer ${String(raw).trim()}` };
    }
    return {};
}
