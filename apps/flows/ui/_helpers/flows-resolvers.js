/**
 * flows-resolvers — чистые хелперы для нормализации данных в UI flows.
 *
 * Канон: дефолты живут только в фабриках (initialSlice). Эти helpers — для случаев,
 * когда нужен явный выбор-источника или приведение типа на стороне рендера.
 * Все функции бросают на отсутствии обязательных аргументов.
 */

export function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function isNonEmptyString(value) {
    return typeof value === 'string' && value.length > 0;
}

export function asString(value) {
    return typeof value === 'string' ? value : '';
}

export function asArray(value) {
    return Array.isArray(value) ? value : [];
}

export function asObject(value) {
    return isPlainObject(value) ? value : {};
}

export function asNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
}

export function asBoolean(value) {
    return Boolean(value);
}

/**
 * Активная компания для клиентских вызовов (voice, и т.д.) из `state.auth`.
 * Слайс `companies` хранит только список (`list`); объекта `companies.active` в сторе нет.
 */
export function authActiveCompanyId(state) {
    if (!isPlainObject(state)) {
        return '';
    }
    const auth = state.auth;
    if (!isPlainObject(auth)) {
        return '';
    }
    if (isNonEmptyString(auth.activeCompanyId)) {
        return auth.activeCompanyId;
    }
    const user = auth.user;
    if (isPlainObject(user) && isNonEmptyString(user.company_id)) {
        return user.company_id;
    }
    return '';
}

/**
 * Возвращает строку value, если она непустая; иначе fallback (обязателен).
 */
export function stringOr(value, fallback) {
    if (typeof fallback !== 'string') {
        throw new Error('stringOr: fallback string required');
    }
    return isNonEmptyString(value) ? value : fallback;
}

/**
 * Цвет/токен с обязательным дефолтом — для опциональных кастомных цветов нод/sticky.
 */
export function colorOrDefault(value, defaultColor) {
    if (typeof defaultColor !== 'string' || defaultColor.length === 0) {
        throw new Error('colorOrDefault: defaultColor required');
    }
    return isNonEmptyString(value) ? value : defaultColor;
}

/**
 * Безопасное чтение branchData из editor slice. Slice гарантирует форму через
 * extraInitial, но защита от undefined нужна на момент монтирования.
 */
export function getBranchData(state) {
    if (!isPlainObject(state)) {
        return { nodes: {}, edges: [], entry: null, variables: {}, resources: {} };
    }
    const branchDraft = state.branchData;
    if (!isPlainObject(branchDraft)) {
        return { nodes: {}, edges: [], entry: null, variables: {}, resources: {} };
    }
    return branchDraft;
}

export function getBranchNodes(state) {
    const data = getBranchData(state);
    return isPlainObject(data.nodes) ? data.nodes : {};
}

export function getBranchEdges(state) {
    const data = getBranchData(state);
    return Array.isArray(data.edges) ? data.edges : [];
}

/**
 * Возвращает ноду по id или null. Не бросает — рендер должен уметь скипать.
 */
export function getNodeByIdOrNull(branchData, nodeId) {
    if (!isPlainObject(branchData)) return null;
    const nodes = branchData.nodes;
    if (!isPlainObject(nodes)) return null;
    if (typeof nodeId !== 'string' || nodeId.length === 0) return null;
    const node = nodes[nodeId];
    return isPlainObject(node) ? node : null;
}

export function getEdgeEndpoints(edge) {
    if (!isPlainObject(edge)) return { from_node: '', to_node: '' };
    return {
        from_node: isNonEmptyString(edge.from_node) ? edge.from_node : '',
        to_node: isNonEmptyString(edge.to_node) ? edge.to_node : '',
    };
}

/**
 * Координаты ноды (pos_x/pos_y). Дефолт 0 — позиция всегда определена.
 */
export function getNodePos(node) {
    if (!isPlainObject(node)) return { x: 0, y: 0 };
    return { x: asNumber(node.pos_x), y: asNumber(node.pos_y) };
}

/**
 * Видимое имя ноды (name → fallback на id, который обязателен).
 */
export function getNodeDisplayName(node, nodeId) {
    if (typeof nodeId !== 'string' || nodeId.length === 0) {
        throw new Error('getNodeDisplayName: nodeId required');
    }
    if (!isPlainObject(node)) return nodeId;
    return isNonEmptyString(node.name) ? node.name : nodeId;
}

