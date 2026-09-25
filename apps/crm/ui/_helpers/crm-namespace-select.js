/**
 * Единая реактивная выборка пространства для CRM API и нормализация в optional query payload.
 *
 * `selectCrmApiNamespace` — «все пространства» в сайдбаре даёт `null` (без фильтра в API).
 * `selectCrmSidebarOrDefaultNamespace` — для UI, где нужна строка (например список типов в редакторе):
 * при «всех» подставляется `default`.
 */

import { getEffectiveCrmNamespaceApiFilter } from '@platform/lib/utils/platform-namespace.js';

/**
 * @param {unknown} state
 * @returns {string | null}
 */
export function selectCrmApiNamespace(state) {
    if (!state || typeof state !== 'object') {
        return null;
    }
    const user = state.auth && state.auth.user;
    if (!user || typeof user.company_id !== 'string') {
        return null;
    }
    const map = state.ui && state.ui.namespace && state.ui.namespace.selectionByCompany;
    return getEffectiveCrmNamespaceApiFilter(user.company_id, map);
}

/**
 * `null` из сайдбара — не передавать namespace в load/run (вся компания).
 * Непустая строка — как есть.
 *
 * @param {string | null} ns
 * @returns {string | undefined}
 */
export function crmNamespaceForOptionalQuery(ns) {
    if (ns === null) {
        return undefined;
    }
    if (typeof ns !== 'string') {
        throw new Error('crmNamespaceForOptionalQuery: namespace must be string or null');
    }
    if (ns.length === 0) {
        throw new Error('crmNamespaceForOptionalQuery: empty string is invalid');
    }
    return ns;
}

/**
 * Строка для локальных списков типов: при выборе «все пространства» — `default`.
 *
 * @param {unknown} state
 * @returns {string}
 */
export function selectCrmSidebarOrDefaultNamespace(state) {
    const raw = selectCrmApiNamespace(state);
    if (typeof raw === 'string' && raw.length > 0) {
        return raw;
    }
    return 'default';
}
