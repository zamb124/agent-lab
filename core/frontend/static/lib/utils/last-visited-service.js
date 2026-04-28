/**
 * Последний выбранный сервис (localStorage) и построение URL входа в сервис.
 */

export const LAST_VISITED_SERVICE_STORAGE_KEY = 'platform:last_service';

/** Query на /dashboard после принятия инвайта: не уходить в last-visited sync/crm и т.д. */
export const INVITE_DASHBOARD_QUERY = 'from_invite';

/** Query после OAuth/демо-логина: один раз уйти в last-visited не-console сервис, если сохранён. */
export const POST_LOGIN_DASHBOARD_QUERY = 'post_login';

/** @param {Location | URL} loc */
export function hasInviteDashboardQuery(loc) {
    if (typeof URL === 'undefined') {
        return false;
    }
    const u = loc instanceof URL ? loc : new URL(loc.href);
    return u.searchParams.get(INVITE_DASHBOARD_QUERY) === '1';
}

/**
 * Убирает from_invite=1 из URL без перезагрузки.
 * @param {Location} [loc]
 */
export function stripInviteDashboardQuery(loc) {
    if (typeof window === 'undefined' || typeof URL === 'undefined') {
        return;
    }
    const ref = loc ?? window.location;
    const u = new URL(ref.href);
    if (u.searchParams.get(INVITE_DASHBOARD_QUERY) !== '1') {
        return;
    }
    u.searchParams.delete(INVITE_DASHBOARD_QUERY);
    const next = `${u.pathname}${u.search}${u.hash}`;
    window.history.replaceState(null, '', next);
}

/** @param {Location | URL} loc */
export function hasPostLoginDashboardQuery(loc) {
    if (typeof URL === 'undefined') {
        return false;
    }
    const u = loc instanceof URL ? loc : new URL(loc.href);
    return u.searchParams.get(POST_LOGIN_DASHBOARD_QUERY) === '1';
}

/**
 * Убирает post_login=1 из URL без перезагрузки.
 * @param {Location} [loc]
 */
export function stripPostLoginDashboardQuery(loc) {
    if (typeof window === 'undefined' || typeof URL === 'undefined') {
        return;
    }
    const ref = loc ?? window.location;
    const u = new URL(ref.href);
    if (u.searchParams.get(POST_LOGIN_DASHBOARD_QUERY) !== '1') {
        return;
    }
    u.searchParams.delete(POST_LOGIN_DASHBOARD_QUERY);
    const next = `${u.pathname}${u.search}${u.hash}`;
    window.history.replaceState(null, '', next);
}

/** @type {readonly ['flows', 'crm', 'rag', 'sync', 'documents', 'frontend']} */
const ALLOWED_SERVICE_IDS = ['flows', 'crm', 'rag', 'sync', 'documents', 'frontend'];

const SERVICE_PORT_BY_ID = {
    flows: '8001',
    frontend: '8002',
    crm: '8003',
    rag: '8004',
    sync: '8005',
    documents: '8002',
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
 * Возвращает URL входа в последний посещённый сервис.
 * Если сервис не сохранён — возвращает fallback-путь.
 * @param {{ fallbackPath?: string }} [options]
 * @returns {string}
 */
export function getLastVisitedServiceEntryUrl(options = {}) {
    const { fallbackPath = '/select-company' } = options;
    const id = getLastVisitedService();
    if (!id) {
        return fallbackPath;
    }
    return buildServiceEntryUrl(id);
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
 * Вызывать только при открытии /dashboard с query post_login=1 после OAuth/демо-логина.
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
