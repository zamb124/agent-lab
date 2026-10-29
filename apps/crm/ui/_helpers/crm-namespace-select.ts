/**
 * Единая реактивная выборка пространства для CRM API и нормализация в optional query payload.
 *
 * `selectCrmApiNamespace` — «все пространства» в сайдбаре даёт `null` (без фильтра в API).
 * `selectCrmSidebarOrDefaultNamespace` — для UI, где нужна строка (например список типов в редакторе):
 * при «всех» подставляется `default`.
 */

import { getEffectiveCrmNamespaceApiFilter } from '@platform/lib/utils/platform-namespace.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function selectionByCompany(value: unknown): Record<string, string> | null {
    if (value == null || !isPlainRecord(value)) return null;
    const map: Record<string, string> = {};
    for (const [key, field] of Object.entries(value)) {
        if (typeof field !== 'string') {
            throw new Error('crm-namespace-select: selection must be a string');
        }
        map[key] = field;
    }
    return map;
}

/**
 * @param {unknown} state
 * @returns {string | null}
 */
export function selectCrmApiNamespace(state: unknown): string | null {
    if (!isPlainRecord(state)) {
        return null;
    }
    const auth = state.auth;
    const user = isPlainRecord(auth) ? auth.user : null;
    if (!isPlainRecord(user)) {
        return null;
    }
    const companyId = user.company_id;
    if (typeof companyId !== 'string') {
        return null;
    }
    const ui = state.ui;
    const namespace = isPlainRecord(ui) ? ui.namespace : null;
    const rawMap = isPlainRecord(namespace) ? namespace.selectionByCompany : null;
    return getEffectiveCrmNamespaceApiFilter(companyId, selectionByCompany(rawMap));
}

/**
 * `null` из сайдбара — не передавать namespace в load/run (вся компания).
 * Непустая строка — как есть.
 *
 * @param {string | null} ns
 * @returns {string | undefined}
 */
export function crmNamespaceForOptionalQuery(ns: string | null): string | undefined {
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
export function selectCrmSidebarOrDefaultNamespace(state: unknown): string {
    const raw = selectCrmApiNamespace(state);
    if (typeof raw === 'string' && raw.length > 0) {
        return raw;
    }
    return 'default';
}
