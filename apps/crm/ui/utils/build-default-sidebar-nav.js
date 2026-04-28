/**
 * Дефолтное дерево основного меню сайдбара по типам, разрешённым в пространстве.
 * Подписи групп задаёт хост (переведённые строки).
 *
 * @param {{
 *   allowedTypeIds: string[],
 *   entityTypes: Array<{ type_id: string, name?: string, parent_type_id?: string|null, icon?: string }>,
 *   labels: {
 *     groupNotes: string, groupTasks: string, groupEntities: string,
 *     allNotes: string, allTasks: string, allEntities: string,
 *   },
 * }} opts
 * @returns {Array<Record<string, unknown>>} узлы для platform-sidebar-nav-tree
 */

function _entityTypesById(entityTypes) {
    const byId = new Map();
    for (const t of entityTypes) {
        if (t && typeof t.type_id === 'string' && t.type_id.length > 0) {
            byId.set(t.type_id, t);
        }
    }
    return byId;
}

function _resolvedTypeIcon(byId, typeId, fallbackIcon) {
    if (typeof typeId !== 'string' || typeId.length === 0) {
        return fallbackIcon;
    }
    const t = byId.get(typeId);
    if (!t || typeof t.icon !== 'string') {
        return fallbackIcon;
    }
    const trimmed = t.icon.trim();
    if (trimmed.length === 0) {
        return fallbackIcon;
    }
    return trimmed;
}

function _entitySidebarIconFromType(byId, typeId, fallbackIcon) {
    if (typeof typeId !== 'string' || typeId.length === 0) {
        return fallbackIcon;
    }
    const t = byId.get(typeId);
    if (!t || typeof t.icon !== 'string') {
        return fallbackIcon;
    }
    const trimmed = t.icon.trim();
    if (trimmed.length === 0) {
        return fallbackIcon;
    }
    if (trimmed === 'file') {
        return 'folder';
    }
    if (/^[a-z0-9-]+$/i.test(trimmed)) {
        return trimmed;
    }
    return fallbackIcon;
}

function _typeIdFromNavLeafId(id) {
    if (typeof id !== 'string' || id.length === 0) return null;
    if (id.startsWith('nav-entity-')) return id.slice('nav-entity-'.length);
    if (id.startsWith('nav-task-')) return id.slice('nav-task-'.length);
    if (id.startsWith('nav-note-')) return id.slice('nav-note-'.length);
    return null;
}

function _defaultIconForTypedNavLeaf(id, typeId) {
    if (id.startsWith('nav-entity-')) return 'folder';
    if (id.startsWith('nav-task-')) return 'check';
    if (id.startsWith('nav-note-')) {
        if (typeId === 'meeting') return 'calendar';
        if (typeId === 'call') return 'phone';
    }
    return null;
}

const CRM_SIDEBAR_GROUP_ICON = Object.freeze({
    'grp-notes': 'list',
    'grp-tasks': 'check',
    'grp-entities': 'database',
});

function _sidebarGroupIconForId(id) {
    if (typeof id !== 'string' || id.length === 0) return null;
    if (Object.prototype.hasOwnProperty.call(CRM_SIDEBAR_GROUP_ICON, id)) {
        return CRM_SIDEBAR_GROUP_ICON[id];
    }
    return null;
}

/**
 * Первый лист секции — «Все заметки» / «Все задачи» / «Все сущности» (как в `buildDefaultSidebarNav`).
 * Чинит сохранённое дерево, где этот пункт отсутствует или не на первом месте.
 *
 * @param {Array<Record<string, unknown>>} nodes
 * @param {{ allNotes?: string, allTasks?: string, allEntities?: string }} labels
 * @returns {Array<Record<string, unknown>>}
 */
export function ensureCrmSidebarNavAllLeavesFirst(nodes, labels) {
    if (!Array.isArray(nodes)) {
        throw new Error('ensureCrmSidebarNavAllLeavesFirst: nodes must be an array');
    }
    const L = labels && typeof labels === 'object' ? labels : {};
    const allNotes = typeof L.allNotes === 'string' ? L.allNotes : '';
    const allTasks = typeof L.allTasks === 'string' ? L.allTasks : '';
    const allEntities = typeof L.allEntities === 'string' ? L.allEntities : '';
    const bag = { allNotes, allTasks, allEntities };
    return nodes.map((n) => _ensureAllFirstInNode(n, bag));
}