/**
 * Тип ноды (строка). Если нет — пустая (для UI отображения).
 */
export function getNodeType(node) {
    if (!isPlainObject(node)) return '';
    return asString(node.type);
}

/**
 * Размер стикера с дефолтом из аргументов.
 */
export function getStickyNoteSize(note, defaultW, defaultH) {
    if (typeof defaultW !== 'number' || typeof defaultH !== 'number') {
        throw new Error('getStickyNoteSize: defaults required');
    }
    if (!isPlainObject(note)) return { w: defaultW, h: defaultH };
    const w = Number(note.width);
    const h = Number(note.height);
    return {
        w: Number.isFinite(w) && w > 0 ? w : defaultW,
        h: Number.isFinite(h) && h > 0 ? h : defaultH,
    };
}

/**
 * Получение flow_id из state редактора.
 */
export function resolveFlowId(state) {
    if (!isPlainObject(state)) return null;
    return isNonEmptyString(state.flowId) ? state.flowId : null;
}

/**
 * Resolve активного branch id (или null).
 */
export function resolveBranchId(state) {
    if (!isPlainObject(state)) return null;
    return isNonEmptyString(state.currentBranchId) ? state.currentBranchId : null;
}

function _deepEqual(a, b) {
    if (a === b) return true;
    if (Array.isArray(a) && Array.isArray(b)) {
        if (a.length !== b.length) return false;
        for (let i = 0; i < a.length; i += 1) {
            if (!_deepEqual(a[i], b[i])) return false;
        }
        return true;
    }
    if (isPlainObject(a) && isPlainObject(b)) {
        const keysA = Object.keys(a);
        const keysB = Object.keys(b);
        if (keysA.length !== keysB.length) return false;
        for (const k of keysA) {
            if (!_deepEqual(a[k], b[k])) return false;
        }
        return true;
    }
    return false;
}

/**
 * Фрагмент ноды для `branches[branchId].nodes` при merge: отличия effective от base.
 * Бэкенд делает deep_merge(base_node, branch_fragment) — см. FlowFactory._merge_nodes.
 */
export function buildBranchNodeOverride(baseNode, effectiveNode) {
    if (!isPlainObject(effectiveNode)) {
        throw new Error('buildBranchNodeOverride: effectiveNode object required');
    }
    if (!isPlainObject(baseNode)) {
        return { ...effectiveNode };
    }
    return _diffForBranchOverride(baseNode, effectiveNode);
}

function _diffForBranchOverride(base, effective) {
    const out = {};
    for (const key of Object.keys(effective)) {
        const ev = effective[key];
        if (ev === undefined) continue;
        if (!(key in base)) {
            out[key] = ev;
            continue;
        }
        const bv = base[key];
        if (isPlainObject(ev) && !Array.isArray(ev) && isPlainObject(bv) && !Array.isArray(bv)) {
            const sub = _diffForBranchOverride(bv, ev);
            if (isPlainObject(sub) && Object.keys(sub).length > 0) {
                out[key] = sub;
            }
        } else if (Array.isArray(ev)) {
            if (!_deepEqual(ev, Array.isArray(bv) ? bv : null)) {
                out[key] = ev;
            }
        } else if (!_deepEqual(ev, bv)) {
            out[key] = ev;
        }
    }
    return out;
}

/**
 * Тело flow для публикации (тот же объект, что уходит в PATCH) из slice редактора.
 *
 * @param {unknown} state
 * @returns {Record<string, unknown> | null}
 */
