/**
 * Последний выбранный сервис (localStorage) и построение URL входа в сервис.
 */

export const LAST_VISITED_SERVICE_STORAGE_KEY = 'platform:last_service';

/** @type {readonly ['flows', 'crm', 'rag', 'sync', 'documents', 'frontend']} */
const ALLOWED_SERVICE_IDS = ['flows', 'crm', 'rag', 'sync', 'documents', 'frontend'];

const SERVICE_PORT_BY_ID = {
    flows: '8001',
    frontend: '8002',
    crm: '8003',
    rag: '8004',
    sync: '8005',
    documents: '8008',
};

/**
 * @param {string} hostname
 * @returns {boolean}
 */
function isLocalDevHost(hostname) {
    return (
        hostname === 'localhost' ||
        hostname === '127.0.0.1' ||
        hostname.endsWith('.lvh.me')
    );
}

/**
 * @param {string} serviceId
 * @returns {string}
 */
export function buildServiceEntryUrl(serviceId) {
    if (!ALLOWED_SERVICE_IDS.includes(serviceId)) {
        throw new Error(`Неизвестный сервис для перехода: ${serviceId}`);
    }

    const servicePath =
        serviceId === 'frontend' ? '/dashboard' : serviceId === 'documents' ? '/documents' : `/${serviceId}`;
    if (typeof window === 'undefined') {
        return servicePath;
    }

    if (!isLocalDevHost(window.location.hostname)) {
        return servicePath;
    }

    const targetPort = SERVICE_PORT_BY_ID[serviceId];
    if (!targetPort) {
        throw new Error(`Неизвестный сервис для перехода: ${serviceId}`);
    }

    if (window.location.port === targetPort) {
        return servicePath;
    }

    return `${window.location.protocol}//${window.location.hostname}:${targetPort}${servicePath}`;
}

/**
 * @param {string} id
 */
export function setLastVisitedService(id) {
    if (!ALLOWED_SERVICE_IDS.includes(id)) {
        throw new Error(`Недопустимый id сервиса: ${id}`);
    }
    window.localStorage.setItem(LAST_VISITED_SERVICE_STORAGE_KEY, id);
}

/**
 * @returns {'flows' | 'crm' | 'rag' | 'sync' | 'documents' | 'frontend' | null}
 */
export function getLastVisitedService() {
    const raw = window.localStorage.getItem(LAST_VISITED_SERVICE_STORAGE_KEY);
    if (raw === null || raw === '') {
        return null;
    }
    if (!ALLOWED_SERVICE_IDS.includes(raw)) {
        return null;
    }
    return /** @type {'flows' | 'crm' | 'rag' | 'sync' | 'documents' | 'frontend'} */ (raw);
}

/**
 * Из значения getBaseUrl() вида `/flows` или `/frontend` извлекает id сервиса.
 * @param {string} baseUrl
 * @returns {'flows' | 'crm' | 'rag' | 'sync' | 'documents' | 'frontend' | null}
 */
export function serviceIdFromBaseUrl(baseUrl) {
    const segment = String(baseUrl ?? '')
        .trim()
        .replace(/^\/+/, '')
        .split('/')[0];
    if (!segment) {
        return null;
    }
    if (!ALLOWED_SERVICE_IDS.includes(segment)) {
        return null;
    }
    return /** @type {'flows' | 'crm' | 'rag' | 'sync' | 'documents' | 'frontend'} */ (segment);
}

/**
 * Редирект с /dashboard в последний не-console сервис (flows, crm, rag, sync).
 * @returns {boolean} true если редирект выполнен
 */
export function replaceLocationToLastVisitedNonFrontendService() {
    const id = getLastVisitedService();
    if (!id || id === 'frontend') {
        return false;
    }
    const nonFrontend = ['flows', 'crm', 'rag', 'sync', 'documents'];
    if (!nonFrontend.includes(id)) {
        return false;
    }
    window.location.replace(buildServiceEntryUrl(id));
    return true;
}
