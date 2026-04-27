/**
 * Построение URL входа в сервисный UI (тот же контракт, что и в platform-user).
 */

const SERVICE_DEV_PORTS = Object.freeze({
    flows: '8001',
    frontend: '8002',
    crm: '8003',
    rag: '8004',
    sync: '8005',
    documents: '8008',
    litserve: '8014',
});

function isLocalHost(hostname) {
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
export function buildServiceEntryUrl(serviceId) {
    if (typeof serviceId !== 'string' || serviceId.length === 0) {
        throw new Error('buildServiceEntryUrl: serviceId required');
    }
    const servicePath =
        serviceId === 'frontend' ? '/dashboard' : serviceId === 'documents' ? '/documents' : `/${serviceId}`;
    const hostname = window.location.hostname;
    if (!isLocalHost(hostname)) {
        return servicePath;
    }
    const targetPort = SERVICE_DEV_PORTS[serviceId];
    if (!targetPort) {
        throw new Error(`buildServiceEntryUrl: unknown service id "${serviceId}"`);
    }
    if (window.location.port === targetPort) {
        return servicePath;
    }
    return `${window.location.protocol}//${hostname}:${targetPort}${servicePath}`;
}

export function isStandalonePwaMode() {
    const mq = window.matchMedia('(display-mode: standalone)');
    if (mq && mq.matches) return true;
    return window.navigator.standalone === true;
}