function _ensureAllFirstInNode(node, labelBag) {
    if (!node || typeof node !== 'object') {
        throw new Error('ensureCrmSidebarNavAllLeavesFirst: invalid node');
    }
    const children = Array.isArray(node.children) ? node.children : [];
    if (children.length === 0) {
        return node;
    }
    let nextChildren = children.map((c) => _ensureAllFirstInNode(c, labelBag));
    const gid = node.id;
    if (gid === 'grp-notes') {
        nextChildren = _prependCanonicalAllLeaf(nextChildren, {
            id: 'nav-notes-all',
            label: labelBag.allNotes,
            icon: 'list',
            routeKey: 'notes',
            search: '',
        });
    } else if (gid === 'grp-tasks') {
        nextChildren = _prependCanonicalAllLeaf(nextChildren, {
            id: 'nav-tasks-all',
            label: labelBag.allTasks,
            icon: 'list',
            routeKey: 'tasks',
            search: '',
        });
    } else if (gid === 'grp-entities') {
        nextChildren = _prependCanonicalAllLeaf(nextChildren, {
            id: 'nav-entities-all',
            label: labelBag.allEntities,
            icon: 'list',
            routeKey: 'entities',
            search: '',
        });
    }
    return { ...node, children: nextChildren };
}

function _prependCanonicalAllLeaf(children, spec) {
    if (!spec || typeof spec.id !== 'string' || spec.id.length === 0) {
        throw new Error('_prependCanonicalAllLeaf: spec.id required');
    }
    if (typeof spec.routeKey !== 'string' || spec.routeKey.length === 0) {
        throw new Error('_prependCanonicalAllLeaf: spec.routeKey required');
    }
    const rest = children.filter((c) => c && c.id !== spec.id);
    const first = {
        id: spec.id,
        label: typeof spec.label === 'string' ? spec.label : '',
        icon: spec.icon,
        routeKey: spec.routeKey,
        search: typeof spec.search === 'string' ? spec.search : '',
    };
    return [first, ...rest];
}

function _typeDisplayLabel(byId, typeId) {
    const t = byId.get(typeId);
    if (t && typeof t.name === 'string' && t.name.length > 0) {
        return t.name;
    }
    return typeId;
}

function _makeEntityLeaf(tid, byId) {
    return {
        id: `nav-entity-${tid}`,
        label: _typeDisplayLabel(byId, tid),
        icon: _entitySidebarIconFromType(byId, tid, 'folder'),
        routeKey: 'entities',
        search: `?entity_type=${encodeURIComponent(tid)}`,
    };
}

function _directEntityChildTypeIds(parentId, entitySet, byId) {
    const out = [];
    for (const tid of entitySet) {
        if (tid === parentId) continue;
        const meta = byId.get(tid);
        const p = meta && typeof meta.parent_type_id === 'string' ? meta.parent_type_id : '';
        if (p === parentId) {
            out.push(tid);
        }
    }
    out.sort((a, b) => _typeDisplayLabel(byId, a).localeCompare(_typeDisplayLabel(byId, b)));
    return out;
}

function _entityNavRootTypeIds(entitySet, byId) {
    const out = [];
    for (const tid of entitySet) {
        const meta = byId.get(tid);
        const p = meta && typeof meta.parent_type_id === 'string' ? meta.parent_type_id : '';
        if (p.length === 0 || !entitySet.has(p)) {
            out.push(tid);
        }
    }
    out.sort((a, b) => _typeDisplayLabel(byId, a).localeCompare(_typeDisplayLabel(byId, b)));
    return out;
}

function _entityNavExpandWithAncestors(initialSet, byId, skip) {
    const out = new Set(initialSet);
    for (const start of initialSet) {
        const visited = new Set();
        let cur = start;
        for (;;) {
            if (visited.has(cur)) {
                break;
            }
            visited.add(cur);
            const meta = byId.get(cur);
            if (!meta) {
                break;
            }
            const p = typeof meta.parent_type_id === 'string' ? meta.parent_type_id : '';
            if (p.length === 0) {
                break;
            }
            if (skip.has(p)) {
                break;
            }
            out.add(p);
            cur = p;
        }
    }
    return out;
}

function _buildEntityNavNode(tid, byId, entitySet) {
    const childIds = _directEntityChildTypeIds(tid, entitySet, byId);
    if (childIds.length === 0) {
        return _makeEntityLeaf(tid, byId);
    }
    const childNodes = childIds.map((cid) => _buildEntityNavNode(cid, byId, entitySet));
    return {
        id: `nav-entity-grp-${tid}`,
        label: _typeDisplayLabel(byId, tid),
        icon: _entitySidebarIconFromType(byId, tid, 'folder'),
        children: [_makeEntityLeaf(tid, byId), ...childNodes],
    };
}

