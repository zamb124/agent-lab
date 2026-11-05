/**
 * Построение URL входа в сервисный UI (тот же контракт, что и в platform-user).
 */

const SERVICE_DEV_PORTS = Object.freeze({
    flows: '8001',
    frontend: '8002',
    crm: '8003',
    rag: '8004',
    sync: '8005',
    worktracker: '8021',
    documents: '8008',
    wiki: '8023',
    shop: '8027',
    geo: '8028',
    litserve: '8014',
    grafana: '3000',
});

function devPort(serviceId: string): string {
    switch (serviceId) {
        case 'flows': return SERVICE_DEV_PORTS.flows;
        case 'frontend': return SERVICE_DEV_PORTS.frontend;
        case 'crm': return SERVICE_DEV_PORTS.crm;
        case 'rag': return SERVICE_DEV_PORTS.rag;
        case 'sync': return SERVICE_DEV_PORTS.sync;
        case 'worktracker': return SERVICE_DEV_PORTS.worktracker;
        case 'documents': return SERVICE_DEV_PORTS.documents;
        case 'wiki': return SERVICE_DEV_PORTS.wiki;
        case 'shop': return SERVICE_DEV_PORTS.shop;
        case 'geo': return SERVICE_DEV_PORTS.geo;
        case 'litserve': return SERVICE_DEV_PORTS.litserve;
        case 'grafana': return SERVICE_DEV_PORTS.grafana;
        default:
            throw new Error(`buildServiceEntryUrl: unknown service id "${serviceId}"`);
    }
}

function navigatorStandalone(navigator: Navigator): boolean {
    const nav: unknown = navigator;
    if (typeof nav !== 'object' || nav === null) {
        throw new Error('isStandalonePwaMode: navigator is required');
    }
    if (!('standalone' in nav)) return false;
    return nav.standalone === true;
}

function isLocalHost(hostname: string): boolean {
    return (
        hostname === 'localhost'
        || hostname === '127.0.0.1'
        || hostname.endsWith('.localhost')
        || hostname.endsWith('.lvh.me')
    );
}

/**
 * @param {string} serviceId
 * @returns {string}
 */
export function buildServiceEntryUrl(serviceId: string): string {
    if (typeof serviceId !== 'string' || serviceId.length === 0) {
        throw new Error('buildServiceEntryUrl: serviceId required');
    }
    if (serviceId === 'grafana') {
        const hostname = window.location.hostname;
        if (isLocalHost(hostname)) {
            return `${window.location.protocol}//${hostname}:${SERVICE_DEV_PORTS.grafana}/`;
        }
        const hostParts = hostname.split('.');
        if (hostParts.length >= 2) {
            const baseDomain = hostParts.slice(-2).join('.');
            return `${window.location.protocol}//grafana.${baseDomain}/`;
        }
        return `${window.location.protocol}//grafana.${hostname}/`;
    }
    const servicePath =
        serviceId === 'frontend' ? '/dashboard' : serviceId === 'documents' ? '/documents' : `/${serviceId}`;
    const hostname = window.location.hostname;
    if (!isLocalHost(hostname)) {
        return servicePath;
    }
    const targetPort = devPort(serviceId);
    if (window.location.port === targetPort) {
        return servicePath;
    }
    return `${window.location.protocol}//${hostname}:${targetPort}${servicePath}`;
}

/**
 * @param {string} catalogId
 * @param {string} namespace
 * @returns {string}
 */
export function buildDocumentsCatalogEntryUrl(catalogId: string, namespace: string): string {
    if (typeof catalogId !== 'string' || catalogId.length === 0) {
        throw new Error('buildDocumentsCatalogEntryUrl: catalog_id required');
    }
    if (typeof namespace !== 'string' || namespace.length === 0) {
        throw new Error('buildDocumentsCatalogEntryUrl: namespace required');
    }
    const base = buildServiceEntryUrl('documents');
    const url = new URL(base, window.location.origin);
    url.searchParams.set('namespace', namespace);
    url.searchParams.set('catalog_id', catalogId);
    if (base.startsWith('/')) {
        return `${url.pathname}${url.search}`;
    }
    return url.toString();
}

/**
 * @param {string} path — абсолютный path на frontend (например `/agent`)
 * @returns {string}
 */
export function buildFrontendPublicPath(path: string): string {
    if (typeof path !== 'string' || path.length === 0 || !path.startsWith('/')) {
        throw new Error('buildFrontendPublicPath: path must be a non-empty string starting with /');
    }
    const hostname = window.location.hostname;
    if (!isLocalHost(hostname)) {
        return path;
    }
    const targetPort = SERVICE_DEV_PORTS.frontend;
    if (window.location.port === targetPort) {
        return path;
    }
    return `${window.location.protocol}//${hostname}:${targetPort}${path}`;
}

export function isStandalonePwaMode(): boolean {
    const mq = window.matchMedia('(display-mode: standalone)');
    if (mq && mq.matches) return true;
    return navigatorStandalone(window.navigator);
}
