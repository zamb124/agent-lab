/**
 * Текущий CRM/RAG namespace для HTTP X-Platform-Namespace.
 *
 * Источник правды о выборе namespace — state.ui.namespace (см. reducers/ui.js).
 * Хранилище localStorage поддерживается ui.effect.js при UI_NAMESPACE_SELECT_REQUESTED;
 * утилита используется только http-слоем для подмешивания заголовка и
 * легаси-чтения сразу при старте, до того как bus прогрузит state.
 */

import { CoreEvents } from '../events/contract.js';
import { getPlatformBus } from '../events/bus-singleton.js';

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
 * Имя пространства для фильтрации CRM API (query/body): null — все пространства.
 * Если для компании в bus ещё нет ключа (до гидратации в crm-app), берётся тот же
 * localStorage, что и у CRM-сайдбара — иначе первый запрос после F5 уходит без namespace.
 *
 * @param {string} companyId
 * @param {Record<string, string> | null | undefined} selectionByCompany
 * @returns {string | null}
 */
export function getEffectiveCrmNamespaceApiFilter(companyId, selectionByCompany) {
    if (typeof companyId !== 'string' || companyId.trim().length === 0) {
        return null;
    }
    const cid = companyId.trim();
    const map =
        selectionByCompany && typeof selectionByCompany === 'object' && !Array.isArray(selectionByCompany)
            ? selectionByCompany
            : {};
    if (Object.prototype.hasOwnProperty.call(map, cid)) {
        const s = map[cid];
        return s === 'all' ? null : s;
    }
    const sidebar = getPlatformNamespaceSidebarSelection(cid);
    return sidebar === 'all' ? null : sidebar;
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
    const selection = useAll ? 'all' : rawName.trim();
    getPlatformBus().dispatch(
        CoreEvents.UI_NAMESPACE_SELECT_REQUESTED,
        { company_id: cid, selection },
        { source: 'local' },
    );
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
