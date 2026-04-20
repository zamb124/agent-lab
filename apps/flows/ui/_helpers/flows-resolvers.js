/**
 * flows-resolvers — pure helpers для нормализации данных в UI flows.
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
 * Безопасное чтение skillsData из editor slice. Slice гарантирует форму через
 * extraInitial, но защита от undefined нужна на момент монтирования.
 */
export function getSkillsData(state) {
    if (!isPlainObject(state)) {
        return { nodes: {}, edges: [], entry: null, variables: {}, resources: {} };
    }
    const skills = state.skillsData;
    if (!isPlainObject(skills)) {
        return { nodes: {}, edges: [], entry: null, variables: {}, resources: {} };
    }
    return skills;
}

export function getSkillsNodes(state) {
    const data = getSkillsData(state);
    return isPlainObject(data.nodes) ? data.nodes : {};
}

export function getSkillsEdges(state) {
    const data = getSkillsData(state);
    return Array.isArray(data.edges) ? data.edges : [];
}

/**
 * Возвращает ноду по id или null. Не бросает — рендер должен уметь скипать.
 */
export function getNodeByIdOrNull(skillsData, nodeId) {
    if (!isPlainObject(skillsData)) return null;
    const nodes = skillsData.nodes;
    if (!isPlainObject(nodes)) return null;
    if (typeof nodeId !== 'string' || nodeId.length === 0) return null;
    const node = nodes[nodeId];
    return isPlainObject(node) ? node : null;
}

/**
 * Возвращает endpoints ребра в каноничном виде. Поддерживает legacy-схему
 * with `from`/`to` и новую `from_node`/`to_node`.
 */
export function getEdgeEndpoints(edge) {
    if (!isPlainObject(edge)) return { from: '', to: '' };
    const from = isNonEmptyString(edge.from_node)
        ? edge.from_node
        : (isNonEmptyString(edge.from) ? edge.from : '');
    const to = isNonEmptyString(edge.to_node)
        ? edge.to_node
        : (isNonEmptyString(edge.to) ? edge.to : '');
    return { from, to };
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
 * Sticky note size с дефолтом из аргументов.
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
 * Resolve flow id из state редактора.
 */
export function resolveFlowId(state) {
    if (!isPlainObject(state)) return null;
    return isNonEmptyString(state.flowId) ? state.flowId : null;
}

/**
 * Resolve активного skill id (или 'base' если null).
 */
export function resolveSkillId(state) {
    if (!isPlainObject(state)) return null;
    return isNonEmptyString(state.currentSkillId) ? state.currentSkillId : null;
}
