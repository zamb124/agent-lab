/**
 * Нормализация дерева spans для platform-trace-viewer.
 * Вход — узлы как в ответе API (после build_span_tree): объекты с children[].
 */

/** @typedef {{ span_id: string, trace_id?: string, parent_span_id?: string|null, operation_name?: string, name?: string, kind?: string|null, start_time?: string|null, end_time?: string|null, duration_ms?: number|null, status?: string|null, status_message?: string|null, service_name?: string, event_type?: string|null, attributes?: Record<string, unknown>, children?: unknown[] }} TraceSpanRaw */

/** @typedef {{ id: string, title: string, subtitle: string, uiKind: string, startMs: number|null, endMs: number|null, durationMs: number|null, hasError: boolean, serviceKey: string, childCount: number, children: TraceViewNode[], raw: TraceSpanRaw }} TraceViewNode */

/**
 * @param {unknown} v
 * @returns {v is Record<string, unknown>}
 */
function isPlainObject(v) {
    return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/**
 * @param {unknown} raw
 * @returns {TraceSpanRaw}
 */
export function assertTraceSpanRaw(raw) {
    if (!isPlainObject(raw)) {
        throw new Error('trace-view-model: span must be an object');
    }
    const spanId = raw.span_id;
    if (typeof spanId !== 'string' || spanId.length === 0) {
        throw new Error('trace-view-model: span.span_id must be a non-empty string');
    }
    return /** @type {TraceSpanRaw} */ (raw);
}

/**
 * @param {string|null|undefined} iso
 * @returns {number|null}
 */
export function parseIsoToMs(iso) {
    if (iso == null || typeof iso !== 'string' || iso.length === 0) {
        return null;
    }
    const ms = Date.parse(iso);
    if (Number.isNaN(ms)) {
        return null;
    }
    return ms;
}

/**
 * @param {TraceSpanRaw} raw
 * @returns {string}
 */
export function inferUiKind(raw) {
    const attrs = isPlainObject(raw.attributes) ? raw.attributes : null;
    const opNameAttr =
        attrs && typeof attrs['gen_ai.operation.name'] === 'string'
            ? attrs['gen_ai.operation.name']
            : '';
    if (opNameAttr === 'chat' || opNameAttr === 'text_completion') {
        return 'generation';
    }
    if (opNameAttr === 'execute_tool') {
        return 'tool';
    }
    if (opNameAttr === 'retrieval') {
        return 'retrieval';
    }
    if (opNameAttr === 'embeddings') {
        return 'embedding';
    }
    if (opNameAttr === 'invoke_agent' || opNameAttr === 'create_agent') {
        return 'agent';
    }
    const et = typeof raw.event_type === 'string' ? raw.event_type.toLowerCase() : '';
    if (et.includes('llm') || et.includes('generation')) {
        return 'generation';
    }
    if (et.includes('tool')) {
        return 'tool';
    }
    if (et.includes('retriev')) {
        return 'retrieval';
    }
    if (et.includes('agent')) {
        return 'agent';
    }
    const on = typeof raw.operation_name === 'string' ? raw.operation_name.toLowerCase() : '';
    if (on.includes('llm_call') || on.includes('llm call')) {
        return 'generation';
    }
    if (on.includes('tool_call') || on.includes('tool call')) {
        return 'tool';
    }
    if (on.includes('interrupt')) {
        return 'interrupt';
    }
    if (on.includes('flow') && on.includes('span')) {
        return 'flow';
    }
    return 'span';
}

/**
 * @param {string} serviceName
 * @returns {string}
 */
export function serviceHueCssVar(serviceName) {
    if (typeof serviceName !== 'string' || serviceName.length === 0) {
        return 'var(--accent)';
    }
    let h = 0;
    for (let i = 0; i < serviceName.length; i += 1) {
        h = (h * 31 + serviceName.charCodeAt(i)) % 360;
    }
    return `hsl(${h} 55% 45%)`;
}

/**
 * @param {TraceSpanRaw} raw
 * @returns {TraceViewNode}
 */
export function normalizeSpanNode(raw) {
    const s = assertTraceSpanRaw(raw);
    const titleFromOp = typeof s.operation_name === 'string' ? s.operation_name : '';
    const titleFromName = typeof s.name === 'string' ? s.name : '';
    const title = titleFromOp.length > 0 ? titleFromOp : titleFromName.length > 0 ? titleFromName : s.span_id;

    const svc = typeof s.service_name === 'string' ? s.service_name : '';
    const ev = typeof s.event_type === 'string' ? s.event_type : '';
    const subtitleParts = [];
    if (svc.length > 0) {
        subtitleParts.push(svc);
    }
    if (ev.length > 0) {
        subtitleParts.push(ev);
    }
    const subtitle = subtitleParts.join(' · ');

    const startMs = parseIsoToMs(s.start_time);
    let endMs = parseIsoToMs(s.end_time);
    let durationMs = typeof s.duration_ms === 'number' && !Number.isNaN(s.duration_ms) ? s.duration_ms : null;
    if (endMs == null && startMs != null && durationMs != null) {
        endMs = startMs + durationMs;
    }
    if (durationMs == null && startMs != null && endMs != null) {
        durationMs = Math.max(0, endMs - startMs);
    }

    const st = typeof s.status === 'string' ? s.status : '';
    const hasError = st.toUpperCase() === 'ERROR' || st.toLowerCase() === 'error';

    const rawChildren = Array.isArray(s.children) ? s.children : [];
    const children = rawChildren.map((c) => normalizeSpanNode(assertTraceSpanRaw(c)));

    return {
        id: s.span_id,
        title,
        subtitle,
        uiKind: inferUiKind(s),
        startMs,
        endMs,
        durationMs,
        hasError,
        serviceKey: svc.length > 0 ? svc : 'unknown',
        childCount: children.length,
        children,
        raw: s,
    };
}

/**
 * @param {unknown[]} rootsRaw
 * @returns {TraceViewNode[]}
 */
export function normalizeTraceRoots(rootsRaw) {
    if (!Array.isArray(rootsRaw)) {
        throw new Error('trace-view-model: roots must be an array');
    }
    return rootsRaw.map((r) => normalizeSpanNode(assertTraceSpanRaw(r)));
}

/**
 * @param {TraceSpanRaw} raw
 * @param {string} q
 * @returns {boolean}
 */
export function spanMatchesQuery(raw, q) {
    if (q.length === 0) {
        return true;
    }
    const s = assertTraceSpanRaw(raw);
    const hay = [
        s.span_id,
        typeof s.operation_name === 'string' ? s.operation_name : '',
        typeof s.name === 'string' ? s.name : '',
        typeof s.service_name === 'string' ? s.service_name : '',
        typeof s.event_type === 'string' ? s.event_type : '',
        typeof s.trace_id === 'string' ? s.trace_id : '',
    ]
        .join('\n')
        .toLowerCase();
    return hay.includes(q);
}

/**
 * @param {TraceSpanRaw[]} roots
 * @param {(raw: TraceSpanRaw) => boolean} pred
 * @returns {Set<string>}
 */
export function collectMatchingSpanIds(roots, pred) {
    /** @type {Set<string>} */
    const out = new Set();
    /** @param {TraceSpanRaw} node */
    function walk(node) {
        if (pred(node)) {
            out.add(node.span_id);
        }
        const ch = node.children;
        if (Array.isArray(ch)) {
            for (const c of ch) {
                walk(assertTraceSpanRaw(c));
            }
        }
    }
    for (const r of roots) {
        walk(assertTraceSpanRaw(r));
    }
    return out;
}

/**
 * @param {TraceSpanRaw[]} roots
 */
export function buildParentMap(roots) {
    /** @type {Map<string, string|null>} */
    const m = new Map();
    /** @param {TraceSpanRaw} node @param {string|null} parentId */
    function walk(node, parentId) {
        m.set(node.span_id, parentId);
        const ch = node.children;
        if (Array.isArray(ch)) {
            for (const c of ch) {
                const cr = assertTraceSpanRaw(c);
                walk(cr, node.span_id);
            }
        }
    }
    for (const r of roots) {
        walk(assertTraceSpanRaw(r), null);
    }
    return m;
}

/**
 * @param {Set<string>} matchedIds
 * @param {Map<string, string|null>} parentMap
 * @returns {Set<string>}
 */
export function ancestorIdsForMatches(matchedIds, parentMap) {
    /** @type {Set<string>} */
    const expand = new Set();
    for (const id of matchedIds) {
        let cur = parentMap.get(id);
        while (cur != null) {
            expand.add(cur);
            cur = parentMap.get(cur);
        }
    }
    return expand;
}

/**
 * @param {unknown[]} rootsRaw
 * @returns {{ min: number, max: number }|null}
 */
export function computeTraceTimeRangeMs(rootsRaw) {
    if (!Array.isArray(rootsRaw)) {
        return null;
    }
    /** @type {number[]} */
    const starts = [];
    /** @type {number[]} */
    const ends = [];
    /** @param {TraceSpanRaw} node */
    function walk(node) {
        const startMs = parseIsoToMs(node.start_time);
        let endMs = parseIsoToMs(node.end_time);
        const dur =
            typeof node.duration_ms === 'number' && !Number.isNaN(node.duration_ms) ? node.duration_ms : null;
        if (startMs == null) {
            return;
        }
        starts.push(startMs);
        if (endMs == null && dur != null) {
            endMs = startMs + dur;
        }
        if (endMs != null) {
            ends.push(endMs);
        } else {
            ends.push(startMs);
        }
        const ch = node.children;
        if (Array.isArray(ch)) {
            for (const c of ch) {
                walk(assertTraceSpanRaw(c));
            }
        }
    }
    for (const r of rootsRaw) {
        walk(assertTraceSpanRaw(r));
    }
    if (starts.length === 0) {
        return null;
    }
    const min = Math.min(...starts);
    const max = Math.max(...ends);
    if (max <= min) {
        return { min, max: min + 1 };
    }
    return { min, max };
}

/**
 * @param {TraceViewNode[]} nodes
 * @param {Set<string>} matchedIds
 * @returns {TraceViewNode[]}
 */
export function pruneTraceViewNodes(nodes, matchedIds) {
    /** @type {TraceViewNode[]} */
    const out = [];
    for (const n of nodes) {
        const childPruned = pruneTraceViewNodes(n.children, matchedIds);
        if (matchedIds.has(n.id) || childPruned.length > 0) {
            out.push({ ...n, children: childPruned });
        }
    }
    return out;
}

/**
 * @param {TraceViewNode} node
 * @param {number} traceMin
 * @param {number} traceMax
 * @param {number} depth
 * @returns {Array<{ node: TraceViewNode, depth: number, leftPct: number, widthPct: number }>}
 */
/**
 * Доля длительности узла относительно родителя (0–100) для мини-бара в дереве.
 * @param {TraceViewNode} node
 * @param {TraceViewNode|null} parent
 * @param {number|null} traceSpanMs длительность всего trace (для корней)
 * @returns {number}
 */
export function treeDurationBarPct(node, parent, traceSpanMs) {
    const d = node.durationMs;
    if (d == null || d <= 0) {
        return 0;
    }
    if (parent != null && parent.durationMs != null && parent.durationMs > 0) {
        return Math.min(100, (d / parent.durationMs) * 100);
    }
    if (traceSpanMs != null && traceSpanMs > 0) {
        return Math.min(100, (d / traceSpanMs) * 100);
    }
    return 0;
}

/**
 * @param {TraceViewNode} node
 * @param {number} traceMin
 * @param {number} traceMax
 * @param {number} depth
 * @returns {Array<{ node: TraceViewNode, depth: number, leftPct: number, widthPct: number }>}
 */
export function flattenTimelineRows(node, traceMin, traceMax, depth) {
    const span = traceMax - traceMin;
    if (span <= 0) {
        return [];
    }
    /** @type {Array<{ node: TraceViewNode, depth: number, leftPct: number, widthPct: number }>} */
    const rows = [];
    const startMs = node.startMs;
    const endMs = node.endMs;
    let leftPct = 0;
    let widthPct = 100;
    if (startMs != null && endMs != null) {
        leftPct = ((startMs - traceMin) / span) * 100;
        widthPct = Math.max(0.15, ((endMs - startMs) / span) * 100);
    }
    rows.push({ node, depth, leftPct, widthPct });
    for (const c of node.children) {
        rows.push(...flattenTimelineRows(c, traceMin, traceMax, depth + 1));
    }
    return rows;
}