function _deepCopyNavNode(node) {
    if (!node || typeof node !== 'object') {
        throw new Error('_deepCopyNavNode: invalid node');
    }
    const ch = node.children;
    const out = { ...node };
    if (Array.isArray(ch) && ch.length > 0) {
        out.children = ch.map((c) => _deepCopyNavNode(c));
    } else {
        delete out.children;
    }
    return out;
}

/**
 * Дети `grp-notes` / `grp-tasks` / `grp-entities` из свежего `buildDefaultSidebarNav`,
 * чтобы новые типы и иерархия сущностей не «залипали» в старом `sidebar_navigation`.
 *
 * @param {Array<Record<string, unknown>>} nodes
 * @param {Array<Record<string, unknown>>} canonicalNodes
 */
export function replaceCrmSidebarGroupChildrenFromCanonical(nodes, canonicalNodes) {
    if (!Array.isArray(nodes)) {
        throw new Error('replaceCrmSidebarGroupChildrenFromCanonical: nodes must be an array');
    }
    if (!Array.isArray(canonicalNodes)) {
        throw new Error('replaceCrmSidebarGroupChildrenFromCanonical: canonicalNodes must be an array');
    }
    const canonMap = new Map();
    for (const n of canonicalNodes) {
        if (n && typeof n.id === 'string' && n.id.length > 0) {
            canonMap.set(n.id, n);
        }
    }
    return nodes.map((node) => {
        if (!node || typeof node.id !== 'string') {
            return node;
        }
        const cid = node.id;
        if (cid === 'grp-notes' || cid === 'grp-tasks' || cid === 'grp-entities') {
            const canon = canonMap.get(cid);
            if (canon && Array.isArray(canon.children) && canon.children.length > 0) {
                const childrenCopy = canon.children.map((ch) => _deepCopyNavNode(ch));
                const out = { ...node, children: childrenCopy };
                if (typeof canon.icon === 'string' && canon.icon.length > 0) {
                    out.icon = canon.icon;
                }
                return out;
            }
        }
        return node;
    });
}

/**
 * Дополняет дерево из API недостающими верхнеуровневыми узлами из canonical (порядок как у canonical).
 * Сохранённый snapshot мог содержать только часть секций (например только grp-entities).
 *
 * @param {Array<Record<string, unknown>>} patchedNodes
 * @param {Array<Record<string, unknown>>} canonicalNodes
 * @returns {Array<Record<string, unknown>>}
 */
export function mergeCrmSidebarNavMissingGroups(patchedNodes, canonicalNodes) {
    if (!Array.isArray(patchedNodes)) {
        throw new Error('mergeCrmSidebarNavMissingGroups: patchedNodes must be an array');
    }
    if (!Array.isArray(canonicalNodes)) {
        throw new Error('mergeCrmSidebarNavMissingGroups: canonicalNodes must be an array');
    }
    const patchedById = new Map();
    for (const n of patchedNodes) {
        if (n && typeof n.id === 'string' && n.id.length > 0) {
            patchedById.set(n.id, n);
        }
    }
    const out = [];
    for (const c of canonicalNodes) {
        if (!c || typeof c.id !== 'string' || c.id.length === 0) {
            continue;
        }
        const p = patchedById.get(c.id);
        if (p) {
            out.push(p);
            patchedById.delete(c.id);
        } else {
            out.push(_deepCopyNavNode(c));
        }
    }
    for (const n of patchedById.values()) {
        out.push(n);
    }
    return out;
}

/**
 * Подставляет иконки листьев `nav-entity-*` / `nav-task-*` / `nav-note-*` из актуальных типов
 * и статичные иконки секций `grp-notes` / `grp-tasks` / `grp-entities` (как у плоского CRM-меню).
 * Нужно при сохранённом `sidebar_navigation`: снимок не обновляется при смене иконки типа.
 *
 * @param {Array<Record<string, unknown>>} nodes
 * @param {Array<{ type_id: string, icon?: string }>} entityTypes
 * @returns {Array<Record<string, unknown>>}
 */
export function enrichSidebarNavWithEntityTypeIcons(nodes, entityTypes) {
    if (!Array.isArray(nodes)) {
        throw new Error('enrichSidebarNavWithEntityTypeIcons: nodes must be an array');
    }
    const byId = _entityTypesById(Array.isArray(entityTypes) ? entityTypes : []);
    return nodes.map((n) => _enrichSidebarNavNode(n, byId));
}

