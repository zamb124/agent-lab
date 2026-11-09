/**
 * flows-resolvers — чистые хелперы для нормализации данных в UI flows.
 *
 * Канон: дефолты живут только в фабриках (initialSlice). Эти helpers — для случаев,
 * когда нужен явный выбор-источника или приведение типа на стороне рендера.
 * Все функции бросают на отсутствии обязательных аргументов.
 */

export function isPlainObject(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function isNonEmptyString(value: unknown): value is string {
    return typeof value === 'string' && value.length > 0;
}

export function asString(value: unknown) {
    return typeof value === 'string' ? value : '';
}

export function asArray(value: unknown): unknown[] {
    if (!Array.isArray(value)) {
        return [];
    }
    const items: unknown[] = [];
    for (const item of value) {
        items.push(item);
    }
    return items;
}

export function asObject(value: unknown): Record<string, unknown> {
    return isPlainObject(value) ? value : {};
}

export function asNumber(value: unknown) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
}

export function asBoolean(value: unknown) {
    return Boolean(value);
}

/**
 * Активная компания для клиентских вызовов (voice, и т.д.) из `state.auth`.
 * Слайс `companies` хранит только список (`list`); объекта `companies.active` в сторе нет.
 */
export function authActiveCompanyId(state: unknown) {
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
export function stringOr(value: unknown, fallback: unknown) {
    if (typeof fallback !== 'string') {
        throw new Error('stringOr: fallback string required');
    }
    return isNonEmptyString(value) ? value : fallback;
}

/**
 * Цвет/токен с обязательным дефолтом — для опциональных кастомных цветов нод/sticky.
 */
export function colorOrDefault(value: unknown, defaultColor: unknown) {
    if (typeof defaultColor !== 'string' || defaultColor.length === 0) {
        throw new Error('colorOrDefault: defaultColor required');
    }
    return isNonEmptyString(value) ? value : defaultColor;
}

/**
 * Безопасное чтение branchData из editor slice. Slice гарантирует форму через
 * extraInitial, но защита от undefined нужна на момент монтирования.
 */
export function getBranchData(state: unknown): Record<string, unknown> {
    if (!isPlainObject(state)) {
        return { nodes: {}, edges: [], entry: null, variables: {}, resources: {} };
    }
    const branchDraft = state.branchData;
    if (!isPlainObject(branchDraft)) {
        return { nodes: {}, edges: [], entry: null, variables: {}, resources: {} };
    }
    return branchDraft;
}

export function getBranchNodes(state: unknown): Record<string, unknown> {
    const data = getBranchData(state);
    return isPlainObject(data.nodes) ? data.nodes : {};
}

export function getBranchEdges(state: unknown): unknown[] {
    const data = getBranchData(state);
    return Array.isArray(data.edges) ? data.edges : [];
}

/**
 * Возвращает ноду по id или null. Не бросает — рендер должен уметь скипать.
 */
export function getNodeByIdOrNull(branchData: unknown, nodeId: string): Record<string, unknown> | null {
    if (!isPlainObject(branchData)) return null;
    const nodes = branchData.nodes;
    if (!isPlainObject(nodes)) return null;
    if (typeof nodeId !== 'string' || nodeId.length === 0) return null;
    const node = nodes[nodeId];
    return isPlainObject(node) ? node : null;
}

export function getEdgeEndpoints(edge: unknown): { from_node: string; to_node: string } {
    if (!isPlainObject(edge)) return { from_node: '', to_node: '' };
    return {
        from_node: isNonEmptyString(edge.from_node) ? edge.from_node : '',
        to_node: isNonEmptyString(edge.to_node) ? edge.to_node : '',
    };
}

/**
 * Координаты ноды (pos_x/pos_y). Дефолт 0 — позиция всегда определена.
 */
export function getNodePos(node: unknown): { x: number; y: number } {
    if (!isPlainObject(node)) return { x: 0, y: 0 };
    return { x: asNumber(node.pos_x), y: asNumber(node.pos_y) };
}

/**
 * Видимое имя ноды (name → fallback на id, который обязателен).
 */
export function getNodeDisplayName(node: unknown, nodeId: string) {
    if (typeof nodeId !== 'string' || nodeId.length === 0) {
        throw new Error('getNodeDisplayName: nodeId required');
    }
    if (!isPlainObject(node)) return nodeId;
    return isNonEmptyString(node.name) ? node.name : nodeId;
}

/**
 * Тип ноды (строка). Если нет — пустая (для UI отображения).
 */
export function getNodeType(node: unknown) {
    if (!isPlainObject(node)) return '';
    return asString(node.type);
}

/**
 * Размер стикера с дефолтом из аргументов.
 */
export function getStickyNoteSize(note: unknown, defaultW: unknown, defaultH: unknown): { w: number; h: number } {
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
export function resolveFlowId(state: unknown) {
    if (!isPlainObject(state)) return null;
    return isNonEmptyString(state.flowId) ? state.flowId : null;
}

/**
 * Resolve активного branch id (или null).
 */
export function resolveBranchId(state: unknown) {
    if (!isPlainObject(state)) return null;
    return isNonEmptyString(state.currentBranchId) ? state.currentBranchId : null;
}

function _deepEqual(a: unknown, b: unknown) {
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
export function buildBranchNodeOverride(baseNode: unknown, effectiveNode: unknown) {
    if (!isPlainObject(effectiveNode)) {
        throw new Error('buildBranchNodeOverride: effectiveNode object required');
    }
    if (!isPlainObject(baseNode)) {
        return { ...effectiveNode };
    }
    return _diffForBranchOverride(baseNode, effectiveNode);
}

function _diffForBranchOverride(base: Record<string, unknown>, effective: Record<string, unknown>): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(effective)) {
        const ev = effective[key];
        if (ev === undefined) continue;
        if (!(key in base)) {
            out[key] = ev;
            continue;
        }
        const bv = base[key];
        if (isPlainObject(ev) && isPlainObject(bv)) {
            const sub = _diffForBranchOverride(bv, ev);
            if (Object.keys(sub).length > 0) {
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
export function buildFlowPublishBody(state: unknown): Record<string, unknown> | null {
    if (!isPlainObject(state) || !isPlainObject(state.flowConfig)) {
        return null;
    }
    const data = isPlainObject(state.branchData) ? state.branchData : {};
    const branchId = asString(state.currentBranchId);
    const isBase = !branchId || branchId === 'base';
    const body: Record<string, unknown> = { ...state.flowConfig };
    if (isBase) {
        body.nodes = data.nodes;
        body.edges = data.edges;
        body.entry = data.entry;
        body.variables = data.variables;
        body.resources = data.resources;
    } else {
        const existingBranches = isPlainObject(body.branches) ? body.branches : {};
        const existingBranch = isPlainObject(existingBranches[branchId]) ? existingBranches[branchId] : { name: branchId };
        const inheritedNodeIds = asArray(state.inheritedNodeIds);
        const inheritedEdgeKeys = asArray(state.inheritedEdgeKeys);
        const baseNodes = isPlainObject(state.flowConfig?.nodes) ? state.flowConfig.nodes : {};
        const ownNodes: Record<string, unknown> = {};
        for (const [id, node] of Object.entries(isPlainObject(data.nodes) ? data.nodes : {})) {
            if (!inheritedNodeIds.includes(id)) {
                ownNodes[id] = node;
            } else {
                const baseN = baseNodes[id];
                const fragment = buildBranchNodeOverride(baseN, node);
                if (Object.keys(fragment).length > 0) {
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
                nodes_mode: 'merge',
                edges: ownEdges,
                edges_mode: 'merge',
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
export function deriveRunPanelStatus(params: unknown) {
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
export function humanReadableErrorSummary(text: unknown) {
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
        const status = clientErr[1];
        const reason = clientErr[2];
        if (status === undefined || reason === undefined) {
            throw new Error('humanReadableErrorSummary: HTTP client error match incomplete');
        }
        return `HTTP ${status}: ${reason.trim()}`;
    }
    const httpPlain = line.match(/^HTTP\s+(\d{3})\s+(.+)$/i);
    if (httpPlain) {
        const status = httpPlain[1];
        const reason = httpPlain[2];
        if (status === undefined || reason === undefined) {
            throw new Error('humanReadableErrorSummary: HTTP status match incomplete');
        }
        return `HTTP ${status}: ${reason.trim()}`;
    }
    if (line.length > 200) {
        return `${line.slice(0, 200)}…`;
    }
    return line;
}

export { toolCallIconName } from '@platform/lib/utils/tool-call-icon.js';
