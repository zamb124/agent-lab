/**
 * Параметры graph workspace в query: view (3d | mindmap), root, depth, q.
 */

/** @typedef {'3d' | 'mindmap'} GraphCanvasViewMode */

const MIN_DEPTH = 1;
const MAX_DEPTH = 5;

/**
 * @param {unknown} raw
 * @returns {GraphCanvasViewMode}
 */
export function graphCanvasViewFromParam(raw) {
    if (raw === null || raw === undefined) {
        return 'mindmap';
    }
    if (typeof raw !== 'string') {
        throw new Error('graphCanvasViewFromParam: view must be string or null');
    }
    const t = raw.trim();
    if (t.length === 0) {
        return 'mindmap';
    }
    if (t === '3d') {
        return '3d';
    }
    if (t === 'mindmap') {
        return 'mindmap';
    }
    throw new Error(`graphCanvasViewFromParam: unknown view "${t}"`);
}

/**
 * @param {number} n
 * @returns {number}
 */
export function clampGraphDepth(n) {
    if (!Number.isFinite(n)) {
        throw new Error('clampGraphDepth: number required');
    }
    const i = Math.trunc(n);
    if (i < MIN_DEPTH) {
        return MIN_DEPTH;
    }
    if (i > MAX_DEPTH) {
        return MAX_DEPTH;
    }
    return i;
}

/**
 * @param {unknown} searchRaw
 * @returns {{
 *   view: GraphCanvasViewMode,
 *   root: string | null,
 *   depth: number | null,
 *   query: string,
 * }}
 */
export function parseGraphWorkspaceQuery(searchRaw) {
    const raw = typeof searchRaw === 'string' ? searchRaw : '';
    const qs = raw.startsWith('?') ? raw.slice(1) : raw;
    const params = new URLSearchParams(qs);
    const view = graphCanvasViewFromParam(params.get('view'));
    const rootRaw = params.get('root');
    let root = null;
    if (typeof rootRaw === 'string') {
        const tr = rootRaw.trim();
        if (tr.length > 0) {
            root = tr;
        }
    }
    const depthRaw = params.get('depth');
    let depth = null;
    if (typeof depthRaw === 'string' && depthRaw.trim().length > 0) {
        const n = Number(depthRaw.trim());
        if (!Number.isInteger(n)) {
            throw new Error('parseGraphWorkspaceQuery: depth must be integer');
        }
        depth = clampGraphDepth(n);
    }
    const qRaw = params.get('q');
    const query = typeof qRaw === 'string' ? qRaw : '';
    return { view, root, depth, query };
}

/**
 * @param {{
 *   view: GraphCanvasViewMode,
 *   root: string | null,
 *   depth: number | undefined | null,
 *   query: string | undefined,
 * }} parts
 * @returns {string} строка с ведущим `?` или `''` если пусто
 */
export function buildGraphWorkspaceSearch(parts) {
    if (!parts || typeof parts !== 'object') {
        throw new Error('buildGraphWorkspaceSearch: parts required');
    }
    const view = parts.view;
    if (view !== '3d' && view !== 'mindmap') {
        throw new Error('buildGraphWorkspaceSearch: view must be 3d or mindmap');
    }
    const p = new URLSearchParams();
    p.set('view', view);
    const root = parts.root;
    if (typeof root === 'string' && root.trim().length > 0) {
        p.set('root', root.trim());
    }
    if (parts.depth !== null && parts.depth !== undefined) {
        const d = clampGraphDepth(Number(parts.depth));
        p.set('depth', String(d));
    }
    const q = parts.query;
    if (typeof q === 'string' && q.length > 0) {
        p.set('q', q);
    }
    const s = p.toString();
    if (s.length === 0) {
        return '';
    }
    return `?${s}`;
}
