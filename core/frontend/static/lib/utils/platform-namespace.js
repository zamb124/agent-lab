/**
 * Текущий CRM/RAG namespace для HTTP X-Platform-Namespace.
 * Ключ localStorage совпадает с CRMStore (apps/crm/ui/store/crm.store.js).
 */

const LAST_NAMESPACE_STORAGE_KEY = 'crm:last-namespace-by-company';
const ALL_NAMESPACES_SENTINEL = '__ALL__';

/**
 * @param {string | null | undefined} companyId
 * @returns {string}
 */
export function getActivePlatformNamespaceName(companyId) {
    if (typeof companyId !== 'string' || companyId.trim().length === 0) {
        return 'default';
    }
    try {
        const raw = window.localStorage.getItem(LAST_NAMESPACE_STORAGE_KEY);
        if (!raw) {
            return 'default';
        }
        const map = JSON.parse(raw);
        if (!map || typeof map !== 'object' || Array.isArray(map)) {
            return 'default';
        }
        const v = map[companyId];
        if (typeof v !== 'string' || v.trim().length === 0) {
            return 'default';
        }
        if (v === ALL_NAMESPACES_SENTINEL) {
            return 'default';
        }
        return v.trim();
    } catch {
        return 'default';
    }
}

/**
 * @param {string | null | undefined} companyId
 * @param {string} namespaceName
 */
export function setActivePlatformNamespaceName(companyId, namespaceName) {
    if (typeof companyId !== 'string' || companyId.trim().length === 0) {
        throw new Error('setActivePlatformNamespaceName: companyId is required');
    }
    const name =
        typeof namespaceName === 'string' && namespaceName.trim().length > 0
            ? namespaceName.trim()
            : 'default';
    let map = {};
    try {
        const raw = window.localStorage.getItem(LAST_NAMESPACE_STORAGE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                map = parsed;
            }
        }
    } catch {
        map = {};
    }
    map[companyId.trim()] = name;
    window.localStorage.setItem(LAST_NAMESPACE_STORAGE_KEY, JSON.stringify(map));
    window.dispatchEvent(
        new CustomEvent('office-documents-list-reload', { bubbles: true }),
    );
}