function _enrichSidebarNavNode(node, byId) {
    if (!node || typeof node !== 'object') {
        throw new Error('enrichSidebarNavWithEntityTypeIcons: invalid node');
    }
    const children = Array.isArray(node.children) ? node.children : [];
    if (children.length > 0) {
        const enrichedChildren = children.map((c) => _enrichSidebarNavNode(c, byId));
        const gid = node.id;
        const groupIcon = typeof gid === 'string' ? _sidebarGroupIconForId(gid) : null;
        let next = { ...node, children: enrichedChildren };
        if (groupIcon !== null) {
            next = { ...next, icon: groupIcon };
        } else if (typeof gid === 'string' && gid.startsWith('nav-entity-grp-')) {
            const rootTid = gid.slice('nav-entity-grp-'.length);
            if (rootTid.length > 0) {
                next = {
                    ...next,
                    icon: _entitySidebarIconFromType(byId, rootTid, 'folder'),
                };
            }
        }
        return next;
    }
    const id = node.id;
    if (typeof id !== 'string') {
        return node;
    }
    const tid = _typeIdFromNavLeafId(id);
    if (tid === null || tid.length === 0) {
        return node;
    }
    const fallback = _defaultIconForTypedNavLeaf(id, tid);
    if (fallback === null) {
        return node;
    }
    const icon = id.startsWith('nav-entity-')
        ? _entitySidebarIconFromType(byId, tid, fallback)
        : _resolvedTypeIcon(byId, tid, fallback);
    return { ...node, icon };
}

export function buildDefaultSidebarNav(opts) {
    if (!opts || typeof opts !== 'object') {
        throw new Error('buildDefaultSidebarNav: opts required');
    }
    const allowedTypeIds = Array.isArray(opts.allowedTypeIds) ? opts.allowedTypeIds : [];
    const allowed = new Set(
        allowedTypeIds.filter((id) => typeof id === 'string' && id.length > 0),
    );
    const entityTypes = Array.isArray(opts.entityTypes) ? opts.entityTypes : [];
    const labels = opts.labels && typeof opts.labels === 'object' ? opts.labels : {};
    const groupNotes = typeof labels.groupNotes === 'string' ? labels.groupNotes : '';
    const groupTasks = typeof labels.groupTasks === 'string' ? labels.groupTasks : '';
    const groupEntities = typeof labels.groupEntities === 'string' ? labels.groupEntities : '';
    const allNotes = typeof labels.allNotes === 'string' ? labels.allNotes : '';
    const allTasks = typeof labels.allTasks === 'string' ? labels.allTasks : '';
    const allEntities = typeof labels.allEntities === 'string' ? labels.allEntities : '';

    const byId = _entityTypesById(entityTypes);

    const out = [];

    const noteChildren = [];
    if (allowed.has('note') || allowed.has('meeting') || allowed.has('call')) {
        noteChildren.push({
            id: 'nav-notes-all',
            label: allNotes,
            icon: 'list',
            routeKey: 'notes',
            search: '',
        });
    }
    for (const tid of ['meeting', 'call']) {
        if (!allowed.has(tid)) continue;
        const t = byId.get(tid);
        const label = t && typeof t.name === 'string' && t.name.length > 0 ? t.name : tid;
        const noteFallback = tid === 'meeting' ? 'calendar' : 'phone';
        const icon = _resolvedTypeIcon(byId, tid, noteFallback);
        noteChildren.push({
            id: `nav-note-${tid}`,
            label,
            icon,
            routeKey: 'notes',
            search: `?entity_type=note&entity_subtype=${encodeURIComponent(tid)}`,
        });
    }
    if (noteChildren.length > 0) {
        out.push({
            id: 'grp-notes',
            label: groupNotes,
            icon: CRM_SIDEBAR_GROUP_ICON['grp-notes'],
            children: noteChildren,
        });
    }

    const taskSubIds = [];
    for (const tid of allowed) {
        const meta = byId.get(tid);
        const parent = meta && typeof meta.parent_type_id === 'string' ? meta.parent_type_id : '';
        if (parent === 'task' && tid !== 'task') {
            taskSubIds.push(tid);
        }
    }
    taskSubIds.sort();

    const taskChildren = [];
    if (allowed.has('task') || taskSubIds.length > 0) {
        taskChildren.push({
            id: 'nav-tasks-all',
            label: allTasks,
            icon: 'list',
            routeKey: 'tasks',
            search: '',
        });
    }
    for (const tid of taskSubIds) {
        const t = byId.get(tid);
        const label = t && typeof t.name === 'string' && t.name.length > 0 ? t.name : tid;
        taskChildren.push({
            id: `nav-task-${tid}`,
            label,
            icon: _resolvedTypeIcon(byId, tid, 'check'),
            routeKey: 'tasks',
            search: `?entity_type=task&entity_subtype=${encodeURIComponent(tid)}`,
        });
    }
    if (taskChildren.length > 0) {
        out.push({
            id: 'grp-tasks',
            label: groupTasks,
            icon: CRM_SIDEBAR_GROUP_ICON['grp-tasks'],
            children: taskChildren,
        });
    }

    const skip = new Set(['note', 'meeting', 'call', 'task', ...taskSubIds]);
    const entitySetRaw = new Set();
    for (const tid of allowed) {
        if (!skip.has(tid)) {
            entitySetRaw.add(tid);
        }
    }
    const entitySet = _entityNavExpandWithAncestors(entitySetRaw, byId, skip);
    const entityRootIds = _entityNavRootTypeIds(entitySet, byId);
    const entityChildren = [];
    if (entityRootIds.length > 0) {
        entityChildren.push({
            id: 'nav-entities-all',
            label: allEntities,
            icon: 'list',
            routeKey: 'entities',
            search: '',
        });
        for (const rid of entityRootIds) {
            entityChildren.push(_buildEntityNavNode(rid, byId, entitySet));
        }
    }
    if (entityChildren.length > 0) {
        out.push({
            id: 'grp-entities',
            label: groupEntities,
            icon: CRM_SIDEBAR_GROUP_ICON['grp-entities'],
            children: entityChildren,
        });
    }

    out.push({
        id: 'nav-graph',
        label: typeof labels.graph === 'string' ? labels.graph : '',
        icon: 'share',
        routeKey: 'graph',
        search: '',
    });

    return out;
}

