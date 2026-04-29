/**
 * Персистентность свёрнутых колонок канбана задач (tasks-page): по компании,
 * namespace и board_key с ответа API task-board-stages.
 */

export const TASKS_KANBAN_COLLAPSED_STORAGE_PREFIX = 'platform:crm-tasks-kanban-collapsed:v1:';

/**
 * @param {string} companyId
 * @param {string} namespaceName
 * @param {string} boardKey
 * @returns {string}
 */
export function buildStorageKey(companyId, namespaceName, boardKey) {
    if (typeof companyId !== 'string' || companyId.trim().length === 0) {
        throw new Error('tasks-kanban-column-collapse: companyId must be non-empty string');
    }
    if (typeof namespaceName !== 'string' || namespaceName.trim().length === 0) {
        throw new Error('tasks-kanban-column-collapse: namespaceName must be non-empty string');
    }
    if (typeof boardKey !== 'string' || boardKey.trim().length === 0) {
        throw new Error('tasks-kanban-column-collapse: boardKey must be non-empty string');
    }
    const c = companyId.trim();
    const ns = namespaceName.trim();
    const bk = boardKey.trim();
    return `${TASKS_KANBAN_COLLAPSED_STORAGE_PREFIX}${encodeURIComponent(c)}:${encodeURIComponent(ns)}:${encodeURIComponent(bk)}`;
}

/**
 * @param {string[]} ids
 * @param {Set<string>} allowed
 * @returns {string[]}
 */
export function pruneToAllowedIds(ids, allowed) {
    if (!Array.isArray(ids)) {
        throw new Error('tasks-kanban-column-collapse: ids must be an array');
    }
    if (!(allowed instanceof Set)) {
        throw new Error('tasks-kanban-column-collapse: allowed must be a Set');
    }
    const seen = new Set();
    const out = [];
    for (const raw of ids) {
        if (typeof raw !== 'string') {
            throw new Error('tasks-kanban-column-collapse: each id must be a string');
        }
        const id = raw.trim();
        if (!id) {
            throw new Error('tasks-kanban-column-collapse: empty status id');
        }
        if (!allowed.has(id) || seen.has(id)) {
            continue;
        }
        seen.add(id);
        out.push(id);
    }
    return out;
}

/**
 * @param {string} companyId
 * @param {string} namespaceName
 * @param {string} boardKey
 * @returns {string[]}
 */
export function readCollapsedStatusIds(companyId, namespaceName, boardKey) {
    const key = buildStorageKey(companyId, namespaceName, boardKey);
    const raw = window.localStorage.getItem(key);
    if (raw === null) {
        return [];
    }
    let parsed;
    try {
        parsed = JSON.parse(raw);
    } catch (e) {
        throw new Error(
            `readCollapsedStatusIds: invalid JSON for ${JSON.stringify(key)}: ${e instanceof Error ? e.message : String(e)}`,
        );
    }
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error(`readCollapsedStatusIds: expected object at ${JSON.stringify(key)}`);
    }
    if (!Object.prototype.hasOwnProperty.call(parsed, 'collapsed')) {
        throw new Error(`readCollapsedStatusIds: missing "collapsed" at ${JSON.stringify(key)}`);
    }
    const collapsed = parsed.collapsed;
    if (!Array.isArray(collapsed)) {
        throw new Error(`readCollapsedStatusIds: "collapsed" must be array at ${JSON.stringify(key)}`);
    }
    const seen = new Set();
    for (const item of collapsed) {
        if (typeof item !== 'string') {
            throw new Error(`readCollapsedStatusIds: collapsed entries must be strings at ${JSON.stringify(key)}`);
        }
        const id = item.trim();
        if (!id) {
            throw new Error(`readCollapsedStatusIds: empty status id at ${JSON.stringify(key)}`);
        }
        if (seen.has(id)) {
            throw new Error(`readCollapsedStatusIds: duplicate id ${JSON.stringify(id)} at ${JSON.stringify(key)}`);
        }
        seen.add(id);
    }
    return [...collapsed].map((s) => s.trim());
}

/**
 * @param {string} companyId
 * @param {string} namespaceName
 * @param {string} boardKey
 * @param {string[]} collapsedIds
 * @returns {void}
 */
export function writeCollapsedStatusIds(companyId, namespaceName, boardKey, collapsedIds) {
    const key = buildStorageKey(companyId, namespaceName, boardKey);
    if (!Array.isArray(collapsedIds)) {
        throw new Error('writeCollapsedStatusIds: collapsedIds must be an array');
    }
    const seen = new Set();
    const normalized = [];
    for (const raw of collapsedIds) {
        if (typeof raw !== 'string') {
            throw new Error('writeCollapsedStatusIds: each id must be a string');
        }
        const id = raw.trim();
        if (!id) {
            throw new Error('writeCollapsedStatusIds: empty status id');
        }
        if (seen.has(id)) {
            throw new Error(`writeCollapsedStatusIds: duplicate id ${JSON.stringify(id)}`);
        }
        seen.add(id);
        normalized.push(id);
    }
    window.localStorage.setItem(key, JSON.stringify({ collapsed: normalized }));
}
