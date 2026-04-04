/**
 * Текущий CRM/RAG namespace для HTTP X-Platform-Namespace.
 * Ключ localStorage совпадает с CRMStore (apps/crm/ui/store/crm.store.js).
 */

const LAST_NAMESPACE_STORAGE_KEY = 'crm:last-namespace-by-company';
const ALL_NAMESPACES_SENTINEL = '__ALL__';

/**
 * @returns {Record<string, string> | null}
 */
function readNamespaceMap() {
    try {
        const raw = window.localStorage.getItem(LAST_NAMESPACE_STORAGE_KEY);
        if (!raw) {
            return null;
        }
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            return null;
        }
        return parsed;
    } catch {
        return null;
    }
}

/**
 * Режим сайдбара как в CRM: «все пространства» (пустое значение в select) или конкретное имя.
 *
 * @param {string | null | undefined} companyId
 * @returns {'all' | string}
 */
export function getPlatformNamespaceSidebarSelection(companyId) {
    if (typeof companyId !== 'string' || companyId.trim().length === 0) {
        return 'all';
    }
    const map = readNamespaceMap();
    if (!map) {
        return 'all';
    }
    const v = map[companyId.trim()];
    if (v === ALL_NAMESPACES_SENTINEL) {
        return 'all';
    }
    if (typeof v !== 'string' || v.trim().length === 0) {
        return 'all';
    }
    return v.trim();
}

/**
 * Сохранить выбор из сайдбара: пустая строка / null — как «Все» в NetWorkle (`__ALL__`).
 *
 * @param {string | null | undefined} companyId
 * @param {string | null | undefined} rawName
 */
export function setPlatformNamespaceSelection(companyId, rawName) {
    if (typeof companyId !== 'string' || companyId.trim().length === 0) {
        throw new Error('setPlatformNamespaceSelection: companyId is required');
    }
    const cid = companyId.trim();
    const useAll =
        rawName === null ||
        rawName === undefined ||
        (typeof rawName === 'string' && rawName.trim().length === 0);
    const value = useAll ? ALL_NAMESPACES_SENTINEL : rawName.trim();
    const existing = readNamespaceMap();
    const map = existing ? { ...existing } : {};
    map[cid] = value;
    window.localStorage.setItem(LAST_NAMESPACE_STORAGE_KEY, JSON.stringify(map));
    window.dispatchEvent(new CustomEvent('office-documents-list-reload', { bubbles: true }));
}

/**
 * @param {string | null | undefined} companyId
 * @returns {string}
 */
export function getActivePlatformNamespaceName(companyId) {
    if (typeof companyId !== 'string' || companyId.trim().length === 0) {
        return 'default';
    }
    const map = readNamespaceMap();
    if (!map) {
        return 'default';
    }
    const v = map[companyId.trim()];
    if (typeof v !== 'string' || v.trim().length === 0) {
        return 'default';
    }
    if (v === ALL_NAMESPACES_SENTINEL) {
        return 'default';
    }
    return v.trim();
}

/**
 * @param {string | null | undefined} companyId
 * @param {string} namespaceName
 */
export function setActivePlatformNamespaceName(companyId, namespaceName) {
    if (typeof companyId !== 'string' || companyId.trim().length === 0) {
        throw new Error('setActivePlatformNamespaceName: companyId is required');
    }
    if (typeof namespaceName !== 'string' || namespaceName.trim().length === 0) {
        throw new Error('setActivePlatformNamespaceName: namespaceName is required');
    }
    setPlatformNamespaceSelection(companyId, namespaceName.trim());
}