/**
 * API → дерево для Lit (поля camelCase).
 * @param {Array<Record<string, unknown>> | null | undefined} raw
 */
export function mapSidebarNavFromApi(raw) {
    if (raw === null || raw === undefined) {
        return null;
    }
    if (!Array.isArray(raw)) {
        throw new Error('mapSidebarNavFromApi: expected array or null');
    }
    return raw.map((entry) => _mapEntry(entry));
}

function _mapEntry(entry) {
    if (!entry || typeof entry !== 'object') {
        throw new Error('mapSidebarNavFromApi: invalid entry');
    }
    const id = entry.id;
    const label = entry.label;
    if (typeof id !== 'string' || id.length === 0) {
        throw new Error('mapSidebarNavFromApi: id required');
    }
    if (typeof label !== 'string') {
        throw new Error('mapSidebarNavFromApi: label required');
    }
    const iconRaw = entry.icon;
    const icon = typeof iconRaw === 'string' && iconRaw.length > 0 ? iconRaw : undefined;
    const rkRaw = entry.route_key;
    const routeKey = typeof rkRaw === 'string' && rkRaw.length > 0 ? rkRaw : undefined;
    const searchRaw = entry.search;
    const search = typeof searchRaw === 'string' ? searchRaw : '';
    const chRaw = entry.children;
    const children = Array.isArray(chRaw) ? chRaw.map((c) => _mapEntry(c)) : [];
    const node = { id, label, search };
    if (icon !== undefined) node.icon = icon;
    if (routeKey !== undefined) node.routeKey = routeKey;
    if (children.length > 0) node.children = children;
    return node;
}

/**
 * Дерево → тело для PUT namespace (snake_case).
 * @param {Array<Record<string, unknown>>} nodes
 */
export function sidebarNavTreeToApiPayload(nodes) {
    if (!Array.isArray(nodes)) {
        throw new Error('sidebarNavTreeToApiPayload: nodes must be array');
    }
    return nodes.map((n) => _toApiEntry(n));
}

function _toApiEntry(node) {
    if (!node || typeof node !== 'object') {
        throw new Error('sidebarNavTreeToApiPayload: invalid node');
    }
    const id = node.id;
    const label = node.label;
    if (typeof id !== 'string' || id.length === 0) {
        throw new Error('sidebarNavTreeToApiPayload: id required');
    }
    if (typeof label !== 'string') {
        throw new Error('sidebarNavTreeToApiPayload: label required');
    }
    const out = {
        id,
        label,
        search: typeof node.search === 'string' ? node.search : '',
    };
    if (typeof node.icon === 'string' && node.icon.length > 0) {
        out.icon = node.icon;
    }
    if (typeof node.routeKey === 'string' && node.routeKey.length > 0) {
        out.route_key = node.routeKey;
    }
    const children = node.children;
    if (Array.isArray(children) && children.length > 0) {
        out.children = children.map((c) => _toApiEntry(c));
    } else {
        out.children = [];
    }
    return out;
}
