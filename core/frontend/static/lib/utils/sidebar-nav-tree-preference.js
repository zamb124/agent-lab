/**
 * Персистентность свёрнутых групп platform-sidebar-nav-tree (по scope).
 * В storage только пары id -> false (явно свёрнута); отсутствие ключа у группы = развёрнута.
 */

export const SIDEBAR_NAV_TREE_EXPANDED_STORAGE_PREFIX = 'platform:sidebar-nav-tree-expanded:';

/**
 * @param {string} scope
 * @returns {string}
 */
function _storageKey(scope) {
    if (typeof scope !== 'string' || scope.trim().length === 0) {
        throw new Error('sidebar-nav-tree preference: scope must be non-empty string');
    }
    return `${SIDEBAR_NAV_TREE_EXPANDED_STORAGE_PREFIX}${scope.trim()}`;
}

/**
 * @param {string} scope
 * @returns {Record<string, boolean>}
 */
export function readSidebarNavTreeExpanded(scope) {
    const key = _storageKey(scope);
    const raw = window.localStorage.getItem(key);
    if (raw === null) {
        return Object.create(null);
    }
    let parsed;
    try {
        parsed = JSON.parse(raw);
    } catch (e) {
        throw new Error(
            `readSidebarNavTreeExpanded: invalid JSON for ${JSON.stringify(key)}: ${e instanceof Error ? e.message : String(e)}`,
        );
    }
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error(`readSidebarNavTreeExpanded: expected object at ${JSON.stringify(key)}`);
    }
    const out = Object.create(null);
    for (const k of Object.keys(parsed)) {
        if (typeof k !== 'string') {
            throw new Error(`readSidebarNavTreeExpanded: key must be string at ${JSON.stringify(key)}`);
        }
        const v = parsed[k];
        if (v === false) {
            out[k] = false;
            continue;
        }
        if (v === true) {
            throw new Error(
                `readSidebarNavTreeExpanded: only false values allowed in storage, got true for ${JSON.stringify(k)}`,
            );
        }
        throw new Error(
            `readSidebarNavTreeExpanded: value for ${JSON.stringify(k)} must be boolean false, got ${typeof v}`,
        );
    }
    return out;
}

/**
 * Сохранять только свёрнутые группы (id -> false). Остальные ключи из expandedById игнорируются.
 *
 * @param {string} scope
 * @param {Record<string, boolean>} expandedById
 */
export function writeSidebarNavTreeExpanded(scope, expandedById) {
    const key = _storageKey(scope);
    if (expandedById === null || typeof expandedById !== 'object' || Array.isArray(expandedById)) {
        throw new Error('writeSidebarNavTreeExpanded: expandedById must be a plain object');
    }
    const compact = Object.create(null);
    for (const id of Object.keys(expandedById)) {
        if (typeof id !== 'string') {
            throw new Error('writeSidebarNavTreeExpanded: keys must be strings');
        }
        const v = expandedById[id];
        if (v === false) {
            compact[id] = false;
            continue;
        }
        if (v === true || v === undefined) {
            continue;
        }
        throw new Error(`writeSidebarNavTreeExpanded: value for ${JSON.stringify(id)} must be true, false, or absent`);
    }
    window.localStorage.setItem(key, JSON.stringify(compact));
}