export function buildFlowPublishBody(state) {
    if (!isPlainObject(state) || !isPlainObject(state.flowConfig)) {
        return null;
    }
    const data = isPlainObject(state.branchData) ? state.branchData : {};
    const branchId = state.currentBranchId;
    const isBase = !branchId || branchId === 'base';
    const body = { ...state.flowConfig };
    if (isBase) {
        body.nodes = data.nodes;
        body.edges = data.edges;
        body.entry = data.entry;
        body.variables = data.variables;
        body.resources = data.resources;
    } else {
        const existingBranches = body.branches && typeof body.branches === 'object' ? body.branches : {};
        const existingBranch = isPlainObject(existingBranches[branchId]) ? existingBranches[branchId] : { name: branchId };
        const inheritedNodeIds = asArray(state.inheritedNodeIds);
        const inheritedEdgeKeys = asArray(state.inheritedEdgeKeys);
        const baseNodes = isPlainObject(state.flowConfig?.nodes) ? state.flowConfig.nodes : {};
        const ownNodes = {};
        for (const [id, node] of Object.entries(isPlainObject(data.nodes) ? data.nodes : {})) {
            if (!inheritedNodeIds.includes(id)) {
                ownNodes[id] = node;
            } else {
                const baseN = baseNodes[id];
                const fragment = buildBranchNodeOverride(baseN, node);
                if (isPlainObject(fragment) && Object.keys(fragment).length > 0) {
                    ownNodes[id] = fragment;
                }
            }
        }
        const ownEdges = asArray(data.edges).filter((edge) => {
            const { from_node, to_node } = getEdgeEndpoints(edge);
            const key = `${from_node}->${to_node}`;
            return !inheritedEdgeKeys.includes(key);
        });
        body.branches = {
            ...existingBranches,
            [branchId]: {
                ...existingBranch,
                nodes: ownNodes,
                edges: ownEdges,
                entry: data.entry,
                variables: data.variables,
            },
        };
        body.resources = data.resources;
    }
    return body;
}

/**
 * Статус панели тестового запуска: idle / running / passed / failed.
 *
 * @param {{ runInFlight: boolean, taskId: string | null, activeAssistant: unknown, runTrace: unknown }} params
 * @returns {'idle'|'running'|'passed'|'failed'}
 */
export function deriveRunPanelStatus(params) {
    if (!isPlainObject(params)) {
        throw new Error('deriveRunPanelStatus: params object required');
    }
    if (params.runInFlight === true) {
        return 'running';
    }
    const taskId = isNonEmptyString(params.taskId) ? params.taskId : null;
    const assistant = isPlainObject(params.activeAssistant) ? params.activeAssistant : null;
    if (assistant) {
        const err = assistant.error;
        if (typeof err === 'string' && err.length > 0) {
            return 'failed';
        }
    }
    const trace = Array.isArray(params.runTrace) ? params.runTrace : [];
    let lastTerminal = null;
    for (let i = trace.length - 1; i >= 0; i -= 1) {
        const e = trace[i];
        if (!isPlainObject(e)) {
            continue;
        }
        if (taskId !== null) {
            const tid = e.task_id;
            if (typeof tid === 'string' && tid.length > 0 && tid !== taskId) {
                continue;
            }
        }
        if (e.kind === 'status_terminal' && typeof e.terminal_state === 'string') {
            lastTerminal = e.terminal_state;
            break;
        }
    }
    if (lastTerminal === 'failed' || lastTerminal === 'error') {
        return 'failed';
    }
    if (lastTerminal === 'completed' || lastTerminal === 'finished') {
        return 'passed';
    }
    if (assistant && assistant.streaming === false) {
        if (assistant.inputRequired != null && isPlainObject(assistant.inputRequired)) {
            return 'idle';
        }
        const content = typeof assistant.content === 'string' ? assistant.content : '';
        if (content.length > 0) {
            return 'passed';
        }
    }
    return 'idle';
}

/**
 * Короткое описание ошибки для блока «для человека» (HTTP или первая строка).
 *
 * @param {string} text
 */
export function humanReadableErrorSummary(text) {
    if (typeof text !== 'string') {
        throw new Error('humanReadableErrorSummary: string required');
    }
    if (text.length === 0) {
        throw new Error('humanReadableErrorSummary: non-empty string required');
    }
    const idx = text.indexOf('\n');
    const firstLine = idx >= 0 ? text.slice(0, idx).trim() : text.trim();
    const line = firstLine.length > 0 ? firstLine : text.trim();
    if (line.length === 0) {
        throw new Error('humanReadableErrorSummary: no readable line');
    }
    const clientErr = line.match(/Client error\s+'(\d+)\s+([^']+)'/i);
    if (clientErr) {
        return `HTTP ${clientErr[1]}: ${clientErr[2].trim()}`;
    }
    const httpPlain = line.match(/^HTTP\s+(\d{3})\s+(.+)$/i);
    if (httpPlain) {
        return `HTTP ${httpPlain[1]}: ${httpPlain[2].trim()}`;
    }
    if (line.length > 200) {
        return `${line.slice(0, 200)}…`;
    }
    return line;
}

export { toolCallIconName } from '@platform/lib/utils/tool-call-icon.js';
